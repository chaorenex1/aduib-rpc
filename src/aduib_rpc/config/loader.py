from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import AduibRpcConfig

class ConfigError(RuntimeError):
    """Raised when configuration loading fails."""


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def get_default_config_path() -> Path | None:
    """Return the first default config path that exists."""
    candidates = [
        Path.cwd() / "aduib_rpc.yaml",
        Path.cwd() / "aduib_rpc.yml",
        Path.home() / ".aduib_rpc.yaml",
        Path.home() / ".aduib_rpc.yml",
        Path("/etc/aduib_rpc/config.yaml"),
        Path("/etc/aduib_rpc/config.yml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            if candidate.is_file():
                return candidate
    return None

def load_default_config() -> AduibRpcConfig:
    """Load the default config file into AduibRpcConfig."""
    path = get_default_config_path()
    if path is None:
        raise ConfigError("No default config file found")
    return load_config(path)

def load_config(path: str | Path) -> AduibRpcConfig:
    """Load a YAML config file into AduibRpcConfig."""
    if not path:

        return load_default_config()
    data = _load_config_mapping(path)
    try:
        return AduibRpcConfig.from_dict(data)
    except ConfigError:
        # Re-raise ConfigError as-is to preserve error message
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Failed to build config from {path}") from exc


def load_config_with_overloads(
    base_path: str | Path, *overload_paths: str | Path
) -> AduibRpcConfig:
    """Load a base config file and apply one or more override files."""
    merged = _load_config_mapping(base_path)
    for overload in overload_paths:
        overlay = _load_config_mapping(overload)
        merged = _merge_mapping(merged, overlay)
    try:
        return AduibRpcConfig.from_dict(merged)
    except Exception as exc:  # pragma: no cover - defensive
        raise ConfigError("Failed to build config with overrides") from exc


def _load_config_mapping(path: str | Path) -> dict[str, Any]:
    config_path = _to_path(path)
    _ensure_yaml_path(config_path)
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    try:
        content = config_path.read_text(encoding="utf-8")
        data = _parse_yaml_with_env(content)
    except ConfigError:
        # Re-raise ConfigError as-is to preserve error message
        raise
    except Exception as exc:
        raise ConfigError(f"Failed to load config file: {config_path}") from exc
    if not isinstance(data, Mapping):
        raise ConfigError("Configuration must be a mapping")
    return _normalize_config_root(dict(data))


def _parse_yaml_with_env(content: str) -> Mapping[str, Any]:
    yaml = _get_yaml_module()
    parsed = yaml.safe_load(content) or {}
    if not isinstance(parsed, Mapping):
        raise ConfigError("Config file must parse to a mapping")
    expanded = _expand_env_in_data(parsed)
    return _coerce_env_list_values(expanded)


def _expand_env_in_data(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_env_value(value)
    if isinstance(value, Mapping):
        return {key: _expand_env_in_data(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_expand_env_in_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_expand_env_in_data(item) for item in value)
    return value


def _coerce_env_list_values(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            yaml = _get_yaml_module()
            parsed = yaml.safe_load(text)
            if isinstance(parsed, list):
                return parsed
        return value
    if isinstance(value, Mapping):
        return {key: _coerce_env_list_values(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_coerce_env_list_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_coerce_env_list_values(item) for item in value)
    return value


def _expand_env_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        default = match.group(2)
        env_value = os.getenv(name)
        if env_value is None or env_value == "":
            if default is None:
                raise ConfigError(
                    f"Environment variable '{name}' is not set and no default provided"
                )
            return default
        return env_value

    return _ENV_PATTERN.sub(replace, value)



def _merge_mapping(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _merge_mapping(merged[key], value)
        else:
            merged[key] = value
    return merged


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


def _ensure_yaml_path(path: Path) -> None:
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ConfigError(f"Unsupported config file type: {path.suffix}")


def _to_path(path: str | Path) -> Path:
    return Path(path).expanduser()


def _get_yaml_module() -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency error
        raise ConfigError("PyYAML is required to parse YAML config files.") from exc
    return yaml
