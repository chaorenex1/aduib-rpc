from __future__ import annotations

import argparse
import importlib
import logging
from collections.abc import Callable, Sequence

SubparsersAction = argparse._SubParsersAction  # Runtime-safe alias for type hints
CommandRegistrar = Callable[[SubparsersAction], None]

_COMMAND_MODULES: dict[str, str] = {
    "health": "aduib_rpc.cli.commands.health",
    "discover": "aduib_rpc.cli.commands.discover",
    "config": "aduib_rpc.cli.commands.config",
    "version": "aduib_rpc.cli.commands.version",
}


def _load_registrar(module_path: str) -> CommandRegistrar:
    module = importlib.import_module(module_path)
    registrar = getattr(module, "register_parser", None)
    if not callable(registrar):
        raise ValueError(
            f"Command module '{module_path}' must expose a callable 'register_parser'"
        )
    return registrar


def _configure_logging(verbose: bool, quiet: bool) -> None:
    level = logging.INFO
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aduib-rpc", description="Command line interface for Aduib RPC"
    )

    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging output.",
    )
    log_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress info logs; show warnings and errors only.",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to a configuration file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    for module_path in _COMMAND_MODULES.values():
        _load_registrar(module_path)(subparsers)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(
        verbose=bool(getattr(args, "verbose", False)),
        quiet=bool(getattr(args, "quiet", False)),
    )
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    result = handler(args)
    return int(result) if isinstance(result, int) else 0


__all__ = ["build_parser", "main"]
