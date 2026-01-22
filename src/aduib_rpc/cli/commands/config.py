"""Config command for aduib-cli.

Provides configuration validation and management capabilities.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

__all__ = ["register_parser", "run"]

EXIT_SUCCESS: Final = 0
EXIT_ERROR: Final = 1
EXIT_VALIDATION_FAILED: Final = 2


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the config command subparser.

    Args:
        subparsers: The argparse subparsers action to add to.
    """
    parser = subparsers.add_parser(
        "config",
        help="Inspect or validate Aduib RPC configuration.",
        description="Validate and manage Aduib RPC configuration files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aduib-cli config validate config.yaml
  aduib-cli config get aduib_rpc.runtime.max_connections
  aduib-cli config set aduib_rpc.runtime.timeout_ms 30000
  aduib-cli config validate config.yaml --dry-run
        """,
    )
    parser.set_defaults(handler=run)

    # Add subcommands for config
    config_subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 'validate' subcommand
    validate_parser = config_subparsers.add_parser(
        "validate",
        help="Validate a configuration file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate_parser.add_argument(
        "config_file",
        type=Path,
        help="Path to the configuration file to validate.",
    )
    validate_parser.add_argument(
        "--schema",
        choices=["yaml", "json"],
        default=None,
        help="Expected schema format (default: auto-detect).",
    )
    validate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse without loading actual values.",
    )
    validate_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed validation results.",
    )

    # 'get' subcommand
    get_parser = config_subparsers.add_parser(
        "get",
        help="Get a configuration value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_parser.add_argument(
        "key",
        help="Configuration key (e.g., 'aduib_rpc.runtime.timeout_ms').",
    )
    get_parser.add_argument(
        "--default",
        help="Default value if key is not found.",
    )
    get_parser.add_argument(
        "--format",
        choices=["raw", "json", "yaml"],
        default="raw",
        help="Output format (default: raw).",
    )
    get_parser.add_argument(
        "--config-file",
        type=Path,
        help="Path to configuration file (uses default if not specified).",
    )

    # 'set' subcommand
    set_parser = config_subparsers.add_parser(
        "set",
        help="Set a configuration value.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    set_parser.add_argument(
        "key",
        help="Configuration key to set.",
    )
    set_parser.add_argument(
        "value",
        help="Value to set (JSON format for complex values).",
    )
    set_parser.add_argument(
        "--config-file",
        type=Path,
        required=True,
        help="Path to configuration file to modify.",
    )
    set_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying.",
    )


def run(args: argparse.Namespace) -> int:
    """Execute the config command.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0=success, 1=error, 2=validation failed).
    """
    if args.subcommand == "validate":
        return _run_validate(args)
    elif args.subcommand == "get":
        return _run_get(args)
    elif args.subcommand == "set":
        return _run_set(args)
    else:
        print(f"Error: Unknown subcommand '{args.subcommand}'", file=sys.stderr)
        return EXIT_ERROR


def _run_validate(args: argparse.Namespace) -> int:
    """Execute 'config validate' subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    config_file: Path = args.config_file

    if not config_file.exists():
        print(f"Error: Configuration file not found: {config_file}", file=sys.stderr)
        return EXIT_ERROR

    # Determine file type
    if args.schema is None:
        suffix = config_file.suffix.lower()
        if suffix == ".yaml" or suffix == ".yml":
            file_type = "yaml"
        elif suffix == ".json":
            file_type = "json"
        else:
            print(f"Error: Cannot detect file type from extension: {suffix}", file=sys.stderr)
            return EXIT_ERROR
    else:
        file_type = args.schema

    # Parse and validate
    try:
        if file_type == "yaml":
            data = _load_yaml(config_file)
        else:
            data = _load_json(config_file)
    except Exception as e:
        print(f"Error: Failed to parse configuration file: {e}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    # Validate structure
    errors = _validate_config_structure(data)

    if errors:
        print(f"Validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        if args.verbose:
            print("\nParsed configuration:", file=sys.stderr)
            print(json.dumps(data, indent=2), file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    print(f"✓ Configuration file is valid: {config_file}")

    if args.verbose:
        print("\nConfiguration sections:")
        for key in sorted(data.keys()):
            print(f"  - {key}")

    return EXIT_SUCCESS


def _run_get(args: argparse.Namespace) -> int:
    """Execute 'config get' subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    # Load config
    config_file = getattr(args, "config_file", None)
    if config_file and config_file.exists():
        try:
            if config_file.suffix.lower() in [".yaml", ".yml"]:
                data = _load_yaml(config_file)
            else:
                data = _load_json(config_file)
        except Exception as e:
            print(f"Error: Failed to load configuration: {e}", file=sys.stderr)
            return EXIT_ERROR
    else:
        data = {}

    # Get value
    value = _get_nested_value(data, args.key)

    if value is None:
        if args.default is not None:
            value = args.default
        else:
            print(f"Error: Key '{args.key}' not found", file=sys.stderr)
            return EXIT_ERROR

    # Output result
    if args.format == "json":
        print(json.dumps(value, indent=2))
    elif args.format == "yaml":
        try:
            import yaml
            print(yaml.dump({args.key: value}, default_flow_style=False))
        except ImportError:
            print("Warning: PyYAML not installed. Using JSON format.", file=sys.stderr)
            print(json.dumps(value, indent=2))
    else:
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2))
        else:
            print(value)

    return EXIT_SUCCESS


def _run_set(args: argparse.Namespace) -> int:
    """Execute 'config set' subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    config_file: Path = args.config_file

    # Load existing config
    if config_file.exists():
        try:
            if config_file.suffix.lower() in [".yaml", ".yml"]:
                data = _load_yaml(config_file)
            else:
                data = _load_json(config_file)
        except Exception as e:
            print(f"Error: Failed to load existing configuration: {e}", file=sys.stderr)
            return EXIT_ERROR
    else:
        data = {}

    # Parse value
    try:
        new_value = json.loads(args.value)
    except json.JSONDecodeError:
        # Treat as string
        new_value = args.value

    # Show what would change
    old_value = _get_nested_value(data, args.key)
    print(f"Setting '{args.key}':")
    if old_value is not None:
        print(f"  old: {json.dumps(old_value)}")
    print(f"  new: {json.dumps(new_value)}")

    if args.dry_run:
        print("\n(Dry run - no changes made)")
        return EXIT_SUCCESS

    # Apply change
    _set_nested_value(data, args.key, new_value)

    # Save
    try:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        if config_file.suffix.lower() in [".yaml", ".yml"]:
            _save_yaml(config_file, data)
        else:
            _save_json(config_file, data)
        print(f"\n✓ Configuration saved to {config_file}")
    except Exception as e:
        print(f"Error: Failed to save configuration: {e}", file=sys.stderr)
        return EXIT_ERROR

    return EXIT_SUCCESS


def _load_yaml(path: Path) -> dict:
    """Load a YAML file.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed data as dictionary.
    """
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML is required to parse YAML files. Install with: pip install pyyaml")


def _save_yaml(path: Path, data: dict) -> None:
    """Save data to a YAML file.

    Args:
        path: Path to output file.
        data: Data to save.
    """
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    except ImportError:
        raise ImportError("PyYAML is required to write YAML files. Install with: pip install pyyaml")


def _load_json(path: Path) -> dict:
    """Load a JSON file.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed data as dictionary.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file.

    Args:
        path: Path to output file.
        data: Data to save.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_nested_value(data: dict, key: str):
    """Get a value from nested dictionary using dot notation.

    Args:
        data: Dictionary to search.
        key: Dot-separated key path.

    Returns:
        Value or None if not found.
    """
    parts = key.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current


def _set_nested_value(data: dict, key: str, value) -> None:
    """Set a value in nested dictionary using dot notation.

    Args:
        data: Dictionary to modify.
        key: Dot-separated key path.
        value: Value to set.
    """
    parts = key.split(".")
    current = data

    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


def _validate_config_structure(data: dict) -> list[str]:
    """Validate configuration structure.

    Args:
        data: Parsed configuration data.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors = []

    if not isinstance(data, dict):
        return ["Configuration must be a dictionary/object"]

    # Check for aduib_rpc section
    if "aduib_rpc" in data and not isinstance(data["aduib_rpc"], dict):
        errors.append("'aduib_rpc' section must be a dictionary/object")

    # Validate runtime section if present
    if "aduib_rpc" in data and "runtime" in data["aduib_rpc"]:
        runtime = data["aduib_rpc"]["runtime"]
        if not isinstance(runtime, dict):
            errors("'aduib_rpc.runtime' must be a dictionary/object")
        else:
            # Check timeout value
            if "timeout_ms" in runtime:
                timeout = runtime["timeout_ms"]
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    errors.append("'aduib_rpc.runtime.timeout_ms' must be a positive number")

            # Check max_connections value
            if "max_connections" in runtime:
                max_conn = runtime["max_connections"]
                if not isinstance(max_conn, int) or max_conn <= 0:
                    errors.append("'aduib_rpc.runtime.max_connections' must be a positive integer")

    return errors
