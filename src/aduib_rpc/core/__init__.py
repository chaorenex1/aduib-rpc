"""Core primitives for aduib_rpc.

Note: This module re-exports from aduib_rpc.server.rpc_execution.runtime for backward compatibility.
New code should import directly from aduib_rpc.server.rpc_execution.runtime.
"""

from aduib_rpc.server.rpc_execution.runtime import (
    ScopedRuntime,
    create_runtime,
    get_current_runtime,
    get_runtime,
    with_runtime,
    with_tenant,
)

__all__ = [
    "ScopedRuntime",
    "create_runtime",
    "get_current_runtime",
    "get_runtime",
    "with_runtime",
    "with_tenant",
]
