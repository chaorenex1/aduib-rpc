"""Server-side async task support (long-running jobs).

This module provides a transport-agnostic task manager that can be used by
request handlers to run long-running work in the background and allow clients
to poll or subscribe to progress/results.
"""

