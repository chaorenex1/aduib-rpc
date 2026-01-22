from __future__ import annotations

import argparse
import importlib.metadata

__all__ = ["register_parser", "run"]


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "version",
        help="Show the Aduib RPC package version.",
    )
    parser.set_defaults(handler=run)


def run(_: argparse.Namespace) -> int:
    try:
        version = importlib.metadata.version("aduib-rpc")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    print(version)
    return 0
