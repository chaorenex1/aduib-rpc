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
    for m in modules:
        if not m:
            continue
        logger.debug("Importing service module: %s", m)
        importlib.import_module(m)

