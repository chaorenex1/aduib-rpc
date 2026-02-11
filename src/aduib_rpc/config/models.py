from __future__ import annotations

from collections.abc import Mapping, Sequence, Callable
from dataclasses import dataclass, field
from pathlib import Path
import ssl
from typing import Any, TypeVar, cast

from aduib_rpc.client.config import ClientConfig as _ClientConfig
from aduib_rpc.discover.health.health_status import (
    HealthCheckConfig as _HealthCheckConfig,
)
from aduib_rpc.resilience import ResilienceConfig as _ResilienceConfig

from aduib_rpc.telemetry.config import TelemetryConfig
from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
from aduib_rpc.resilience.fallback import FallbackPolicy
from aduib_rpc.resilience.rate_limiter import RateLimitAlgorithm, RateLimiterConfig
from aduib_rpc.resilience.retry_policy import RetryPolicy, RetryStrategy
from aduib_rpc.security.mtls import ServerTlsConfig, TlsConfig, TlsVersion
from aduib_rpc.server.interceptors.security import (
    SecurityConfig as _ServerSecurityConfig,
)
from aduib_rpc.server.qos import QosConfig as _ServerQosConfig
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


FieldSpec = tuple[str, Callable[[Any, str], Any], str]


def _optional(coerce: Callable[[Any, str], Any]) -> Callable[[Any, str], Any]:
    def _wrapped(value: Any, field_name: str) -> Any:
        if value is None:
            return None
        return coerce(value, field_name)

    return _wrapped


def _enum_coerce(enum_cls: type[T]) -> Callable[[Any, str], Any]:
    def _wrapped(value: Any, field_name: str) -> Any:
        return _coerce_enum(value, enum_cls, field_name)

    return _wrapped


def _coerce_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, Sequence):
        return [_coerce_str(item, field_name) for item in value]
    raise TypeError(f"{field_name} must be a list of strings")


def _extract_fields(payload: Mapping[str, Any], specs: Sequence[FieldSpec]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for name, coerce, label in specs:
        if name in payload:
            kwargs[name] = coerce(payload[name], label)
    return kwargs


def _apply_field_specs(target: Any, specs: Sequence[FieldSpec]) -> None:
    for name, coerce, label in specs:
        setattr(target, name, coerce(getattr(target, name), label))


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

_CLIENT_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("pooling_enabled", _coerce_bool, "client.pooling_enabled"),
    ("supported_transports", _coerce_transport_list, "client.supported_transports"),
    ("http_timeout", _optional(_coerce_float), "client.http_timeout"),
    ("grpc_timeout", _optional(_coerce_float), "client.grpc_timeout"),
)


@dataclass
class ClientConfig(_ClientConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ClientConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ClientConfig) and not isinstance(data, cls):
            kwargs = {name: getattr(data, name) for name, _, _ in _CLIENT_FIELD_SPECS}
            kwargs["httpx_client"] = data.httpx_client
            kwargs["grpc_channel_factory"] = data.grpc_channel_factory
            return cls(**kwargs)
        payload = _ensure_mapping(data, "client")
        kwargs = _extract_fields(payload, _CLIENT_FIELD_SPECS)
        if "httpx_client" in payload:
            kwargs["httpx_client"] = payload["httpx_client"]
        if "grpc_channel_factory" in payload:
            kwargs["grpc_channel_factory"] = payload["grpc_channel_factory"]
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _CLIENT_FIELD_SPECS)
        if self.http_timeout is not None:
            if self.http_timeout < 0:
                raise ValueError("client.http_timeout must be >= 0")
        if self.grpc_timeout is not None:
            if self.grpc_timeout < 0:
                raise ValueError("client.grpc_timeout must be >= 0")


_MTLS_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("enabled", _coerce_bool, "security.mtls.enabled"),
    ("allowed_common_names", _coerce_str_set, "security.mtls.allowed_common_names"),
    ("allowed_san_dns", _coerce_str_set, "security.mtls.allowed_san_dns"),
    ("allowed_issuer_common_names", _coerce_str_set, "security.mtls.allowed_issuer_common_names"),
)


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
        kwargs = _extract_fields(payload, _MTLS_FIELD_SPECS)
        if "tls" in payload:
            kwargs["tls"] = ServerTlsSettings.from_dict(payload["tls"])
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _MTLS_FIELD_SPECS)
        if not isinstance(self.tls, ServerTlsSettings):
            self.tls = ServerTlsSettings.from_dict(self.tls)

    def to_server_tls_config(self) -> ServerTlsConfig | None:
        if self.tls is None:
            return None
        return self.tls.to_runtime_config()


_SERVER_TLS_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("server_cert_path", _optional(_coerce_path), "security.mtls.tls.server_cert_path"),
    ("server_key_path", _optional(_coerce_path), "security.mtls.tls.server_key_path"),
    ("server_key_password", _optional(_coerce_str), "security.mtls.tls.server_key_password"),
    ("ca_cert_path", _optional(_coerce_path), "security.mtls.tls.ca_cert_path"),
    ("client_cert_verification", _optional(_coerce_verify_mode), "security.mtls.tls.client_cert_verification"),
    ("minimum_version", _enum_coerce(TlsVersion), "security.mtls.tls.minimum_version"),
    ("maximum_version", _optional(_enum_coerce(TlsVersion)), "security.mtls.tls.maximum_version"),
    ("ciphers", _optional(_coerce_str), "security.mtls.tls.ciphers"),
)


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
        kwargs = _extract_fields(payload, _SERVER_TLS_FIELD_SPECS)
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _SERVER_TLS_FIELD_SPECS)

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


_SECURITY_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("rbac_enabled", _coerce_bool, "security.rbac_enabled"),
    ("audit_enabled", _coerce_bool, "security.audit_enabled"),
    ("default_role", _coerce_str, "security.default_role"),
    ("superadmin_role", _optional(_coerce_str), "security.superadmin_role"),
    ("require_auth", _coerce_bool, "security.require_auth"),
    ("anonymous_methods", _coerce_str_set, "security.anonymous_methods"),
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
            kwargs = {name: getattr(data, name) for name, _, _ in _SECURITY_FIELD_SPECS}
            if isinstance(kwargs.get("anonymous_methods"), set):
                kwargs["anonymous_methods"] = set(kwargs["anonymous_methods"])
            return cls(**kwargs)
        payload = _ensure_mapping(data, "security")
        kwargs = _extract_fields(payload, _SECURITY_FIELD_SPECS)
        if "rbac" in payload and "rbac_enabled" not in kwargs:
            kwargs["rbac_enabled"] = _coerce_bool(payload["rbac"], "security.rbac")
        if "audit" in payload and "audit_enabled" not in kwargs:
            kwargs["audit_enabled"] = _coerce_bool(payload["audit"], "security.audit")
        if "mtls" in payload:
            kwargs["mtls"] = MtlsConfig.from_dict(payload["mtls"])
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _SECURITY_FIELD_SPECS)
        if not isinstance(self.mtls, MtlsConfig):
            self.mtls = MtlsConfig.from_dict(self.mtls)  # type: ignore[arg-type]

_RESILIENCE_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("enabled", _coerce_bool, "resilience.enabled"),
    ("circuit_breaker", _build_circuit_breaker_config, "resilience.circuit_breaker"),
    ("rate_limiter", _build_rate_limiter_config, "resilience.rate_limiter"),
    ("retry", _build_retry_policy, "resilience.retry"),
    ("fallback", _build_fallback_policy, "resilience.fallback"),
)


class ResilienceConfig(_ResilienceConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "ResilienceConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ResilienceConfig) and not isinstance(data, cls):
            kwargs = {name: getattr(data, name) for name, _, _ in _RESILIENCE_FIELD_SPECS}
            return cls(**kwargs)
        payload = _ensure_mapping(data, "resilience")
        kwargs = _extract_fields(payload, _RESILIENCE_FIELD_SPECS)
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _RESILIENCE_FIELD_SPECS)

_HEALTH_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("interval_seconds", _coerce_float, "health_check.interval_seconds"),
    ("timeout_seconds", _coerce_float, "health_check.timeout_seconds"),
    ("healthy_threshold", _coerce_int, "health_check.healthy_threshold"),
    ("unhealthy_threshold", _coerce_int, "health_check.unhealthy_threshold"),
    ("path", _coerce_str, "health_check.path"),
)


@dataclass
class HealthCheckConfig(_HealthCheckConfig):
    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "HealthCheckConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _HealthCheckConfig) and not isinstance(data, cls):
            kwargs = {name: getattr(data, name) for name, _, _ in _HEALTH_FIELD_SPECS}
            return cls(**kwargs)
        payload = _ensure_mapping(data, "health_check")
        kwargs = _extract_fields(payload, _HEALTH_FIELD_SPECS)
        return cls(**kwargs)

    def __post_init__(self) -> None:
        _apply_field_specs(self, _HEALTH_FIELD_SPECS)
        if self.interval_seconds <= 0:
            raise ValueError("health_check.interval_seconds must be > 0")
        if self.timeout_seconds <= 0:
            raise ValueError("health_check.timeout_seconds must be > 0")
        if self.healthy_threshold < 1:
            raise ValueError("health_check.healthy_threshold must be >= 1")
        if self.unhealthy_threshold < 1:
            raise ValueError("health_check.unhealthy_threshold must be >= 1")

_PROTOCOL_FIELD_SPECS: tuple[FieldSpec, ...] = (
    ("protocol_versions", _coerce_str_list, "protocol.protocol_versions"),
    ("default_version", _coerce_str, "protocol.default_version"),
)


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
        return cls(**_extract_fields(payload, _PROTOCOL_FIELD_SPECS))

    def __post_init__(self) -> None:
        _apply_field_specs(self, _PROTOCOL_FIELD_SPECS)


_QOS_FIELD_SPECS: tuple[tuple[str, Callable[[Any, str], Any], str], ...] = (
    ("enabled", _coerce_bool, "qos.enabled"),
    ("priority", _coerce_int, "qos.priority"),
    ("timeout_ms", _coerce_int, "qos.timeout_ms"),
    ("idempotency_key", _coerce_str, "qos.idempotency_key"),
    ("idempotency_ttl_s", _coerce_int, "qos.idempotency_ttl_s"),
)


@dataclass
class QosConfig(_ServerQosConfig):

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "QosConfig":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        if isinstance(data, _ServerQosConfig) and not isinstance(data, cls):
            kwargs = {name: getattr(data, name) for name, _, _ in _QOS_FIELD_SPECS}
            if getattr(data, "retry", None) is not None:
                kwargs["retry"] = data.retry
            return cls(**kwargs)
        payload = _ensure_mapping(data, "qos")
        kwargs: dict[str, Any] = {}
        for name, coerce, label in _QOS_FIELD_SPECS:
            if name in payload:
                kwargs[name] = coerce(payload[name], label)
        if "retry" in payload:
            kwargs["retry"] = _build_retry_policy(
                payload["retry"], "qos.retry"
            )
        return cls(**kwargs)

    def __post_init__(self) -> None:
        for name, coerce, label in _QOS_FIELD_SPECS:
            setattr(self, name, coerce(getattr(self, name), label))
        if self.timeout_ms <= 0:
            raise ValueError("qos.timeout_ms must be > 0")
        if self.idempotency_ttl_s < 0:
            raise ValueError("qos.idempotency_ttl_s must be >= 0")
        if self.retry is not None and not isinstance(self.retry, RetryPolicy):
            self.retry = _build_retry_policy(self.retry, "qos.retry")




@dataclass
class AduibRpcConfig:
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    qos: QosConfig = field(default_factory=QosConfig)

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

