"""Service discovery command for aduib-cli.

Provides service discovery and instance listing capabilities.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Final

__all__ = ["register_parser", "run"]

EXIT_SUCCESS: Final = 0
EXIT_ERROR: Final = 1


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the discover command subparser.

    Args:
        subparsers: The argparse subparsers action to add to.
    """
    parser = subparsers.add_parser(
        "discover",
        help="Service discovery tooling.",
        description="Query service registry for registered services and instances.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aduib-cli discover services
  aduib-cli discover list my-service
  aduib-cli discover list my-service --format json
  aduib-cli discover list my-service --show-metadata
        """,
    )
    parser.set_defaults(handler=run)

    # Add subcommands for discover
    discover_subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 'list' subcommand
    list_parser = discover_subparsers.add_parser(
        "list",
        help="List service instances.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument(
        "service_name",
        help="Name of the service to query.",
    )
    list_parser.add_argument(
        "--registry",
        choices=["memory", "nacos", "multi"],
        default="memory",
        help="Registry type to query (default: memory).",
    )
    list_parser.add_argument(
        "--format",
        choices=["text", "json", "table"],
        default="text",
        help="Output format (default: text).",
    )
    list_parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="Include instance metadata in output.",
    )
    list_parser.add_argument(
        "--healthy-only",
        action="store_true",
        help="Show only healthy instances.",
    )

    # 'services' subcommand
    services_parser = discover_subparsers.add_parser(
        "services",
        help="List all registered services.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    services_parser.add_argument(
        "--registry",
        choices=["memory", "nacos", "multi"],
        default="memory",
        help="Registry type to query (default: memory).",
    )
    services_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )


def run(args: argparse.Namespace) -> int:
    """Execute the discover command.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0=success, 1=error).
    """
    if args.subcommand == "list":
        return _run_list(args)
    elif args.subcommand == "services":
        return _run_services(args)
    else:
        print(f"Error: Unknown subcommand '{args.subcommand}'", file=sys.stderr)
        return EXIT_ERROR


def _run_list(args: argparse.Namespace) -> int:
    """Execute 'discover list' subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    try:
        from aduib_rpc.discover.registry import ServiceRegistry
        from aduib_rpc.discover.entities import ServiceInstance
    except ImportError as e:
        print(f"Error: Failed to import discovery modules: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Get registry instance
    registry = _get_registry(args.registry)
    if registry is None:
        return EXIT_ERROR

    # List instances
    try:
        instances = registry.list_instances(args.service_name)
    except Exception as e:
        print(f"Error: Failed to list instances: {e}", file=sys.stderr)
        return EXIT_ERROR

    if not instances:
        if args.format == "json":
            print(json.dumps({"service": args.service_name, "instances": []}))
        else:
            print(f"No instances found for service '{args.service_name}'")
        return EXIT_SUCCESS

    # Filter by health if requested
    if args.healthy_only:
        instances = [i for i in instances if getattr(i, "healthy", True)]

    # Output results
    if args.format == "json":
        _print_instances_json(instances, args.show_metadata)
    elif args.format == "table":
        _print_instances_table(instances, args.show_metadata)
    else:
        _print_instances_text(instances, args.show_metadata)

    return EXIT_SUCCESS


def _run_services(args: argparse.Namespace) -> int:
    """Execute 'discover services' subcommand.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    try:
        from aduib_rpc.discover.registry import ServiceRegistry
    except ImportError as e:
        print(f"Error: Failed to import discovery modules: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Get registry instance
    registry = _get_registry(args.registry)
    if registry is None:
        return EXIT_ERROR

    # Get all services
    try:
        get_all = getattr(registry, "get_all_services", None)
        if get_all is None:
            print("Error: Registry does not support listing all services", file=sys.stderr)
            return EXIT_ERROR

        services = get_all()
    except Exception as e:
        print(f"Error: Failed to list services: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Output results
    if args.format == "json":
        print(json.dumps({"services": services}, indent=2))
    else:
        if services:
            print("Registered services:")
            for service in sorted(services):
                print(f"  - {service}")
        else:
            print("No services registered")

    return EXIT_SUCCESS


def _get_registry(registry_type: str) -> ServiceRegistry | None:
    """Get a registry instance by type.

    Args:
        registry_type: Type of registry to create.

    Returns:
        ServiceRegistry instance or None on error.
    """
    try:
        if registry_type == "memory":
            from aduib_rpc.discover.registry import InMemoryServiceRegistry
            return InMemoryServiceRegistry()
        elif registry_type == "nacos":
            from aduib_rpc.discover.registry import NacosServiceRegistry
            print("Warning: Nacos registry requires configuration. Using default values.", file=sys.stderr)
            return NacosServiceRegistry(
                server_addresses="localhost:8848",
                namespace="public",
            )
        elif registry_type == "multi":
            from aduib_rpc.discover.multi_registry import MultiRegistry, RegistryAdapter
            from aduib_rpc.discover.registry import InMemoryServiceRegistry
            return MultiRegistry([
                RegistryAdapter(name="memory", registry=InMemoryServiceRegistry()),
            ])
        else:
            print(f"Error: Unknown registry type '{registry_type}'", file=sys.stderr)
            return None
    except ImportError as e:
        print(f"Error: Registry type '{registry_type}' not available: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: Failed to create registry: {e}", file=sys.stderr)
        return None


def _print_instances_text(instances: list, show_metadata: bool) -> None:
    """Print instances in text format.

    Args:
        instances: List of service instances.
        show_metadata: Whether to include metadata.
    """
    for i, instance in enumerate(instances, 1):
        print(f"[{i}] {getattr(instance, 'host', 'N/A')}:{getattr(instance, 'port', 'N/A')}")
        print(f"    service: {getattr(instance, 'service_name', 'N/A')}")
        print(f"    weight: {getattr(instance, 'weight', 1)}")
        print(f"    protocol: {getattr(instance, 'protocol', 'N/A')}")
        print(f"    scheme: {getattr(instance, 'scheme', 'N/A')}")

        if show_metadata:
            metadata = getattr(instance, 'metadata', {})
            if metadata:
                print("    metadata:")
                for key, value in sorted(metadata.items()):
                    print(f"      {key}: {value}")


def _print_instances_table(instances: list, show_metadata: bool) -> None:
    """Print instances in table format.

    Args:
        instances: List of service instances.
        show_metadata: Whether to include metadata.
    """
    if not instances:
        return

    # Calculate column widths
    host_width = max(20, max(len(getattr(i, 'host', 'N/A')) for i in instances))
    port_width = 6
    weight_width = 6
    protocol_width = max(8, max(len(str(getattr(i, 'protocol', 'N/A'))) for i in instances))

    # Print header
    header = f"  {'HOST':<{host_width}}  {'PORT':<{port_width}}  {'WEIGHT':<{weight_width}}  {'PROTOCOL':<{protocol_width}}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    # Print rows
    for i, instance in enumerate(instances, 1):
        host = getattr(instance, 'host', 'N/A')
        port = getattr(instance, 'port', 'N/A')
        weight = getattr(instance, 'weight', 1)
        protocol = getattr(instance, 'protocol', 'N/A')

        print(f"{i:<2} {host:<{host_width}}  {str(port):<{port_width}}  {str(weight):<{weight_width}}  {str(protocol):<{protocol_width}}")

        if show_metadata:
            metadata = getattr(instance, 'metadata', {})
            if metadata:
                print(f"    metadata: {json.dumps(metadata)}")


def _print_instances_json(instances: list, show_metadata: bool) -> None:
    """Print instances in JSON format.

    Args:
        instances: List of service instances.
        show_metadata: Whether to include metadata.
    """
    output = []

    for instance in instances:
        data = {
            "host": getattr(instance, 'host', None),
            "port": getattr(instance, 'port', None),
            "service_name": getattr(instance, 'service_name', None),
            "weight": getattr(instance, 'weight', 1),
            "protocol": str(getattr(instance, 'protocol', None)),
            "scheme": str(getattr(instance, 'scheme', None)),
        }

        if show_metadata:
            data["metadata"] = getattr(instance, 'metadata', {})

        output.append(data)

    print(json.dumps(output, indent=2))
