import asyncio
import contextlib
import socket
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from aduib_rpc.client.client_factory import AduibRpcClientFactory
from aduib_rpc.client.errors import ClientHTTPError
from aduib_rpc.discover.entities import HealthStatus, ServiceCapabilities, ServiceInstance
from aduib_rpc.protocol.v2 import AduibRpcRequest
from aduib_rpc.protocol.v2.errors import ErrorCode
from aduib_rpc.protocol.v2.health import HealthCheckRequest, HealthStatus as HealthCheckStatus
from aduib_rpc.protocol.v2.metadata import AuthContext, AuthScheme, RequestMetadata
from aduib_rpc.protocol.v2.qos import QosConfig
from aduib_rpc.resilience.cache import InMemoryIdempotencyCache
from aduib_rpc.resilience.retry_policy import RetryPolicy
from aduib_rpc.security.rbac import Permission, Principal, RbacPolicy, Role
from aduib_rpc.security.validators import PermissionValidator, RbacPermissionValidator, TokenValidator
from aduib_rpc.server.interceptors.qos import QosInterceptor
from aduib_rpc.server.interceptors.security import SecurityConfig, SecurityInterceptor
from aduib_rpc.server.qos.handler import QosHandler
from aduib_rpc.server.rpc_execution import MethodName, set_service_info
from aduib_rpc.server.rpc_execution.service_call import FuncCallContext, function, service
from aduib_rpc.server.tasks import TaskMethod, TaskStatus, TaskSubscribeRequest
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes
from aduib_rpc.discover.service.aduibrpc_service_factory import AduibServiceFactory
from aduib_rpc.exceptions import InvalidTokenError, TokenExpiredError

HOST = "127.0.0.1"
SERVICE_NAME = "e2e_service"
SERVICE_CLASS_NAME = "E2EFixtureService"
TENANT_ID = "tenant-e2e"
CLIENT_ID = "client-e2e"

TRANSPORTS = [
    TransportSchemes.HTTP,
    TransportSchemes.JSONRPC,
    TransportSchemes.GRPC,
    TransportSchemes.THRIFT,
]


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"

STATE = {
    "flaky": {},
    "idempotent": {},
}


class E2ETokenValidator(TokenValidator):
    async def validate(self, token: str, *, method: str, request: AduibRpcRequest, context) -> Principal:
        if token == "invalid":
            raise InvalidTokenError()
        if token == "expired":
            raise TokenExpiredError()

        roles = _roles_for_token(token)
        if roles is None:
            raise InvalidTokenError()

        auth = request.metadata.auth if request.metadata is not None else None
        principal_id = auth.principal if auth and auth.principal else f"user-{token}"
        principal_type = auth.principal_type if auth and auth.principal_type else "user"
        if auth and auth.roles:
            roles = list(auth.roles)

        return Principal(
            id=str(principal_id),
            type=str(principal_type),
            roles=frozenset(roles),
        )


class E2EPermissionValidator(PermissionValidator):
    def __init__(self) -> None:
        self._policy = _build_rbac_policy()
        self._validator = RbacPermissionValidator(self._policy)

    async def check(
        self,
        principal: Principal,
        *,
        permission: Permission,
        method: str,
        request: AduibRpcRequest,
        context,
    ) -> bool:
        return await self._validator.check(
            principal,
            permission=permission,
            method=method,
            request=request,
            context=context,
        )


def _roles_for_token(token: str) -> list[str] | None:
    mapping = {
        "token_reader": ["reader"],
        "token_writer": ["writer"],
        "token_admin": ["admin"],
    }
    return mapping.get(token)


def _build_rbac_policy() -> RbacPolicy:
    reader = Role(
        name="reader",
        permissions=frozenset({Permission(resource="docs", action="read")}),
    )
    writer = Role(
        name="writer",
        permissions=frozenset({
            Permission(resource="docs", action="read"),
            Permission(resource="docs", action="write"),
        }),
    )
    admin = Role(
        name="admin",
        permissions=frozenset({Permission(resource="*", action="*")}),
        allowed_methods=frozenset({"*"}),
    )
    policy = RbacPolicy(roles=[reader, writer, admin], default_role="anonymous")
    policy.set_superadmin_role("admin")
    return policy


def _handler_names() -> dict[str, str]:
    return {
        "ping": f"{SERVICE_CLASS_NAME}.ping",
        "secure_echo": f"{SERVICE_CLASS_NAME}.secure_echo",
        "secure_write": f"{SERVICE_CLASS_NAME}.secure_write",
        "flaky": f"{SERVICE_CLASS_NAME}.flaky",
        "idempotent": f"{SERVICE_CLASS_NAME}.idempotent_increment",
        "stream_numbers": f"{SERVICE_CLASS_NAME}.stream_numbers",
        "client_stream_sum": f"{SERVICE_CLASS_NAME}.client_stream_sum",
        "bidi_echo": f"{SERVICE_CLASS_NAME}.bidi_echo",
        "slow": f"{SERVICE_CLASS_NAME}.slow",
        "breaker_fail": f"{SERVICE_CLASS_NAME}.breaker_fail",
    }


def _register_services() -> dict[str, str]:
    @service(name=SERVICE_CLASS_NAME)
    class E2EFixtureService:
        def ping(self) -> str:
            return "pong"

        @function(permission=("docs", "read"))
        def secure_echo(self, text: str) -> str:
            return text

        @function(permission=("docs", "write"))
        def secure_write(self, value: int) -> int:
            return value

        @function(permission=("docs", "write"))
        def flaky(self, key: str) -> dict[str, int]:
            count = _bump_state("flaky", key)
            if count == 1:
                raise RuntimeError("boom")
            return {"attempts": count}

        @function(permission=("docs", "write"))
        def idempotent_increment(self, key: str) -> dict[str, int]:
            count = _bump_state("idempotent", key)
            return {"count": count}

        @function(permission=("docs", "read"), server_stream=True)
        async def stream_numbers(self, count: int) -> Any:
            for idx in range(int(count)):
                await asyncio.sleep(0)
                yield {"index": idx}

        @function(permission=("docs", "write"), client_stream=True)
        def client_stream_sum(self, stream_items: list[dict[str, Any]] | None = None) -> dict[str, int]:
            items = stream_items or []
            total = sum(int(item.get("value", 0)) for item in items if isinstance(item, dict))
            return {"total": total, "count": len(items)}

        @function(permission=("docs", "write"), bidirectional_stream=True)
        async def bidi_echo(self, stream_items: list[dict[str, Any]] | None = None) -> Any:
            for item in stream_items or []:
                await asyncio.sleep(0)
                if isinstance(item, dict):
                    yield {"echo": item.get("value")}
                else:
                    yield {"echo": item}

        @function(permission=("docs", "write"))
        async def slow(self, delay_ms: int) -> str:
            await asyncio.sleep(max(0, int(delay_ms)) / 1000)
            return "done"

        @function(permission=("docs", "write"))
        def breaker_fail(self) -> None:
            raise RuntimeError("boom")

    assert E2EFixtureService.__name__ == SERVICE_CLASS_NAME
    return _handler_names()


def _bump_state(bucket: str, key: str) -> int:
    counts = STATE[bucket]
    counts[key] = counts.get(key, 0) + 1
    return counts[key]


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _build_service_instance(port: int, scheme: TransportSchemes) -> ServiceInstance:
    capabilities = ServiceCapabilities(streaming=True, bidirectional=True)
    return ServiceInstance.create(
        service_name=SERVICE_NAME,
        host=HOST,
        port=port,
        scheme=scheme,
        protocol=AIProtocols.AduibRpc,
        weight=1,
        health=HealthStatus.HEALTHY,
        capabilities=capabilities,
    )


def _build_interceptors(
    cache: InMemoryIdempotencyCache,
    *,
    include_resilience: bool = False,
    circuit_breaker_config: dict[str, Any] | None = None,
    include_telemetry: bool = False,
):
    security = SecurityInterceptor(
        config=SecurityConfig(
            rbac_enabled=True,
            require_auth=True,
            audit_enabled=False,
        ),
        token_validator=E2ETokenValidator(),
        permission_validator=E2EPermissionValidator(),
    )
    qos = QosInterceptor(QosHandler(cache=cache, default_timeout_ms=2000, idempotency_ttl_s=60))
    interceptors = [security, qos]

    if include_resilience:
        from aduib_rpc.resilience.circuit_breaker import CircuitBreakerConfig
        from aduib_rpc.server.interceptors.resilience import ServerResilienceConfig, ServerResilienceInterceptor

        cb_cfg = None
        if circuit_breaker_config is not None:
            cb_cfg = CircuitBreakerConfig(**circuit_breaker_config)
        interceptors.append(ServerResilienceInterceptor(config=ServerResilienceConfig(circuit_breaker=cb_cfg)))

    if include_telemetry:
        from aduib_rpc.server.interceptors.telemetry import OTelServerInterceptor

        interceptors.append(OTelServerInterceptor())

    return interceptors


async def _wait_for_port(port: int, timeout_s: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        try:
            reader, writer = await asyncio.open_connection(HOST, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError(f"Timeout waiting for port {port}")
            await asyncio.sleep(0.05)


def _client_url(scheme: TransportSchemes, port: int) -> str:
    if scheme == TransportSchemes.GRPC:
        return f"{HOST}:{port}"
    if scheme == TransportSchemes.THRIFT:
        return f"thrift://{HOST}:{port}"
    return f"http://{HOST}:{port}"


@dataclass
class TransportServerHandle:
    scheme: TransportSchemes
    url: str
    client: Any
    handlers: dict[str, str]
    cache: InMemoryIdempotencyCache
    factory: AduibServiceFactory | None = None
    task: asyncio.Task | None = None
    process: Any | None = None

    async def close(self) -> None:
        if self.factory is not None:
            await _stop_factory(self.factory)
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.process is not None:
            self.process.terminate()
            self.process.join(5)


def _build_request(
    handler: str,
    *,
    token: str | None,
    roles: list[str] | None = None,
    data: dict[str, Any] | None = None,
    qos: QosConfig | None = None,
    long_task: bool = False,
    long_task_method: str | None = None,
    long_task_timeout: int | None = None,
) -> AduibRpcRequest:
    auth = None
    if token is not None:
        auth = AuthContext.create(
            scheme=AuthScheme.BEARER,
            credentials=token,
            principal="user-1",
            principal_type="user",
            roles=roles,
        )
    metadata = RequestMetadata.create(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        auth=auth,
        long_task=long_task,
        long_task_method=long_task_method,
        long_task_timeout=long_task_timeout,
    )
    return AduibRpcRequest(
        id=str(uuid.uuid4()),
        name=SERVICE_NAME,
        method=MethodName.format_v2(SERVICE_NAME, handler),
        data=data,
        metadata=metadata,
        qos=qos,
    )


def _make_retry_qos() -> QosConfig:
    return QosConfig(
        retry=RetryPolicy(
            max_attempts=2,
            initial_delay_ms=1,
            max_delay_ms=1,
            backoff_multiplier=1.0,
            jitter=0.0,
        )
    )


def _make_idempotency_qos(key: str) -> QosConfig:
    return QosConfig(idempotency_key=key)


def _start_thrift_server(port: int, interceptor_flags: dict[str, Any] | None = None) -> None:
    FuncCallContext.reset()
    cache = InMemoryIdempotencyCache()
    instance = _build_service_instance(port, TransportSchemes.THRIFT)
    set_service_info(instance)
    _register_services()
    factory = AduibServiceFactory(
        service_instance=instance,
        interceptors=_build_interceptors(cache, **(interceptor_flags or {})),
    )
    asyncio.run(factory.run_thrift_server())


async def _start_in_process_server(
    scheme: TransportSchemes,
    *,
    interceptor_flags: dict[str, Any] | None = None,
) -> TransportServerHandle:
    FuncCallContext.reset()
    cache = InMemoryIdempotencyCache()
    port = _get_free_port()
    instance = _build_service_instance(port, scheme)
    set_service_info(instance)
    handlers = _register_services()
    factory = AduibServiceFactory(
        service_instance=instance,
        interceptors=_build_interceptors(cache, **(interceptor_flags or {})),
    )
    task = asyncio.create_task(factory.run_server())
    await _wait_for_port(port)
    url = _client_url(scheme, port)
    client = AduibRpcClientFactory.create_client(url, server_preferred=scheme)
    return TransportServerHandle(
        scheme=scheme,
        url=url,
        client=client,
        handlers=handlers,
        cache=cache,
        factory=factory,
        task=task,
    )


async def _start_thrift_handle(
    *,
    interceptor_flags: dict[str, Any] | None = None,
) -> TransportServerHandle:
    import multiprocessing

    port = _get_free_port()
    process = multiprocessing.Process(target=_start_thrift_server, args=(port, interceptor_flags))
    process.daemon = True
    process.start()
    await _wait_for_port(port)
    url = _client_url(TransportSchemes.THRIFT, port)
    client = AduibRpcClientFactory.create_client(url, server_preferred=TransportSchemes.THRIFT)
    return TransportServerHandle(
        scheme=TransportSchemes.THRIFT,
        url=url,
        client=client,
        handlers=_handler_names(),
        cache=InMemoryIdempotencyCache(),
        process=process,
    )


async def _stop_factory(factory: AduibServiceFactory) -> None:
    server = factory.get_server()
    if server is None:
        return
    stop = getattr(server, "stop", None)
    if callable(stop):
        result = stop(0)
        if asyncio.iscoroutine(result):
            await result
        return
    shutdown = getattr(server, "shutdown", None)
    if callable(shutdown):
        result = shutdown()
        if asyncio.iscoroutine(result):
            await result
        return
    if hasattr(server, "should_exit"):
        server.should_exit = True


@pytest.fixture(scope="module", params=TRANSPORTS)
async def transport_server(request) -> TransportServerHandle:
    scheme: TransportSchemes = request.param
    if scheme == TransportSchemes.THRIFT:
        pytest.importorskip("aiothrift")
        handle = await _start_thrift_handle()
    else:
        handle = await _start_in_process_server(scheme)
    yield handle
    await handle.close()


async def _call_and_capture_error(transport_server: TransportServerHandle, request: AduibRpcRequest):
    try:
        return await transport_server.client.call(request)
    except ClientHTTPError as exc:
        return exc


async def _collect_stream(stream):
    items: list[Any] = []
    async for item in stream:
        items.append(item)
    return items


async def _iter_requests(requests: list[AduibRpcRequest]):
    for req in requests:
        yield req


@pytest.mark.anyio
async def test_security_errors(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["secure_echo"]
    request = _build_request(handler, token=None, data={"text": "hello"})
    response = await _call_and_capture_error(transport_server, request)
    if isinstance(response, ClientHTTPError):
        assert response.status_code == 401
    else:
        assert response.error is not None
        assert response.error.code == int(ErrorCode.UNAUTHENTICATED)

    request = _build_request(handler, token="invalid", data={"text": "hello"})
    response = await _call_and_capture_error(transport_server, request)
    if isinstance(response, ClientHTTPError):
        assert response.status_code == 401
    else:
        assert response.error is not None
        assert response.error.code == int(ErrorCode.INVALID_TOKEN)

    request = _build_request(handler, token="expired", data={"text": "hello"})
    response = await _call_and_capture_error(transport_server, request)
    if isinstance(response, ClientHTTPError):
        assert response.status_code == 401
    else:
        assert response.error is not None
        assert response.error.code == int(ErrorCode.TOKEN_EXPIRED)


@pytest.mark.anyio
async def test_rbac_permission_denied(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["secure_write"]
    request = _build_request(
        handler,
        token="token_reader",
        roles=["reader"],
        data={"value": 10},
    )
    response = await _call_and_capture_error(transport_server, request)
    if isinstance(response, ClientHTTPError):
        assert response.status_code == 403
    else:
        assert response.error is not None
        assert response.error.code == int(ErrorCode.PERMISSION_DENIED)


@pytest.mark.anyio
async def test_rbac_permission_allowed(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["secure_echo"]
    request = _build_request(
        handler,
        token="token_reader",
        roles=["reader"],
        data={"text": "ok"},
    )
    response = await transport_server.client.call(request)
    assert response.error is None
    assert response.result == "ok"


@pytest.mark.anyio
async def test_qos_retry(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["flaky"]
    key = f"retry-{uuid.uuid4()}"
    request = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data={"key": key},
        qos=_make_retry_qos(),
    )
    response = await transport_server.client.call(request)
    assert response.error is None
    assert response.result == {"attempts": 2}


@pytest.mark.anyio
async def test_qos_idempotency(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["idempotent"]
    idem_key = f"idem-{uuid.uuid4()}"
    data = {"key": idem_key}
    first_request = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data=data,
        qos=_make_idempotency_qos(idem_key),
    )
    second_request = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data=data,
        qos=_make_idempotency_qos(idem_key),
    )
    first = await transport_server.client.call(first_request)
    second = await transport_server.client.call(second_request)
    assert first.error is None
    assert second.error is None
    assert first.result == {"count": 1}
    assert second.result == {"count": 1}


@pytest.mark.anyio
async def test_streaming_server_stream(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["stream_numbers"]
    request = _build_request(
        handler,
        token="token_reader",
        roles=["reader"],
        data={"count": 3},
    )
    responses = await _collect_stream(transport_server.client.call_server_stream(request))
    assert responses
    assert [resp.result for resp in responses] == [
        {"index": 0},
        {"index": 1},
        {"index": 2},
    ]
    assert all(resp.error is None for resp in responses)


@pytest.mark.anyio
async def test_streaming_client_stream(transport_server: TransportServerHandle) -> None:
    if transport_server.scheme in {TransportSchemes.HTTP, TransportSchemes.JSONRPC}:
        pytest.skip("client streaming not supported for REST/JSON-RPC")
    handler = transport_server.handlers["client_stream_sum"]
    base = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data={},
    )
    requests = [base] + [
        _build_request(handler, token="token_writer", roles=["writer"], data={"value": value})
        for value in (1, 2, 3)
    ]
    response = await transport_server.client.call_client_stream(_iter_requests(requests))
    assert response.error is None
    assert response.result == {"total": 6, "count": 3}


@pytest.mark.anyio
async def test_streaming_bidirectional(transport_server: TransportServerHandle) -> None:
    if transport_server.scheme in {TransportSchemes.HTTP, TransportSchemes.JSONRPC}:
        pytest.skip("bidirectional streaming not supported for REST/JSON-RPC")
    handler = transport_server.handlers["bidi_echo"]
    base = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data={},
    )
    requests = [base] + [
        _build_request(handler, token="token_writer", roles=["writer"], data={"value": value})
        for value in ("a", "b", "c")
    ]
    responses = await _collect_stream(
        transport_server.client.call_bidirectional(_iter_requests(requests))
    )
    assert [resp.result for resp in responses] == [
        {"echo": "a"},
        {"echo": "b"},
        {"echo": "c"},
    ]


@pytest.mark.anyio
async def test_qos_timeout(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["slow"]
    request = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data={"delay_ms": 50},
        qos=QosConfig(timeout_ms=5),
    )
    response = await _call_and_capture_error(transport_server, request)
    if isinstance(response, ClientHTTPError):
        assert response.status_code in {408, 504, 500}
    else:
        assert response.error is not None
        assert response.error.code == int(ErrorCode.RPC_TIMEOUT)


@pytest.mark.anyio
async def test_long_task_submit_and_subscribe(transport_server: TransportServerHandle) -> None:
    handler = transport_server.handlers["secure_echo"]
    request = _build_request(
        handler,
        token="token_reader",
        roles=["reader"],
        data={"text": "long-task"},
        long_task=True,
        long_task_method=TaskMethod.SUBMIT_TASK,
    )
    response = await transport_server.client.call(request)
    assert response.error is None
    assert isinstance(response.result, dict)
    task_id = response.result.get("task_id")
    assert task_id

    events = await _collect_stream(
        transport_server.client.task_subscribe(TaskSubscribeRequest(task_id=task_id))
    )
    assert events
    assert any(event.task.status == TaskStatus.SUCCEEDED for event in events)


@pytest.mark.anyio
async def test_health_check(transport_server: TransportServerHandle) -> None:
    response = await transport_server.client.health_check(
        HealthCheckRequest(service=SERVICE_NAME)
    )
    assert response.status == HealthCheckStatus.HEALTHY
    assert response.services is not None
    assert response.services.get(SERVICE_NAME) == HealthCheckStatus.HEALTHY


@pytest.mark.anyio
async def test_health_watch(transport_server: TransportServerHandle) -> None:
    responses = await _collect_stream(
        transport_server.client.health_watch(HealthCheckRequest(service=SERVICE_NAME))
    )
    assert responses
    assert responses[0].status == HealthCheckStatus.HEALTHY


@pytest.fixture(scope="module", params=TRANSPORTS)
async def resilience_server(request) -> TransportServerHandle:
    scheme: TransportSchemes = request.param
    flags = {
        "include_resilience": True,
        "circuit_breaker_config": {
            "failure_threshold": 1,
            "success_threshold": 1,
            "timeout_seconds": 30.0,
        },
    }
    if scheme == TransportSchemes.THRIFT:
        pytest.importorskip("aiothrift")
        handle = await _start_thrift_handle(interceptor_flags=flags)
    else:
        handle = await _start_in_process_server(scheme, interceptor_flags=flags)
    yield handle
    await handle.close()


@pytest.mark.anyio
async def test_circuit_breaker_open(resilience_server: TransportServerHandle) -> None:
    handler = resilience_server.handlers["breaker_fail"]
    request = _build_request(
        handler,
        token="token_writer",
        roles=["writer"],
        data={},
    )
    await _call_and_capture_error(resilience_server, request)
    second = await _call_and_capture_error(resilience_server, request)
    if isinstance(second, ClientHTTPError):
        assert second.status_code in {429, 503, 500}
    else:
        assert second.error is not None
        assert second.error.code == int(ErrorCode.CIRCUIT_BREAKER_OPEN)


@pytest.mark.anyio
async def test_telemetry_span_emitted() -> None:
    pytest.importorskip("opentelemetry")
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    old_provider = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)

    handle = await _start_in_process_server(
        TransportSchemes.HTTP,
        interceptor_flags={"include_telemetry": True},
    )
    try:
        handler = handle.handlers["secure_echo"]
        request = _build_request(
            handler,
            token="token_reader",
            roles=["reader"],
            data={"text": "trace"},
        )
        resp = await handle.client.call(request)
        assert resp.error is None
        spans = exporter.get_finished_spans()
        assert spans
        assert any(span.attributes.get("rpc.method") == request.method for span in spans)
    finally:
        await handle.close()
        trace.set_tracer_provider(old_provider)
