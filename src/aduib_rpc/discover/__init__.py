"""Service discovery module with health checking support.

This module provides:
- Service registration and discovery
- Health checking of service instances
- Multi-registry support
- Load balancing
- v2 protocol entities

Example:
    from aduib_rpc.discover import InMemoryRegistry, HttpHealthChecker, HealthAwareRegistry
    from aduib_rpc.discover.entities import ServiceInstance

    # Create a registry
    registry = InMemoryRegistry()

    # Add health checking
    checker = HttpHealthChecker(HealthCheckConfig(interval_seconds=10))
    health_aware_registry = HealthAwareRegistry(registry, checker, config)

    # Register an instance
    instance = ServiceInstance.create(service_name="my-service", host="localhost", port=8080)
    await registry.register(instance)

    # Get healthy instances
    healthy = await health_aware_registry.list_healthy_instances("my-service")
"""

from __future__ import annotations

# v1 compatibility entities
from aduib_rpc.discover.entities.service_instance import ServiceInstance as V1ServiceInstance
from aduib_rpc.discover.health import (
    HealthCheckConfig,
    HealthChecker,
    DefaultHealthChecker,
    HealthStatus,
)
from aduib_rpc.discover.health.health_status import (
    HealthCheckResult,
)
from aduib_rpc.discover.registry.in_memory import InMemoryServiceRegistry
from aduib_rpc.discover.registry.service_registry import ServiceRegistry

# v2 protocol entities
from aduib_rpc.discover.entities.service_instance import (
    HealthStatus as V2HealthStatus,
    MethodDescriptor,
    ServiceCapabilities,
    ServiceInstance as V2ServiceInstance,
)

# For backwards compatibility, export V1ServiceInstance as ServiceInstance
ServiceInstance = V1ServiceInstance

__all__ = [
    # v1 Core entities (default for compatibility)
    "ServiceInstance",
    "V1ServiceInstance",
    "ServiceRegistry",
    # v2 entities
    "V2ServiceInstance",
    "ServiceCapabilities",
    "MethodDescriptor",
    "V2HealthStatus",
    # In-memory registry
    "InMemoryServiceRegistry",
    # Health checking
    "HealthChecker",
    "DefaultHealthChecker",
    "HealthCheckConfig",
    "HealthCheckResult",
    "HealthStatus",
]
