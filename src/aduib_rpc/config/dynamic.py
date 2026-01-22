from __future__ import annotations

"""Dynamic configuration sources and accessors."""

import asyncio
import inspect
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

__all__ = [
    "ConfigSource",
    "InMemoryConfigSource",
    "FileConfigSource",
    "DynamicConfig",
]

logger = logging.getLogger(__name__)

ConfigCallback = Callable[[str, str | None], Awaitable[None] | None]


class ConfigSource(ABC):
    """Abstract configuration source."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the value for a key if present."""

    @abstractmethod
    async def watch(self, prefix: str, callback: ConfigCallback) -> None:
        """Register a callback for keys with the given prefix."""


@dataclass(slots=True)
class _Watch:
    prefix: str
    callback: ConfigCallback
    active: bool = True


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


def _flatten_config(data: Mapping[str, Any], prefix: str = "") -> dict[str, str | None]:
    flattened: dict[str, str | None] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.update(_flatten_config(value, full_key))
        elif value is None:
            flattened[full_key] = None
        else:
            flattened[full_key] = str(value)
    return flattened


def _parse_kv(content: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value.startswith(("'", '"')):
            value = value[1:-1]
        data[key] = value
    return data


class InMemoryConfigSource(ConfigSource):
    """In-memory configuration source with change notifications."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._data: dict[str, str] = dict(initial or {})
        self._watchers: list[_Watch] = []
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, value: str | None) -> None:
        async with self._lock:
            previous = self._data.get(key)
            if value is None:
                self._data.pop(key, None)
            else:
                self._data[key] = value
            changed = previous != value
            watchers = list(self._watchers) if changed else []
        if changed:
            await self._notify(watchers, key, value)

    async def update(self, updates: Mapping[str, str | None]) -> None:
        notifications: list[tuple[str, str | None]] = []
        async with self._lock:
            for key, value in updates.items():
                previous = self._data.get(key)
                if value is None:
                    self._data.pop(key, None)
                else:
                    self._data[key] = value
                if previous != value:
                    notifications.append((key, value))
            watchers = list(self._watchers)
        for key, value in notifications:
            await self._notify(watchers, key, value)

    async def watch(self, prefix: str, callback: ConfigCallback) -> None:
        async with self._lock:
            self._watchers.append(_Watch(prefix=prefix, callback=callback))

    async def _notify(self, watchers: list[_Watch], key: str, value: str | None) -> None:
        for watcher in watchers:
            if not watcher.active or not key.startswith(watcher.prefix):
                continue
            try:
                await _maybe_await(watcher.callback(key, value))
            except Exception:
                logger.exception("Config watcher callback failed for key=%s", key)


class FileConfigSource(ConfigSource):
    """File-backed configuration source with hot reload support."""

    def __init__(
        self,
        path: str | Path,
        *,
        poll_interval: float = 1.0,
        parser: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        self._path = Path(path)
        self._poll_interval = max(0.1, float(poll_interval))
        self._parser = parser
        self._data: dict[str, str | None] = {}
        self._watchers: list[_Watch] = []
        self._lock = asyncio.Lock()
        self._reload_lock = asyncio.Lock()
        self._last_mtime: float | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._load_initial()

    async def get(self, key: str) -> str | None:
        await self._reload_if_needed()
        async with self._lock:
            return self._data.get(key)

    async def watch(self, prefix: str, callback: ConfigCallback) -> None:
        async with self._lock:
            self._watchers.append(_Watch(prefix=prefix, callback=callback))
            should_start = self._watch_task is None
        if should_start:
            self._watch_task = asyncio.create_task(self._poll_loop())

    async def reload(self) -> None:
        await self._load_and_notify(force=True)

    def _load_initial(self) -> None:
        mtime = self._stat_mtime()
        self._last_mtime = mtime
        if mtime is None:
            self._data = {}
            return
        try:
            self._data = self._load_sync()
        except Exception:
            logger.exception("Failed to load config file %s", self._path)
            self._data = {}

    async def _reload_if_needed(self) -> None:
        mtime = self._stat_mtime()
        if mtime == self._last_mtime:
            return
        await self._load_and_notify(current_mtime=mtime)

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._reload_if_needed()
            except Exception:
                logger.exception("Config file reload failed for %s", self._path)
            await asyncio.sleep(self._poll_interval)

    async def _load_and_notify(
        self,
        *,
        force: bool = False,
        current_mtime: float | None = None,
    ) -> None:
        async with self._reload_lock:
            mtime = current_mtime if current_mtime is not None else self._stat_mtime()
            if not force and mtime == self._last_mtime:
                return
            try:
                new_data = self._load_sync() if mtime is not None else {}
            except Exception:
                logger.exception("Failed to parse config file %s", self._path)
                return

            async with self._lock:
                old_data = dict(self._data)
                self._data = new_data
                self._last_mtime = mtime
                watchers = list(self._watchers)

        await self._notify_changes(old_data, new_data, watchers)

    async def _notify_changes(
        self,
        old_data: Mapping[str, str | None],
        new_data: Mapping[str, str | None],
        watchers: list[_Watch],
    ) -> None:
        for key in set(old_data) | set(new_data):
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            if old_value == new_value:
                continue
            for watcher in watchers:
                if not watcher.active or not key.startswith(watcher.prefix):
                    continue
                try:
                    await _maybe_await(watcher.callback(key, new_value))
                except Exception:
                    logger.exception("Config watcher callback failed for key=%s", key)

    def _stat_mtime(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _load_sync(self) -> dict[str, str | None]:
        content = self._path.read_text(encoding="utf-8")
        if self._parser is not None:
            parsed = self._parser(content)
        else:
            ext = self._path.suffix.lower()
            if ext == ".json":
                parsed = json.loads(content) if content.strip() else {}
            elif ext == ".toml":
                parsed = tomllib.loads(content) if content.strip() else {}
            elif ext in (".yaml", ".yml"):
                try:
                    import yaml
                except ImportError as exc:
                    raise RuntimeError(
                        "PyYAML is required to parse YAML config files."
                    ) from exc
                parsed = yaml.safe_load(content) or {}
            else:
                parsed = _parse_kv(content)
        if parsed is None:
            return {}
        if not isinstance(parsed, Mapping):
            raise ValueError("Config file must parse to a mapping.")
        return _flatten_config(parsed)


class DynamicConfig:
    """Dynamic config accessor across multiple sources."""

    def __init__(self, sources: list[ConfigSource]) -> None:
        self._sources = list(sources)
        self._subscriptions: list[_Watch] = []
        self._lock = asyncio.Lock()

    async def get(self, key: str, default: str | None = None) -> str | None:
        for source in self._sources:
            value = await source.get(key)
            if value is not None:
                return value
        return default

    async def get_int(self, key: str, default: int = 0) -> int:
        value = await self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        value = await self.get(key)
        if value is None:
            return default
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    async def get_float(self, key: str, default: float = 0.0) -> float:
        value = await self.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    async def subscribe(self, key: str, callback: ConfigCallback) -> Callable[[], None]:
        watch = _Watch(prefix=key, callback=callback)

        async def _source_callback(changed_key: str, value: str | None) -> None:
            if not watch.active or changed_key != key:
                return
            await _maybe_await(callback(changed_key, value))

        for source in self._sources:
            await source.watch(key, _source_callback)

        async with self._lock:
            self._subscriptions.append(watch)

        def _unsubscribe() -> None:
            watch.active = False

        return _unsubscribe

    async def reload(self) -> None:
        for source in self._sources:
            reload_fn = getattr(source, "reload", None)
            if reload_fn is None:
                continue
            result = reload_fn()
            if inspect.isawaitable(result):
                await result
