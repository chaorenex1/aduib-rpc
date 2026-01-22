"""Health check command for aduib-cli.

Provides health checking capabilities for RPC services via HTTP and gRPC protocols.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Final

__all__ = ["register_parser", "run"]

# Exit codes
EXIT_HEALTHY: Final = 0
EXIT_UNHEALTHY: Final = 1
EXIT_TIMEOUT: Final = 2
EXIT_ERROR: Final = 3


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the health command subparser.

    Args:
        subparsers: The argparse subparsers action to add to.
    """
    parser = subparsers.add_parser(
        "health",
        help="Run health checks for Aduib RPC services.",
        description="Check service health using HTTP or gRPC protocols.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  aduib-cli health localhost:8080
  aduib-cli health localhost:9090 --protocol grpc
  aduib-cli health example.com:443 --path /healthz --timeout 10
  aduib-cli health localhost:8080 --format json
        """,
    )
    parser.set_defaults(handler=run)
    parser.add_argument(
        "target",
        help="Service target in format 'host:port'.",
    )
    parser.add_argument(
        "--protocol",
        choices=["http", "grpc"],
        default="http",
        help="Health check protocol (default: http).",
    )
    parser.add_argument(
        "--path",
        default="/health",
        help="HTTP health check path (default: /health).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Request timeout in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification.",
    )
    parser.add_argument(
        "--headers",
        action="append",
        metavar="KEY=VALUE",
        help="Additional HTTP headers (can be repeated).",
    )


def run(args: argparse.Namespace) -> int:
    """Execute the health check command.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0=healthy, 1=unhealthy, 2=timeout, 3=error).
    """
    # Parse target
    try:
        host, port = _parse_target(args.target)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Parse headers
    headers = {}
    if args.headers:
        for header in args.headers:
            if "=" not in header:
                print(f"Error: Invalid header format '{header}'. Use KEY=VALUE.", file=sys.stderr)
                return EXIT_ERROR
            key, value = header.split("=", 1)
            headers[key.strip()] = value.strip()

    # Run health check
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            _check_health(
                host=host,
                port=port,
                protocol=args.protocol,
                path=args.path,
                timeout=args.timeout,
                insecure=args.insecure,
                headers=headers,
            )
        )
    except asyncio.TimeoutError:
        _print_result(args.format, {
            "status": "timeout",
            "message": f"Health check timed out after {args.timeout}s",
            "latency_ms": args.timeout * 1000,
        })
        return EXIT_TIMEOUT
    except Exception as e:
        _print_result(args.format, {
            "status": "error",
            "message": str(e),
            "latency_ms": 0,
        })
        return EXIT_ERROR
    finally:
        loop.close()

    # Print result and return exit code
    _print_result(args.format, result)

    if result["status"] == "healthy":
        return EXIT_HEALTHY
    elif result["status"] == "timeout":
        return EXIT_TIMEOUT
    return EXIT_UNHEALTHY


def _parse_target(target: str) -> tuple[str, int]:
    """Parse host:port target.

    Args:
        target: Target string in format 'host:port'.

    Returns:
        Tuple of (host, port).

    Raises:
        ValueError: If target format is invalid.
    """
    if ":" not in target:
        raise ValueError(f"Invalid target '{target}'. Expected format: 'host:port'")

    host, port_str = target.rsplit(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"Invalid port '{port_str}'. Port must be a number.")

    if not (1 <= port <= 65535):
        raise ValueError(f"Port must be between 1 and 65535, got {port}.")

    return host, port


async def _check_health(
    host: str,
    port: int,
    protocol: str,
    path: str,
    timeout: float,
    insecure: bool,
    headers: dict[str, str],
) -> dict:
    """Perform the actual health check.

    Args:
        host: Target hostname or IP.
        port: Target port.
        protocol: Protocol to use (http or grpc).
        path: HTTP health check path.
        timeout: Request timeout in seconds.
        insecure: Skip TLS verification.
        headers: Additional HTTP headers.

    Returns:
        Health check result dictionary.
    """
    start = time.monotonic()

    if protocol == "http":
        result = await _check_http(host, port, path, timeout, insecure, headers)
    else:
        result = await _check_grpc(host, port, timeout, insecure)

    latency_ms = (time.monotonic() - start) * 1000
    result["latency_ms"] = round(latency_ms, 2)
    return result


async def _check_http(
    host: str,
    port: int,
    path: str,
    timeout: float,
    insecure: bool,
    headers: dict[str, str],
) -> dict:
    """Check health via HTTP/HTTPS.

    Args:
        host: Target hostname.
        port: Target port.
        path: Health check endpoint path.
        timeout: Request timeout.
        insecure: Skip TLS verification.
        headers: Additional headers.

    Returns:
        Health check result dictionary.
    """
    try:
        import httpx
    except ImportError:
        return {
            "status": "error",
            "message": "httpx is required for HTTP health checks. Install with: pip install httpx",
        }

    # Determine scheme
    scheme = "https" if port == 443 else "http"
    url = f"{scheme}://{host}:{port}{path}"

    # Configure client
    verify = not insecure
    async with httpx.AsyncClient(verify=verify, timeout=timeout) as client:
        try:
            response = await client.get(url, headers=headers)
            body = response.text[:200] if response.text else ""

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "message": f"HTTP {response.status_code} OK",
                    "body_preview": body,
                }
            elif response.status_code >= 500:
                return {
                    "status": "unhealthy",
                    "message": f"HTTP {response.status_code} Server Error",
                    "body_preview": body,
                }
            elif response.status_code == 503:
                return {
                    "status": "unhealthy",
                    "message": "Service unavailable (HTTP 503)",
                    "body_preview": body,
                }
            else:
                return {
                    "status": "degraded",
                    "message": f"HTTP {response.status_code}",
                    "body_preview": body,
                }
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "message": f"Request timed out after {timeout}s",
            }
        except httpx.ConnectError as e:
            return {
                "status": "unhealthy",
                "message": f"Connection failed: {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }


async def _check_grpc(
    host: str,
    port: int,
    timeout: float,
    insecure: bool,
) -> dict:
    """Check health via gRPC.

    Args:
        host: Target hostname.
        port: Target port.
        timeout: Request timeout.
        insecure: Skip TLS verification.

    Returns:
        Health check result dictionary.
    """
    try:
        import grpc
        from grpc.health.v1 import health_pb2, health_pb2_grpc
    except ImportError:
        return {
            "status": "error",
            "message": "grpcio is required for gRPC health checks. Install with: pip install grpcio",
        }

    try:
        if insecure:
            channel = grpc.aio.insecure_channel(f"{host}:{port}")
        else:
            channel = grpc.aio.secure_channel(f"{host}:{port}", grpc.ssl_channel_credentials())

        stub = health_pb2_grpc.HealthStub(channel)
        response = await asyncio.wait_for(
            stub.Check(health_pb2.HealthCheckRequest(service="")),
            timeout=timeout,
        )

        await channel.close()

        if response.status == health_pb2.HealthCheckResponse.SERVING:
            return {
                "status": "healthy",
                "message": "gRPC health check: SERVING",
            }
        elif response.status == health_pb2.HealthCheckResponse.NOT_SERVING:
            return {
                "status": "unhealthy",
                "message": "gRPC health check: NOT_SERVING",
            }
        else:
            return {
                "status": "unknown",
                "message": f"gRPC health check: {response.status}",
            }

    except asyncio.TimeoutError:
        return {
            "status": "timeout",
            "message": f"gRPC request timed out after {timeout}s",
        }
    except grpc.aio.AioRpcError as e:
        return {
            "status": "unhealthy",
            "message": f"gRPC error: {e.code()} {e.details()}",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


def _print_result(format_type: str, result: dict) -> None:
    """Print health check result in specified format.

    Args:
        format_type: Output format ('text' or 'json').
        result: Health check result dictionary.
    """
    if format_type == "json":
        print(json.dumps(result, indent=2))
    else:
        status = result.get("status", "unknown")
        message = result.get("message", "")
        latency = result.get("latency_ms", 0)

        status_symbols = {
            "healthy": "✓",
            "unhealthy": "✗",
            "degraded": "⚠",
            "timeout": "⏱",
            "error": "!",
        }

        symbol = status_symbols.get(status, "?")
        print(f"{symbol} {status.upper()}: {message}")
        if latency > 0:
            print(f"  latency: {latency:.2f}ms")

        if "body_preview" in result:
            preview = result["body_preview"]
            if preview and len(preview) > 100:
                preview = preview[:100] + "..."
            if preview:
                print(f"  body: {preview}")
