from __future__ import annotations

import json
import logging
import ssl

import pytest

from aduib_rpc.config.dynamic import DynamicConfig, InMemoryConfigSource
from aduib_rpc.discover.entities.service_instance import ServiceInstance
from aduib_rpc.discover.multi_registry import MultiRegistry, RegistryAdapter
from aduib_rpc.security.audit import AuditEvent, AuditLogger
from aduib_rpc.security.mtls import TlsConfig, TlsVersion, create_ssl_context
from aduib_rpc.security.rbac import InMemoryPermissionChecker, Permission, Role, Subject


class _StaticRegistry:
    def __init__(self, instances: list[ServiceInstance]) -> None:
        self._instances = list(instances)

    def list_instances(self, service_name: str) -> list[ServiceInstance]:
        return list(self._instances)


@pytest.fixture()
def tls_config() -> TlsConfig:
    return TlsConfig()


@pytest.fixture()
def in_memory_source() -> InMemoryConfigSource:
    return InMemoryConfigSource()


@pytest.fixture()
def dynamic_config(in_memory_source: InMemoryConfigSource) -> DynamicConfig:
    return DynamicConfig([in_memory_source])


@pytest.fixture()
def service_instances() -> tuple[ServiceInstance, ServiceInstance]:
    instance_a = ServiceInstance(service_name="svc", host="127.0.0.1", port=8001)
    instance_b = ServiceInstance(service_name="svc", host="127.0.0.1", port=8002)
    return instance_a, instance_b


class TestSecurityMtls:
    @pytest.mark.asyncio
    async def test_tls_version_enum(self) -> None:
        assert {member.name: member.value for member in TlsVersion} == {
            "TLSv1_2": "TLSv1.2",
            "TLSv1_3": "TLSv1.3",
        }

    @pytest.mark.asyncio
    async def test_tls_config_defaults(self, tls_config: TlsConfig) -> None:
        assert tls_config.ca_cert_path is None
        assert tls_config.client_cert_path is None
        assert tls_config.client_key_path is None
        assert tls_config.client_key_password is None
        assert tls_config.minimum_version is TlsVersion.TLSv1_2
        assert tls_config.maximum_version is None
        assert tls_config.check_hostname is True
        assert tls_config.verify_mode is ssl.CERT_REQUIRED
        assert tls_config.ciphers is None

    @pytest.mark.asyncio
    async def test_create_ssl_context_basic(self, tls_config: TlsConfig) -> None:
        context = create_ssl_context(tls_config)

        assert isinstance(context, ssl.SSLContext)
        assert context.minimum_version is ssl.TLSVersion.TLSv1_2
        assert context.verify_mode is ssl.CERT_REQUIRED
        assert context.check_hostname is True


class TestSecurityRbac:
    @pytest.mark.asyncio
    async def test_permission_creation(self) -> None:
        permission = Permission(resource="svc", action="read")

        assert permission.resource == "svc"
        assert permission.action == "read"

    @pytest.mark.asyncio
    async def test_role_with_permissions(self) -> None:
        read = Permission(resource="svc", action="read")
        write = Permission(resource="svc", action="write")
        role = Role(name="admin", permissions={read, write})

        assert isinstance(role.permissions, frozenset)
        assert role.permissions == frozenset({read, write})

    @pytest.mark.asyncio
    async def test_in_memory_checker_has_permission(self) -> None:
        read = Permission(resource="svc", action="read")
        write = Permission(resource="svc", action="write")
        role = Role(name="reader", permissions={read})
        checker = InMemoryPermissionChecker([role])
        subject = Subject(id="u1", type="user", roles={"reader"})

        assert checker.has_permission(subject, read) is True
        assert checker.has_permission(subject, write) is False

    @pytest.mark.asyncio
    async def test_subject_with_multiple_roles(self) -> None:
        read = Permission(resource="svc", action="read")
        write = Permission(resource="svc", action="write")
        reader = Role(name="reader", permissions={read})
        writer = Role(name="writer", permissions={write})
        checker = InMemoryPermissionChecker([reader, writer])
        subject = Subject(id="u1", type="user", roles={"reader", "writer"})

        assert isinstance(subject.roles, frozenset)
        assert checker.has_permission(subject, read) is True
        assert checker.has_permission(subject, write) is True


class TestSecurityAudit:
    @pytest.mark.asyncio
    async def test_audit_event_creation(self) -> None:
        event = AuditEvent(
            action="login",
            resource="console",
            subject_id="user-1",
            subject_type="user",
            status="success",
            metadata={"ip": "127.0.0.1"},
        )

        assert event.action == "login"
        assert event.resource == "console"
        assert event.subject_id == "user-1"
        assert event.subject_type == "user"
        assert event.status == "success"
        assert event.timestamp_ms > 0
        assert event.event_id
        assert event.to_dict()["metadata"] == {"ip": "127.0.0.1"}

    @pytest.mark.asyncio
    async def test_audit_logger_log_event(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("aduib_rpc.audit.test")
        audit_logger = AuditLogger(logger)
        event = AuditEvent(action="create", resource="svc")

        with caplog.at_level(logging.INFO, logger="aduib_rpc.audit.test"):
            payload = audit_logger.log_event(event)

        logged = [record.message for record in caplog.records if record.name == logger.name]
        assert payload in logged
        assert json.loads(payload)["event_id"] == event.event_id


class TestMultiRegistry:
    @pytest.mark.asyncio
    async def test_registry_adapter_creation(self) -> None:
        registry = _StaticRegistry([])
        adapter = RegistryAdapter(name="primary", registry=registry, priority=5, enabled=False)

        assert adapter.name == "primary"
        assert adapter.registry is registry
        assert adapter.priority == 5
        assert adapter.enabled is False

    @pytest.mark.asyncio
    async def test_multi_registry_aggregates_instances(
        self,
        service_instances: tuple[ServiceInstance, ServiceInstance],
    ) -> None:
        instance_a, instance_b = service_instances
        primary = _StaticRegistry([instance_a])
        secondary = _StaticRegistry([instance_a, instance_b])
        registry = MultiRegistry(
            [
                RegistryAdapter(name="primary", registry=primary, priority=1),
                RegistryAdapter(name="secondary", registry=secondary, priority=0),
            ]
        )

        instances = await registry.list_instances("svc")

        assert [instance.instance_id for instance in instances] == [
            instance_a.instance_id,
            instance_b.instance_id,
        ]

    @pytest.mark.asyncio
    async def test_multi_registry_priority_order(
        self,
        service_instances: tuple[ServiceInstance, ServiceInstance],
    ) -> None:
        instance_a, instance_b = service_instances
        high = _StaticRegistry([instance_a])
        low = _StaticRegistry([instance_b])
        registry = MultiRegistry(
            [
                RegistryAdapter(name="low", registry=low, priority=1),
                RegistryAdapter(name="high", registry=high, priority=10),
            ]
        )

        instances = await registry.list_instances("svc")

        assert [instance.instance_id for instance in instances] == [
            instance_a.instance_id,
            instance_b.instance_id,
        ]


class TestDynamicConfig:
    @pytest.mark.asyncio
    async def test_in_memory_source_get_set(self, in_memory_source: InMemoryConfigSource) -> None:
        await in_memory_source.set("feature.enabled", "true")
        assert await in_memory_source.get("feature.enabled") == "true"

        await in_memory_source.set("feature.enabled", None)
        assert await in_memory_source.get("feature.enabled") is None

    @pytest.mark.asyncio
    async def test_in_memory_source_watch_callback(
        self,
        in_memory_source: InMemoryConfigSource,
    ) -> None:
        seen: list[tuple[str, str | None]] = []

        async def _callback(key: str, value: str | None) -> None:
            seen.append((key, value))

        await in_memory_source.watch("app.", _callback)
        await in_memory_source.set("app.timeout", "30")

        assert seen == [("app.timeout", "30")]

    @pytest.mark.asyncio
    async def test_dynamic_config_get_int_bool_float(
        self,
        in_memory_source: InMemoryConfigSource,
        dynamic_config: DynamicConfig,
    ) -> None:
        await in_memory_source.set("app.timeout", "15")
        await in_memory_source.set("feature.enabled", "true")
        await in_memory_source.set("metrics.rate", "0.75")
        await in_memory_source.set("bad.number", "nope")

        assert await dynamic_config.get_int("app.timeout", default=1) == 15
        assert await dynamic_config.get_bool("feature.enabled", default=False) is True
        assert await dynamic_config.get_float("metrics.rate", default=0.0) == pytest.approx(0.75)
        assert await dynamic_config.get_int("bad.number", default=3) == 3

    @pytest.mark.asyncio
    async def test_dynamic_config_subscribe(
        self,
        in_memory_source: InMemoryConfigSource,
        dynamic_config: DynamicConfig,
    ) -> None:
        seen: list[tuple[str, str | None]] = []

        async def _callback(key: str, value: str | None) -> None:
            seen.append((key, value))

        unsubscribe = await dynamic_config.subscribe("feature.flag", _callback)
        await in_memory_source.set("feature.flag", "on")
        unsubscribe()
        await in_memory_source.set("feature.flag", "off")

        assert seen == [("feature.flag", "on")]
