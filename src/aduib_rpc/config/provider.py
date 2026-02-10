from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from aduib_rpc.config.loader import ConfigError, load_config
from aduib_rpc.config.models import AduibRpcConfig

ConfigUpdateCallback = Callable[[AduibRpcConfig], Awaitable[None] | None]
ConfigErrorCallback = Callable[[Exception], Awaitable[None] | None]

logger = logging.getLogger(__name__)


def config_source_loader(name: str):
    """Decorator to register a config source loader class."""
    def decorator(cls: Any) -> Any:
        if not name:
            raise ValueError("Config source loader name must be provided")
        if not issubclass(cls, ConfigSourceLoader):
            raise TypeError("Config source loader must implement ConfigSourceLoader")
        ConfigSourceProvider.register_config_source_class(name, cls)
        logger.info("Config source loader %s registered", name)
        return cls
    return decorator


class ConfigSourceLoader(ABC):
    """Interface for config source loaders with optional live updates."""

    def __init__(self, *, target: AduibRpcConfig | None = None, **_: Any) -> None:
        self._target = target

    @property
    def target(self) -> AduibRpcConfig | None:
        return self._target

    def set_target(self, target: AduibRpcConfig | None) -> None:
        self._target = target

    def _update_target(self, updated: AduibRpcConfig) -> AduibRpcConfig:
        if self._target is None:
            self._target = updated
            return updated
        if self._target is updated:
            return self._target
        return ConfigUpdater.update_in_place(self._target, updated)

    @abstractmethod
    def load(self) -> AduibRpcConfig:
        """Load config and return (or update) AduibRpcConfig."""

    async def start(self) -> None:
        """Start dynamic updates (optional)."""

    async def stop(self) -> None:
        """Stop dynamic updates (optional)."""


def _normalize_config_root(data: Mapping[str, Any]) -> dict[str, Any]:
    if "aduib_rpc" not in data:
        return dict(data)
    nested = data["aduib_rpc"]
    if not isinstance(nested, Mapping):
        raise ConfigError("aduib_rpc section must be a mapping")
    merged = dict(nested)
    for key, value in data.items():
        if key == "aduib_rpc":
            continue
        merged[key] = value
    return merged


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ConfigError("Config content is empty")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml
            except Exception as exc:
                raise ConfigError("Config content must be JSON or YAML object") from exc
            parsed = yaml.safe_load(text)
        if isinstance(parsed, Mapping):
            return parsed
    raise ConfigError("Config content must be a mapping")


def _build_config_from_mapping(data: Mapping[str, Any]) -> AduibRpcConfig:
    normalized = _normalize_config_root(data)
    return AduibRpcConfig.from_dict(normalized)


class ConfigSourceProvider:
    """Config source provider for managing config loaders."""
    config_source_classes: dict[str, Any] = {}
    config_source_instances: dict[str, ConfigSourceLoader] = {}

    @classmethod
    def register_config_source_class(cls, source_type: str, source_class: Any) -> None:
        cls.config_source_classes[source_type] = source_class

    @classmethod
    def get_config_source_class(cls, source_type: str) -> Any | None:
        return cls.config_source_classes.get(source_type)

    @classmethod
    def from_config_source_instance(cls, source_type: str, **kwargs: Any) -> Any:
        source_class = cls.get_config_source_class(source_type)
        if source_class is None:
            logger.warning("No config source loader registered for %s", source_type)
            raise ValueError(f"No config source loader registered for {source_type}")
        if not issubclass(source_class, ConfigSourceLoader):
            raise TypeError("Config source loader must implement ConfigSourceLoader")
        instance = source_class(**kwargs)
        cls.config_source_instances[source_type] = instance
        return instance

    @classmethod
    def get_config_source_instance(cls, source_type: str) -> ConfigSourceLoader | None:
        return cls.config_source_instances.get(source_type)

    @classmethod
    async def load_config(
        cls, source_type: str, **kwargs: Any
    ) -> AduibRpcConfig | tuple[AduibRpcConfig, Any]:
        auto_start = bool(kwargs.pop("auto_start", True))
        instance = cls.get_config_source_instance(source_type)
        if instance is None:
            instance = cls.from_config_source_instance(source_type, **kwargs)
        else:
            target = kwargs.get("target")
            if target is not None:
                instance.set_target(target)
        loaded = instance.load()
        if auto_start:
            result = instance.start()
            if asyncio.iscoroutine(result):
                await result
        return loaded

    @classmethod
    async def stop_config(cls, source_type: str) -> None:
        instance = cls.get_config_source_instance(source_type)
        if instance is None:
            return
        result = instance.stop()
        if asyncio.iscoroutine(result):
            await result


@config_source_loader("file")
class FileConfigSourceLoader(ConfigSourceLoader):
    """Config source loader for local files."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        config_path: str | Path | None = None,
        poll_interval: float = 5.0,
        watch: bool = True,
        target: AduibRpcConfig | None = None,
        **_: Any,
    ) -> None:
        super().__init__(target=target)
        resolved = path or config_path
        if resolved is None:
            raise ValueError("file config loader requires 'path' or 'config_path'")
        self._path = resolved
        self._poll_interval = poll_interval
        self._watch = watch
        self._reloader: ConfigFileReloader | None = None

    def load(self) -> AduibRpcConfig:
        loaded = load_config(self._path)
        return self._update_target(loaded)

    async def start(self) -> None:
        if not self._watch:
            return
        if self._reloader is not None:
            return
        if self._target is None:
            self.load()
        if self._target is None:
            return
        self._reloader = await ConfigFileReloader.watch(
            path=self._path,
            target=self._target,
            poll_interval=self._poll_interval,
        )

    async def stop(self) -> None:
        if self._reloader is None:
            return
        await self._reloader.stop()
        self._reloader = None


@config_source_loader("nacos")
class NacosConfigSourceLoader(ConfigSourceLoader):
    """Config source loader for Nacos config service."""

    def __init__(
        self,
        *,
        server_addresses: str,
        namespace: str,
        username: str,
        password: str,
        data_id: str,
        group_name: str = "DEFAULT_GROUP",
        log_level: str = "INFO",
        watch: bool = True,
        target: AduibRpcConfig | None = None,
        **_: Any,
    ) -> None:
        super().__init__(target=target)
        try:
            from aduib_rpc.discover.registry.nacos import client as nacos_client
        except Exception as exc:
            raise RuntimeError("nacos config loader requires nacos SDK") from exc

        if getattr(nacos_client, "nacos", None) is None:
            raise RuntimeError("nacos config loader requires nacos-sdk-python")

        self._nacos_client = nacos_client.InnerNacosClient(
            server_addresses, namespace, username, password, group_name, log_level
        )
        self._data_id = data_id
        self._watch = watch
        self._listener_registered = False
        self._callback: Callable[[Any], None] | None = None

    def load(self) -> AduibRpcConfig:
        data = self._nacos_client.get_config_sync(self._data_id)
        if data is None:
            if self._target is not None:
                return self._target
            raise ConfigError(f"Nacos config not found for data_id={self._data_id}")
        mapping = _coerce_mapping(data)
        config = _build_config_from_mapping(mapping)
        return self._update_target(config)

    async def start(self) -> None:
        if not self._watch:
            return
        if self._listener_registered:
            return
        if self._target is None:
            self.load()
        if self._target is None:
            return

        def _on_change(payload: Any) -> None:
            try:
                mapping = _coerce_mapping(payload)
                config = _build_config_from_mapping(mapping)
                self._update_target(config)
            except Exception:
                logger.exception("Nacos config update failed for data_id=%s", self._data_id)

        self._callback = _on_change
        self._nacos_client.add_config_callback(self._data_id, _on_change)
        await self._nacos_client.register_config_listener(self._data_id)
        self._listener_registered = True

    async def stop(self) -> None:
        if not self._listener_registered:
            return

        # Best-effort unregister if underlying client supports it.
        service = getattr(self._nacos_client, "config_service", None)
        watcher = getattr(self._nacos_client, "config_watcher", None)
        if service is not None and watcher is not None:
            remove = getattr(service, "remove_listener", None)
            if callable(remove):
                try:
                    result = remove(
                        data_id=self._data_id,
                        group=self._nacos_client.group,
                        listener=watcher,
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Failed to remove Nacos config listener for data_id=%s", self._data_id)

        client = getattr(self._nacos_client, "client", None)
        if client is not None:
            remove_watch = getattr(client, "remove_config_watcher", None)
            if callable(remove_watch):
                try:
                    remove_watch(self._data_id, group=self._nacos_client.group)
                except Exception:
                    logger.exception("Failed to remove Nacos config watcher for data_id=%s", self._data_id)

        # Remove callback from local dispatch list to stop updates.
        if self._callback is not None:
            callbacks = self._nacos_client.config_callbacks.get(self._data_id, [])
            if self._callback in callbacks:
                callbacks.remove(self._callback)
            if not callbacks and self._data_id in self._nacos_client.config_callbacks:
                self._nacos_client.config_callbacks.pop(self._data_id, None)

        self._callback = None
        self._listener_registered = False


class ConfigUpdater:
    """Helpers for updating config objects in-place."""

    @staticmethod
    def _update_collection_in_place(target: Any, source: Any) -> bool:
        if isinstance(target, dict) and isinstance(source, dict):
            target.clear()
            target.update(source)
            return True
        if isinstance(target, set) and isinstance(source, set):
            target.clear()
            target.update(source)
            return True
        if isinstance(target, list) and isinstance(source, list):
            target.clear()
            target.extend(source)
            return True
        return False

    @staticmethod
    def _update_dataclass_in_place(target: Any, source: Any) -> None:
        for field in fields(target):
            name = field.name
            current = getattr(target, name)
            incoming = getattr(source, name)

            if is_dataclass(current) and is_dataclass(incoming):
                params = getattr(current, "__dataclass_params__", None)
                if params is not None and getattr(params, "frozen", False):
                    setattr(target, name, incoming)
                else:
                    ConfigUpdater._update_dataclass_in_place(current, incoming)
                continue

            if ConfigUpdater._update_collection_in_place(current, incoming):
                continue

            setattr(target, name, incoming)

    @staticmethod
    def update_in_place(target: AduibRpcConfig, updated: AduibRpcConfig) -> AduibRpcConfig:
        """Update a static config object in-place using another config."""
        ConfigUpdater._update_dataclass_in_place(target, updated)
        return target

    @staticmethod
    def load_into(path: str | Path, target: AduibRpcConfig) -> AduibRpcConfig:
        """Load config from file and update target in-place."""
        updated = load_config(path)
        return ConfigUpdater.update_in_place(target, updated)


class ConfigFileReloader:
    """Poll a config file and update an AduibRpcConfig in-place."""

    def __init__(
        self,
        *,
        path: str | Path,
        target: AduibRpcConfig,
        poll_interval: float = 5.0,
        on_update: ConfigUpdateCallback | None = None,
        on_error: ConfigErrorCallback | None = None,
    ) -> None:
        self._path = Path(path)
        self._target = target
        self._poll_interval = max(0.1, float(poll_interval))
        self._on_update = on_update
        self._on_error = on_error
        self._task: asyncio.Task[None] | None = None
        self._last_mtime: float | None = None
        self._lock = asyncio.Lock()

    async def start(self, *, initial_load: bool = True) -> None:
        if self._task and not self._task.done():
            return
        if initial_load:
            await self.refresh()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def refresh(self) -> AduibRpcConfig:
        async with self._lock:
            try:
                update = load_config(self._path)
            except Exception as exc:
                await self._notify_error(exc)
                if isinstance(exc, ConfigError):
                    return self._target
                return self._target

            ConfigUpdater.update_in_place(self._target, update)
            self._last_mtime = self._stat_mtime()
            await self._notify_update()
            return self._target

    async def _poll_loop(self) -> None:
        while True:
            try:
                mtime = self._stat_mtime()
                if mtime is not None and mtime != self._last_mtime:
                    await self.refresh()
            except Exception as exc:
                await self._notify_error(exc)
            await asyncio.sleep(self._poll_interval)

    def _stat_mtime(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except FileNotFoundError:
            return None

    async def _notify_update(self) -> None:
        if self._on_update is None:
            return
        result = self._on_update(self._target)
        if asyncio.iscoroutine(result):
            await result

    async def _notify_error(self, exc: Exception) -> None:
        if self._on_error is None:
            return
        result = self._on_error(exc)
        if asyncio.iscoroutine(result):
            await result

    @classmethod
    async def watch(
        cls,
        *,
        path: str | Path,
        target: AduibRpcConfig,
        poll_interval: float = 5.0,
        on_update: ConfigUpdateCallback | None = None,
        on_error: ConfigErrorCallback | None = None,
        initial_load: bool = True,
    ) -> "ConfigFileReloader":
        """Create and start a ConfigFileReloader."""
        reloader = cls(
            path=path,
            target=target,
            poll_interval=poll_interval,
            on_update=on_update,
            on_error=on_error,
        )
        await reloader.start(initial_load=initial_load)
        return reloader

