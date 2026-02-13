"""Utilities for loading @service-decorated modules.

Why this exists
- Services are registered into RpcRuntime/_SERVICE_CATALOG at *import time* via
  the `@service("...")` decorator.
- An application entry point often wants to take a list of module paths and
  import them, so all decorators run and services become available.

This helper keeps that logic in one place.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def import_service_modules(modules: Iterable[str]) -> None:
    """Import modules so @service decorators execute.

    Args:
        modules: e.g. ["my_app.services.user", "my_app.services.order"]
    """
    for package_name in modules:
        if not package_name:
            continue
        try:
            package = importlib.import_module(package_name)
        except Exception:
            logger.exception("Failed to import package %s", package_name)
            return

        package_path = getattr(package, "__path__", None)
        if not package_path:
            return

        import pkgutil
        for _, module_name, _ in pkgutil.iter_modules(package_path):
            full_module_name = f"{package_name}.{module_name}"
            try:
                importlib.import_module(full_module_name)
            except Exception:
                logger.exception("Failed to import plugin module %s", full_module_name)
