from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Iterable, Mapping


class Cache(ABC):
    """Abstract cache interface."""

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any:
        """Return cached value or default if missing/expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        """Set a value with optional TTL in seconds."""

    @abstractmethod
    async def add(self, key: str, value: Any, ttl_s: float | None = None) -> bool:
        """Set value only if key does not exist. Returns True if set."""

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if deleted."""

    @abstractmethod
    async def clear(self) -> None:
        """Remove all entries."""

    @abstractmethod
    async def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        """Get multiple keys."""

    @abstractmethod
    async def set_many(self, items: Mapping[str, Any], ttl_s: float | None = None) -> None:
        """Set multiple keys."""

    @abstractmethod
    async def delete_many(self, keys: Iterable[str]) -> int:
        """Delete multiple keys. Returns count deleted."""

    @abstractmethod
    async def contains(self, key: str) -> bool:
        """Return True if key exists and not expired."""

    @abstractmethod
    async def ttl(self, key: str) -> float | None:
        """Return remaining TTL in seconds, -1 for no expiry, None if missing."""

    @abstractmethod
    async def incr(self, key: str, delta: int = 1, ttl_s: float | None = None) -> int:
        """Increment numeric value and return new value."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""


class InMemoryCache(Cache):
    """In-memory cache with optional TTL support."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            value = self._get_unlocked(key, default)
            return value

    async def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        expires_at = self._expires_at(ttl_s)
        async with self._lock:
            self._store[str(key)] = (value, expires_at)

    async def add(self, key: str, value: Any, ttl_s: float | None = None) -> bool:
        expires_at = self._expires_at(ttl_s)
        async with self._lock:
            if self._exists_unlocked(key):
                return False
            self._store[str(key)] = (value, expires_at)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._store.pop(str(key), None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        async with self._lock:
            result: dict[str, Any] = {}
            for key in keys:
                value = self._get_unlocked(key, default=None)
                if value is not None or self._exists_unlocked(key):
                    result[str(key)] = value
            return result

    async def set_many(self, items: Mapping[str, Any], ttl_s: float | None = None) -> None:
        expires_at = self._expires_at(ttl_s)
        async with self._lock:
            for key, value in items.items():
                self._store[str(key)] = (value, expires_at)

    async def delete_many(self, keys: Iterable[str]) -> int:
        async with self._lock:
            count = 0
            for key in keys:
                if self._store.pop(str(key), None) is not None:
                    count += 1
            return count

    async def contains(self, key: str) -> bool:
        async with self._lock:
            return self._exists_unlocked(key)

    async def ttl(self, key: str) -> float | None:
        async with self._lock:
            key = str(key)
            if key not in self._store:
                return None
            _, expires_at = self._store.get(key, (None, None))
            if expires_at is None:
                return -1
            remaining = expires_at - self._now()
            if remaining <= 0:
                self._store.pop(key, None)
                return None
            return remaining

    async def incr(self, key: str, delta: int = 1, ttl_s: float | None = None) -> int:
        async with self._lock:
            key = str(key)
            if not self._exists_unlocked(key):
                value = 0
                expires_at = self._expires_at(ttl_s)
            else:
                value, expires_at = self._store.get(key, (0, None))
                if not isinstance(value, int):
                    raise ValueError("cached value is not an int")
            value = int(value) + int(delta)
            if ttl_s is not None:
                expires_at = self._expires_at(ttl_s)
            self._store[key] = (value, expires_at)
            return value

    async def close(self) -> None:
        await self.clear()

    def _now(self) -> float:
        return time.monotonic()

    def _expires_at(self, ttl_s: float | None) -> float | None:
        if ttl_s is None:
            return None
        ttl = float(ttl_s)
        if ttl <= 0:
            return self._now()
        return self._now() + ttl

    def _exists_unlocked(self, key: str) -> bool:
        key = str(key)
        if key not in self._store:
            return False
        _, expires_at = self._store.get(key, (None, None))
        if expires_at is None:
            return True
        if expires_at <= self._now():
            self._store.pop(key, None)
            return False
        return True

    def _get_unlocked(self, key: str, default: Any) -> Any:
        key = str(key)
        if key not in self._store:
            return default
        value, expires_at = self._store.get(key, (default, None))
        if expires_at is not None and expires_at <= self._now():
            self._store.pop(key, None)
            return default
        return value


class InMemoryIdempotencyCache(Cache):
    """In-memory LRU cache for idempotent request responses."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._max_size = max(1, int(max_size))
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._lock: asyncio.Lock = asyncio.Lock()

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return default
            if entry.expires_at is not None and entry.expires_at <= time.time():
                self._cache.pop(key, None)
                return default
            self._cache.move_to_end(key)
            return entry.response

    async def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        async with self._lock:
            expires_at = self._expires_at(ttl_s)
            if len(self._cache) >= self._max_size and key not in self._cache:
                self._cache.popitem(last=False)
            self._cache[str(key)] = _CacheEntry(response=value, expires_at=expires_at)

    async def add(self, key: str, value: Any, ttl_s: float | None = None) -> bool:
        async with self._lock:
            if self._exists_unlocked(key):
                return False
            expires_at = self._expires_at(ttl_s)
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[str(key)] = _CacheEntry(response=value, expires_at=expires_at)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._cache.pop(str(key), None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        async with self._lock:
            result: dict[str, Any] = {}
            for key in keys:
                value = self._get_unlocked(key, default=None)
                if value is not None or self._exists_unlocked(key):
                    result[str(key)] = value
            return result

    async def set_many(self, items: Mapping[str, Any], ttl_s: float | None = None) -> None:
        async with self._lock:
            for key, value in items.items():
                expires_at = self._expires_at(ttl_s)
                if len(self._cache) >= self._max_size and key not in self._cache:
                    self._cache.popitem(last=False)
                self._cache[str(key)] = _CacheEntry(response=value, expires_at=expires_at)

    async def delete_many(self, keys: Iterable[str]) -> int:
        async with self._lock:
            count = 0
            for key in keys:
                if self._cache.pop(str(key), None) is not None:
                    count += 1
            return count

    async def contains(self, key: str) -> bool:
        async with self._lock:
            return self._exists_unlocked(key)

    async def ttl(self, key: str) -> float | None:
        async with self._lock:
            key = str(key)
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at is None:
                return -1
            remaining = entry.expires_at - time.time()
            if remaining <= 0:
                self._cache.pop(key, None)
                return None
            return remaining

    async def incr(self, key: str, delta: int = 1, ttl_s: float | None = None) -> int:
        async with self._lock:
            key = str(key)
            if not self._exists_unlocked(key):
                value = 0
                expires_at = self._expires_at(ttl_s)
            else:
                entry = self._cache.get(key)
                value = entry.response if entry is not None else 0
                expires_at = entry.expires_at if entry is not None else None
                if not isinstance(value, int):
                    raise ValueError("cached value is not an int")
                if ttl_s is not None:
                    expires_at = self._expires_at(ttl_s)
            value = int(value) + int(delta)
            self._cache[key] = _CacheEntry(response=value, expires_at=expires_at)
            self._cache.move_to_end(key)
            return value

    async def close(self) -> None:
        await self.clear()

    def _expires_at(self, ttl_s: float | None) -> float | None:
        if ttl_s is None:
            return time.time() + self._ttl_seconds
        ttl = float(ttl_s)
        if ttl <= 0:
            return time.time()
        return time.time() + ttl

    def _exists_unlocked(self, key: str) -> bool:
        key = str(key)
        entry = self._cache.get(key)
        if entry is None:
            return False
        if entry.expires_at is None:
            return True
        if entry.expires_at <= time.time():
            self._cache.pop(key, None)
            return False
        return True

    def _get_unlocked(self, key: str, default: Any) -> Any:
        key = str(key)
        entry = self._cache.get(key)
        if entry is None:
            return default
        if entry.expires_at is not None and entry.expires_at <= time.time():
            self._cache.pop(key, None)
            return default
        self._cache.move_to_end(key)
        return entry.response


class _CacheEntry:
    def __init__(self, response: Any, expires_at: float | None):
        self.response = response
        self.expires_at = expires_at
