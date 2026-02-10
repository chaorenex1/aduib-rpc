from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
import ssl
from typing import Any, TypeVar, cast

from aduib_rpc.client.config import ClientConfig as _ClientConfig
from aduib_rpc.client.interceptors.resilience import (
    ResilienceConfig as _ClientResilienceConfig,
)
from aduib_rpc.discover.health.health_status import (
    HealthCheckConfig as _HealthCheckConfig,
)

from aduib_rpc.telemetry.config import TelemetryConfig
from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
from aduib_rpc.resilience.fallback import FallbackPolicy
from aduib_rpc.resilience.rate_limiter import RateLimitAlgorithm, RateLimiterConfig
from aduib_rpc.resilience.retry_policy import RetryPolicy, RetryStrategy
from aduib_rpc.security.mtls import ServerTlsConfig, TlsConfig, TlsVersion
from aduib_rpc.server.interceptors.security import (
    SecurityConfig as _ServerSecurityConfig,
)
from aduib_rpc.utils.constant import TransportSchemes

T = TypeVar("T")


def _ensure_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return cast(Mapping[str, Any], value)


def _coerce_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise TypeError(f"{field_name} must be a bool")


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError(f"{field_name} must be an int")


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a float")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise TypeError(f"{field_name} must be a float")


def _coerce_str(value: Any, field_name: str) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_enum(value: Any, enum_cls: type[T], field_name: str) -> T:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        try:
            return enum_cls(normalized)  # type: ignore[misc]
        except Exception:
            upper = normalized.upper()
            for member in enum_cls:  # type: ignore[call-arg]
                if getattr(member, "name", "").upper() == upper:
                    return member
                if str(getattr(member, "value", "")).upper() == upper:
                    return member
    raise ValueError(f"{field_name} must be a valid {enum_cls.__name__}")


def _coerce_transport(value: Any, field_name: str) -> TransportSchemes:
    if isinstance(value, TransportSchemes):
        return value
    if isinstance(value, str):
        return TransportSchemes.to_original(value.strip().lower())
    raise TypeError(f"{field_name} must be a transport scheme")


def _coerce_transport_list(value: Any, field_name: str) -> list[TransportSchemes]:
    if value is None:
        return []
    if isinstance(value, (str, TransportSchemes)):
        return [_coerce_transport(value, field_name)]
    if isinstance(value, Sequence):
        return [_coerce_transport(item, field_name) for item in value]
    raise TypeError(f"{field_name} must be a list of transport schemes")


def _coerce_str_set(value: Any, field_name: str) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return set(items)
    if isinstance(value, set):
        return {_coerce_str(item, field_name) for item in value}
    if isinstance(value, Sequence):
        return {_coerce_str(item, field_name) for item in value}
    raise TypeError(f"{field_name} must be a list of strings")


def _coerce_verify_mode(value: Any, field_name: str) -> ssl.VerifyMode:
    if isinstance(value, ssl.VerifyMode):
        return value
    if isinstance(value, int):
        return ssl.VerifyMode(value)
    if isinstance(value, str):
        normalized = value.strip().upper()
        mapping = {
            "CERT_NONE": ssl.CERT_NONE,
            "CERT_OPTIONAL": ssl.CERT_OPTIONAL,
            "CERT_REQUIRED": ssl.CERT_REQUIRED,
        }
        if normalized in mapping:
            return ssl.VerifyMode(mapping[normalized])
        try:
            return ssl.VerifyMode(int(normalized))
        except Exception as exc:
            raise TypeError(f"{field_name} must be a valid verify mode") from exc
    raise TypeError(f"{field_name} must be a valid verify mode")


def _coerce_path(value: Any, field_name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"{field_name} must be a path")


def _build_circuit_breaker_config(value: Any, field_name: str) -> CircuitBreakerConfig | None:
    if value is None:
        return None
    if isinstance(value, CircuitBreakerConfig):
        return value
    data = _ensure_mapping(value, field_name)
    payload = dict(data)
    if "excluded_exceptions" in payload:
        exclusions = payload["excluded_exceptions"]
        if exclusions is None:
            payload["excluded_exceptions"] = ()
        elif isinstance(exclusions, Sequence):
            payload["excluded_exceptions"] = tuple(exclusions)
        else:
            raise TypeError(f"{field_name}.excluded_exceptions must be a sequence")
    return CircuitBreakerConfig(**payload)


def _build_rate_limiter_config(value: Any, field_name: str) -> RateLimiterConfig | None:
    if value is None:
        return None
    if isinstance(value, RateLimiterConfig):
        return value
    data = _ensure_mapping(value, field_name)
    payload = dict(data)
    if "algorithm" in payload:
        payload["algorithm"] = _coerce_enum(
            payload["algorithm"], RateLimitAlgorithm, f"{field_name}.algorithm"
        )
    return RateLimiterConfig(**payload)


def _build_retry_policy(value: Any, field_name: str) -> RetryPolicy | None:
    if value is None:
        return None
    if isinstance(value, RetryPolicy):
        return value
    data = _ensure_mapping(value, field_name)
    payload = dict(data)
    if "strategy" in payload:
        payload["strategy"] = _coerce_enum(
            payload["strategy"], RetryStrategy, f"{field_name}.strategy"
        )
    if "retryable_codes" in payload and payload["retryable_codes"] is not None:
        codes = payload["retryable_codes"]
        if isinstance(codes, (set, list, tuple)):
            payload["retryable_codes"] = set(int(code) for code in codes)
        else:
            payload["retryable_codes"] = {int(codes)}
    return RetryPolicy(**payload)


def _build_fallback_policy(value: Any, field_name: str) -> FallbackPolicy | None:
    if value is None:
        return None
    if isinstance(value, FallbackPolicy):
        return value
    data = _ensure_mapping(value, field_name)
    payload = dict(data)
    if "handlers" in payload and payload["handlers"] is not None:
        handlers = payload["handlers"]
        if isinstance(handlers, Sequence):
            payload["handlers"] = tuple(handlers)
        else:
            payload["handlers"] = (handlers,)
    return FallbackPolicy(**payload)


def _build_tls_config(value: Any, field_name: str) -> TlsConfig | None:
    if value is None:
        return None
    if isinstance(value, TlsConfig):
        return value
    data = _ensure_mapping(value, field_name)
    payload = dict(data)
    if "ca_cert_path" in payload:
        payload["ca_cert_path"] = _coerce_path(payload["ca_cert_path"], f"{field_name}.ca_cert_path")
    if "client_cert_path" in payload:
        payload["client_cert_path"] = _coerce_path(payload["client_cert_path"], f"{field_name}.client_cert_path")
    if "client_key_path" in payload:
        payload["client_key_path"] = _coerce_path(payload["client_key_path"], f"{field_name}.client_key_path")
    if "minimum_version" in payload:
        payload["minimum_version"] = _coerce_enum(
            payload["minimum_version"], TlsVersion, f"{field_name}.minimum_version"
        )
    if "maximum_version" in payload and payload["maximum_version"] is not None:
        payload["maximum_version"] = _coerce_enum(
            payload["maximum_version"], TlsVersion, f"{field_name}.maximum_version"
        )
    return TlsConfig(**payload)


# Note: ObservabilityConfig replaced by TelemetryConfig
# Old LoggingConfig and MetricsConfig are deprecated - use TelemetryConfig instead
LOG_FORMAT_JSON = "json"
LOG_FORMAT_CONSOLE = "console"
LEVEL_NAME_TO_INT = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@dataclass
class ClientConfig(_ClientConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ClientConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ClientConfig) and not isinstance(data, cls):
            return cls(
                streaming=data.streaming,
                httpx_client=data.httpx_client,
                grpc_channel_factory=data.grpc_channel_factory,
                supported_transports=list(data.supported_transports),
                pooling_enabled=data.pooling_enabled,
                http_timeout=data.http_timeout,
                grpc_timeout=data.grpc_timeout,
                retry_enabled=data.retry_enabled,
                retry_max_attempts=data.retry_max_attempts,
                retry_backoff_ms=data.retry_backoff_ms,
                retry_max_backoff_ms=data.retry_max_backoff_ms,
                retry_jitter=data.retry_jitter,
            )
        payload = _ensure_mapping(data, "client")
        kwargs: dict[str, Any] = {}
        if "streaming" in payload:
            kwargs["streaming"] = _coerce_bool(payload["streaming"], "client.streaming")
        if "httpx_client" in payload:
            kwargs["httpx_client"] = payload["httpx_client"]
        if "grpc_channel_factory" in payload:
            kwargs["grpc_channel_factory"] = payload["grpc_channel_factory"]
        if "supported_transports" in payload:
            kwargs["supported_transports"] = _coerce_transport_list(
                payload["supported_transports"], "client.supported_transports"
            )
        if "pooling_enabled" in payload:
            kwargs["pooling_enabled"] = _coerce_bool(payload["pooling_enabled"], "client.pooling_enabled")
        if "http_timeout" in payload:
            kwargs["http_timeout"] = None if payload["http_timeout"] is None else _coerce_float(
                payload["http_timeout"], "client.http_timeout"
            )
        if "grpc_timeout" in payload:
            kwargs["grpc_timeout"] = None if payload["grpc_timeout"] is None else _coerce_float(
                payload["grpc_timeout"], "client.grpc_timeout"
            )
        if "retry_enabled" in payload:
            kwargs["retry_enabled"] = _coerce_bool(payload["retry_enabled"], "client.retry_enabled")
        if "retry_max_attempts" in payload:
            kwargs["retry_max_attempts"] = _coerce_int(payload["retry_max_attempts"], "client.retry_max_attempts")
        if "retry_backoff_ms" in payload:
            kwargs["retry_backoff_ms"] = _coerce_int(payload["retry_backoff_ms"], "client.retry_backoff_ms")
        if "retry_max_backoff_ms" in payload:
            kwargs["retry_max_backoff_ms"] = _coerce_int(
                payload["retry_max_backoff_ms"], "client.retry_max_backoff_ms"
            )
        if "retry_jitter" in payload:
            kwargs["retry_jitter"] = _coerce_float(payload["retry_jitter"], "client.retry_jitter")
        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.pooling_enabled = _coerce_bool(self.pooling_enabled, "client.pooling_enabled")
        self.supported_transports = _coerce_transport_list(
            self.supported_transports, "client.supported_transports"
        )
        if self.http_timeout is not None:
            self.http_timeout = _coerce_float(self.http_timeout, "client.http_timeout")
            if self.http_timeout < 0:
                raise ValueError("client.http_timeout must be >= 0")
        if self.grpc_timeout is not None:
            self.grpc_timeout = _coerce_float(self.grpc_timeout, "client.grpc_timeout")
            if self.grpc_timeout < 0:
                raise ValueError("client.grpc_timeout must be >= 0")
        self.retry_enabled = _coerce_bool(self.retry_enabled, "client.retry_enabled")
        self.retry_max_attempts = _coerce_int(self.retry_max_attempts, "client.retry_max_attempts")
        if self.retry_max_attempts < 1:
            raise ValueError("client.retry_max_attempts must be >= 1")
        self.retry_backoff_ms = _coerce_int(self.retry_backoff_ms, "client.retry_backoff_ms")
        if self.retry_backoff_ms < 0:
            raise ValueError("client.retry_backoff_ms must be >= 0")
        self.retry_max_backoff_ms = _coerce_int(
            self.retry_max_backoff_ms, "client.retry_max_backoff_ms"
        )
        if self.retry_max_backoff_ms < self.retry_backoff_ms:
            raise ValueError("client.retry_max_backoff_ms must be >= retry_backoff_ms")
        self.retry_jitter = _coerce_float(self.retry_jitter, "client.retry_jitter")
        if not 0.0 <= self.retry_jitter <= 1.0:
            raise ValueError("client.retry_jitter must be between 0 and 1")


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 50051
    scheme: TransportSchemes = TransportSchemes.GRPC
    enable_legacy_jsonrpc_methods: bool = False
    enable_thrift: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ServerConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        payload = _ensure_mapping(data, "server")
        kwargs: dict[str, Any] = {}
        if "host" in payload:
            kwargs["host"] = _coerce_str(payload["host"], "server.host")
        if "port" in payload:
            kwargs["port"] = _coerce_int(payload["port"], "server.port")
        if "scheme" in payload:
            kwargs["scheme"] = _coerce_transport(payload["scheme"], "server.scheme")
        if "enable_legacy_jsonrpc_methods" in payload:
            kwargs["enable_legacy_jsonrpc_methods"] = _coerce_bool(
                payload["enable_legacy_jsonrpc_methods"], "server.enable_legacy_jsonrpc_methods"
            )
        if "enable_thrift" in payload:
            kwargs["enable_thrift"] = _coerce_bool(
                payload["enable_thrift"], "server.enable_thrift"
            )

        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.host = _coerce_str(self.host, "server.host")
        self.port = _coerce_int(self.port, "server.port")
        if not 0 <= self.port <= 65535:
            raise ValueError("server.port must be between 0 and 65535")
        self.scheme = _coerce_transport(self.scheme, "server.scheme")


@dataclass
class MtlsConfig:
    enabled: bool = False
    tls: "ServerTlsSettings | None" = None
    allowed_common_names: set[str] = field(default_factory=set)
    allowed_san_dns: set[str] = field(default_factory=set)
    allowed_issuer_common_names: set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "MtlsConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, bool):
            return cls(enabled=data)
        payload = _ensure_mapping(data, "security.mtls")
        kwargs: dict[str, Any] = {}
        if "enabled" in payload:
            kwargs["enabled"] = _coerce_bool(payload["enabled"], "security.mtls.enabled")
        if "tls" in payload:
            kwargs["tls"] = ServerTlsSettings.from_dict(payload["tls"])
        if "allowed_common_names" in payload:
            kwargs["allowed_common_names"] = _coerce_str_set(
                payload["allowed_common_names"], "security.mtls.allowed_common_names"
            )
        if "allowed_san_dns" in payload:
            kwargs["allowed_san_dns"] = _coerce_str_set(
                payload["allowed_san_dns"], "security.mtls.allowed_san_dns"
            )
        if "allowed_issuer_common_names" in payload:
            kwargs["allowed_issuer_common_names"] = _coerce_str_set(
                payload["allowed_issuer_common_names"],
                "security.mtls.allowed_issuer_common_names",
            )
        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.enabled = _coerce_bool(self.enabled, "security.mtls.enabled")
        if not isinstance(self.tls, ServerTlsSettings):
            self.tls = ServerTlsSettings.from_dict(self.tls)
        self.allowed_common_names = _coerce_str_set(
            self.allowed_common_names, "security.mtls.allowed_common_names"
        )
        self.allowed_san_dns = _coerce_str_set(
            self.allowed_san_dns, "security.mtls.allowed_san_dns"
        )
        self.allowed_issuer_common_names = _coerce_str_set(
            self.allowed_issuer_common_names, "security.mtls.allowed_issuer_common_names"
        )

    def to_server_tls_config(self) -> ServerTlsConfig | None:
        if self.tls is None:
            return None
        return self.tls.to_runtime_config()


@dataclass
class ServerTlsSettings:
    server_cert_path: Path | None = None
    server_key_path: Path | None = None
    server_key_password: str | None = None
    ca_cert_path: Path | None = None
    client_cert_verification: ssl.VerifyMode | None = None
    minimum_version: TlsVersion = TlsVersion.TLSv1_2
    maximum_version: TlsVersion | None = None
    ciphers: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ServerTlsSettings":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        payload = _ensure_mapping(data, "security.mtls.tls")
        kwargs: dict[str, Any] = {}
        if "server_cert_path" in payload:
            kwargs["server_cert_path"] = _coerce_path(
                payload["server_cert_path"], "security.mtls.tls.server_cert_path"
            )
        if "server_key_path" in payload:
            kwargs["server_key_path"] = _coerce_path(
                payload["server_key_path"], "security.mtls.tls.server_key_path"
            )
        if "server_key_password" in payload:
            value = payload["server_key_password"]
            kwargs["server_key_password"] = None if value is None else _coerce_str(
                value, "security.mtls.tls.server_key_password"
            )
        if "ca_cert_path" in payload:
            kwargs["ca_cert_path"] = _coerce_path(
                payload["ca_cert_path"], "security.mtls.tls.ca_cert_path"
            )
        if "client_cert_verification" in payload:
            kwargs["client_cert_verification"] = _coerce_verify_mode(
                payload["client_cert_verification"], "security.mtls.tls.client_cert_verification"
            )
        if "minimum_version" in payload:
            kwargs["minimum_version"] = _coerce_enum(
                payload["minimum_version"], TlsVersion, "security.mtls.tls.minimum_version"
            )
        if "maximum_version" in payload and payload["maximum_version"] is not None:
            kwargs["maximum_version"] = _coerce_enum(
                payload["maximum_version"], TlsVersion, "security.mtls.tls.maximum_version"
            )
        if "ciphers" in payload:
            value = payload["ciphers"]
            kwargs["ciphers"] = None if value is None else _coerce_str(
                value, "security.mtls.tls.ciphers"
            )
        return cls(**kwargs)

    def __post_init__(self) -> None:
        if self.server_cert_path is not None:
            self.server_cert_path = _coerce_path(
                self.server_cert_path, "security.mtls.tls.server_cert_path"
            )
        if self.server_key_path is not None:
            self.server_key_path = _coerce_path(
                self.server_key_path, "security.mtls.tls.server_key_path"
            )
        if self.ca_cert_path is not None:
            self.ca_cert_path = _coerce_path(
                self.ca_cert_path, "security.mtls.tls.ca_cert_path"
            )
        if self.client_cert_verification is not None and not isinstance(
            self.client_cert_verification, ssl.VerifyMode
        ):
            self.client_cert_verification = _coerce_verify_mode(
                self.client_cert_verification, "security.mtls.tls.client_cert_verification"
            )
        self.minimum_version = _coerce_enum(
            self.minimum_version, TlsVersion, "security.mtls.tls.minimum_version"
        )
        if self.maximum_version is not None:
            self.maximum_version = _coerce_enum(
                self.maximum_version, TlsVersion, "security.mtls.tls.maximum_version"
            )
        if self.server_key_password is not None:
            self.server_key_password = _coerce_str(
                self.server_key_password, "security.mtls.tls.server_key_password"
            )
        if self.ciphers is not None:
            self.ciphers = _coerce_str(self.ciphers, "security.mtls.tls.ciphers")

    def to_runtime_config(self) -> ServerTlsConfig | None:
        if self.server_cert_path is None and self.server_key_path is None:
            return None
        if self.server_cert_path is None or self.server_key_path is None:
            raise ValueError("Both server_cert_path and server_key_path are required for server TLS")
        return ServerTlsConfig(
            server_cert_path=self.server_cert_path,
            server_key_path=self.server_key_path,
            server_key_password=self.server_key_password,
            ca_cert_path=self.ca_cert_path,
            client_cert_verification=self.client_cert_verification or ssl.CERT_NONE,
            minimum_version=self.minimum_version,
            maximum_version=self.maximum_version,
            ciphers=self.ciphers,
        )


@dataclass
class SecurityConfig(_ServerSecurityConfig):
    mtls: MtlsConfig = field(default_factory=MtlsConfig)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SecurityConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ServerSecurityConfig) and not isinstance(data, cls):
            return cls(
                rbac_enabled=data.rbac_enabled,
                audit_enabled=data.audit_enabled,
                default_role=data.default_role,
                superadmin_role=data.superadmin_role,
                require_auth=data.require_auth,
                anonymous_methods=set(data.anonymous_methods),
            )
        payload = _ensure_mapping(data, "security")
        kwargs: dict[str, Any] = {}
        if "rbac_enabled" in payload:
            kwargs["rbac_enabled"] = _coerce_bool(payload["rbac_enabled"], "security.rbac_enabled")
        if "audit_enabled" in payload:
            kwargs["audit_enabled"] = _coerce_bool(payload["audit_enabled"], "security.audit_enabled")
        if "default_role" in payload:
            kwargs["default_role"] = _coerce_str(payload["default_role"], "security.default_role")
        if "superadmin_role" in payload:
            value = payload["superadmin_role"]
            kwargs["superadmin_role"] = None if value is None else _coerce_str(value, "security.superadmin_role")
        if "require_auth" in payload:
            kwargs["require_auth"] = _coerce_bool(payload["require_auth"], "security.require_auth")
        if "anonymous_methods" in payload:
            kwargs["anonymous_methods"] = _coerce_str_set(
                payload["anonymous_methods"], "security.anonymous_methods"
            )
        if "rbac" in payload and "rbac_enabled" not in kwargs:
            kwargs["rbac_enabled"] = _coerce_bool(payload["rbac"], "security.rbac")
        if "audit" in payload and "audit_enabled" not in kwargs:
            kwargs["audit_enabled"] = _coerce_bool(payload["audit"], "security.audit")
        if "mtls" in payload:
            kwargs["mtls"] = MtlsConfig.from_dict(payload["mtls"])
        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.rbac_enabled = _coerce_bool(self.rbac_enabled, "security.rbac_enabled")
        self.audit_enabled = _coerce_bool(self.audit_enabled, "security.audit_enabled")
        self.default_role = _coerce_str(self.default_role, "security.default_role")
        if self.superadmin_role is not None:
            self.superadmin_role = _coerce_str(self.superadmin_role, "security.superadmin_role")
        self.require_auth = _coerce_bool(self.require_auth, "security.require_auth")
        self.anonymous_methods = _coerce_str_set(
            self.anonymous_methods, "security.anonymous_methods"
        )
        if not isinstance(self.mtls, MtlsConfig):
            self.mtls = MtlsConfig.from_dict(self.mtls)  # type: ignore[arg-type]


@dataclass
class ResilienceConfig(_ClientResilienceConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ResilienceConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ClientResilienceConfig) and not isinstance(data, cls):
            return cls(
                circuit_breaker=data.circuit_breaker,
                rate_limiter=data.rate_limiter,
                retry=data.retry,
                fallback=data.fallback,
                enabled=data.enabled,
                service_overrides=dict(data.service_overrides),
            )
        payload = _ensure_mapping(data, "resilience")
        kwargs: dict[str, Any] = {}
        if "circuit_breaker" in payload:
            kwargs["circuit_breaker"] = _build_circuit_breaker_config(
                payload["circuit_breaker"], "resilience.circuit_breaker"
            )
        if "rate_limiter" in payload:
            kwargs["rate_limiter"] = _build_rate_limiter_config(
                payload["rate_limiter"], "resilience.rate_limiter"
            )
        if "retry" in payload:
            kwargs["retry"] = _build_retry_policy(payload["retry"], "resilience.retry")
        if "fallback" in payload:
            kwargs["fallback"] = _build_fallback_policy(payload["fallback"], "resilience.fallback")
        if "enabled" in payload:
            kwargs["enabled"] = _coerce_bool(payload["enabled"], "resilience.enabled")
        if "service_overrides" in payload:
            overrides = payload["service_overrides"]
            if overrides is None:
                kwargs["service_overrides"] = {}
            else:
                kwargs["service_overrides"] = dict(_ensure_mapping(overrides, "resilience.service_overrides"))
        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.enabled = _coerce_bool(self.enabled, "resilience.enabled")
        if not isinstance(self.circuit_breaker, CircuitBreakerConfig):
            self.circuit_breaker = _build_circuit_breaker_config(
                self.circuit_breaker, "resilience.circuit_breaker"
            )
        if not isinstance(self.rate_limiter, RateLimiterConfig):
            self.rate_limiter = _build_rate_limiter_config(
                self.rate_limiter, "resilience.rate_limiter"
            )
        if not isinstance(self.retry, RetryPolicy):
            self.retry = _build_retry_policy(self.retry, "resilience.retry")
        if not isinstance(self.fallback, FallbackPolicy):
            self.fallback = _build_fallback_policy(self.fallback, "resilience.fallback")
        if self.service_overrides is None:
            self.service_overrides = {}
        if not isinstance(self.service_overrides, Mapping):
            raise TypeError("resilience.service_overrides must be a mapping")
        for key, value in self.service_overrides.items():
            if not isinstance(key, str):
                raise TypeError("resilience.service_overrides keys must be strings")
            if not isinstance(value, Mapping):
                raise TypeError("resilience.service_overrides values must be mappings")


@dataclass
class HealthCheckConfig(_HealthCheckConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "HealthCheckConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _HealthCheckConfig) and not isinstance(data, cls):
            return cls(
                interval_seconds=data.interval_seconds,
                timeout_seconds=data.timeout_seconds,
                healthy_threshold=data.healthy_threshold,
                unhealthy_threshold=data.unhealthy_threshold,
                path=data.path,
            )
        payload = _ensure_mapping(data, "health_check")
        kwargs: dict[str, Any] = {}
        if "interval_seconds" in payload:
            kwargs["interval_seconds"] = _coerce_float(
                payload["interval_seconds"], "health_check.interval_seconds"
            )
        if "timeout_seconds" in payload:
            kwargs["timeout_seconds"] = _coerce_float(
                payload["timeout_seconds"], "health_check.timeout_seconds"
            )
        if "healthy_threshold" in payload:
            kwargs["healthy_threshold"] = _coerce_int(
                payload["healthy_threshold"], "health_check.healthy_threshold"
            )
        if "unhealthy_threshold" in payload:
            kwargs["unhealthy_threshold"] = _coerce_int(
                payload["unhealthy_threshold"], "health_check.unhealthy_threshold"
            )
        if "path" in payload:
            kwargs["path"] = _coerce_str(payload["path"], "health_check.path")
        return cls(**kwargs)

    def __post_init__(self) -> None:
        self.interval_seconds = _coerce_float(
            self.interval_seconds, "health_check.interval_seconds"
        )
        self.timeout_seconds = _coerce_float(
            self.timeout_seconds, "health_check.timeout_seconds"
        )
        self.healthy_threshold = _coerce_int(
            self.healthy_threshold, "health_check.healthy_threshold"
        )
        self.unhealthy_threshold = _coerce_int(
            self.unhealthy_threshold, "health_check.unhealthy_threshold"
        )
        self.path = _coerce_str(self.path, "health_check.path")
        if self.interval_seconds <= 0:
            raise ValueError("health_check.interval_seconds must be > 0")
        if self.timeout_seconds <= 0:
            raise ValueError("health_check.timeout_seconds must be > 0")
        if self.healthy_threshold < 1:
            raise ValueError("health_check.healthy_threshold must be >= 1")
        if self.unhealthy_threshold < 1:
            raise ValueError("health_check.unhealthy_threshold must be >= 1")

@dataclass
class ProtocolConfig:
    protocol_versions: list[str] = field(default_factory=lambda: ["1.0", "2.0"])
    default_version: str = "2.0"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ProtocolConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        payload = _ensure_mapping(data, "protocol")
        kwargs: dict[str, Any] = {}
        if "protocol_versions" in payload:
            versions = payload["protocol_versions"]
            if isinstance(versions, Sequence):
                kwargs["protocol_versions"] = [_coerce_str(v, "protocol.protocol_versions") for v in versions]
            else:
                raise TypeError("protocol.protocol_versions must be a list of strings")
        if "default_version" in payload:
            kwargs["default_version"] = _coerce_str(payload["default_version"], "protocol.default_version")
        return cls(**kwargs)




@dataclass
class AduibRpcConfig:
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "AduibRpcConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        payload = _ensure_mapping(data, "config")
        kwargs: dict[str, Any] = {}
        if "protocol" in payload:
            kwargs["protocol"] = ProtocolConfig.from_dict(payload["protocol"])
        if "client" in payload:
            kwargs["client"] = ClientConfig.from_dict(payload["client"])
        if "server" in payload:
            kwargs["server"] = ServerConfig.from_dict(payload["server"])
        if "resilience" in payload:
            kwargs["resilience"] = ResilienceConfig.from_dict(payload["resilience"])
        if "security" in payload:
            kwargs["security"] = SecurityConfig.from_dict(payload["security"])
        # Handle both "telemetry" (new) and "observability" (legacy) keys
        if "telemetry" in payload:
            kwargs["telemetry"] = _parse_telemetry_config(payload["telemetry"])
        if "observability" in payload:
            # Map legacy observability config to TelemetryConfig
            kwargs["telemetry"] = _map_observability_to_telemetry(payload["observability"])
        if "health_check" in payload:
            kwargs["health_check"] = HealthCheckConfig.from_dict(payload["health_check"])
        return cls(**kwargs)

    def __post_init__(self) -> None:
        if not isinstance(self.client, ClientConfig):
            self.client = ClientConfig.from_dict(self.client)  # type: ignore[arg-type]
        if not isinstance(self.server, ServerConfig):
            self.server = ServerConfig.from_dict(self.server)  # type: ignore[arg-type]
        if not isinstance(self.resilience, ResilienceConfig):
            self.resilience = ResilienceConfig.from_dict(self.resilience)  # type: ignore[arg-type]
        if not isinstance(self.security, SecurityConfig):
            self.security = SecurityConfig.from_dict(self.security)  # type: ignore[arg-type]
        # TelemetryConfig is frozen, so we recreate if needed
        if not isinstance(self.telemetry, TelemetryConfig):
            self.telemetry = _parse_telemetry_config(self.telemetry)  # type: ignore[arg-type]
        if not isinstance(self.health_check, HealthCheckConfig):
            self.health_check = HealthCheckConfig.from_dict(self.health_check)  # type: ignore[arg-type]


def _parse_telemetry_config(data: Any) -> TelemetryConfig:
    """Parse telemetry config from various input formats."""
    if isinstance(data, TelemetryConfig):
        return data
    if isinstance(data, bool):
        return TelemetryConfig(enabled=data)
    # For dict-like input, create basic config (TelemetryConfig is frozen)
    return TelemetryConfig(enabled=True)


def _map_observability_to_telemetry(data: Any) -> TelemetryConfig:
    """Map legacy ObservabilityConfig to TelemetryConfig."""
    if isinstance(data, bool):
        return TelemetryConfig(enabled=data)
    # Basic mapping - TelemetryConfig is frozen so we use defaults
    return TelemetryConfig(enabled=True)

