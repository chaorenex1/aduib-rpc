import asyncio

import pytest

from aduib_rpc.app import RpcApp
from aduib_rpc.discover.entities import ServiceInstance
from aduib_rpc.utils.constant import AIProtocols, TransportSchemes


@pytest.mark.asyncio
async def test_registry_register_discover_inmemory() -> None:
    # No server start needed to validate registry+resolver wiring.
    app = RpcApp.from_registry_type("in_memory")

    inst = ServiceInstance(
        service_name="demo-service",
        host="127.0.0.1",
        port=12345,
        protocol=AIProtocols.AduibRpc,
        weight=1,
        scheme=TransportSchemes.JSONRPC,
    )

    await app.register([inst])

    resolved = app.discover("demo-service")
    assert resolved is not None
    assert resolved.instance.host == "127.0.0.1"
    assert resolved.instance.port == 12345


@pytest.mark.asyncio
async def test_start_servers_background_task_cancel() -> None:
    # Use a non-routable port binding? We can't reliably bind on CI if port is in use.
    # So we only verify the tasks get created and can be stopped.
    app = RpcApp.from_registry_type("in_memory")

    inst = ServiceInstance(
        service_name="demo-service",
        host="127.0.0.1",
        port=0,  # let uvicorn/grpc choose? (uvicorn may not accept 0, so we won't actually start here)
        protocol=AIProtocols.AduibRpc,
        weight=1,
        scheme=TransportSchemes.GRPC,
    )

    # We don't actually run the server to termination, but we do ensure stop() is safe
    # by creating a dummy task.
    async def _dummy():
        await asyncio.sleep(10)

    running = []
    from aduib_rpc.app import RunningService
    from aduib_rpc.discover.service.aduibrpc_service_factory import AduibServiceFactory

    factory = AduibServiceFactory(service_instance=inst)
    task = asyncio.create_task(_dummy())
    rs = RunningService(instance=inst, factory=factory, task=task)
    running.append(rs)

    await rs.stop()
    assert rs.task.cancelled() or rs.task.done()


@pytest.mark.asyncio
async def test_run_end_to_end_import_service_modules_auto_instances() -> None:
    from aduib_rpc.app import run_end_to_end
    from aduib_rpc.utils.constant import TransportSchemes

    app, running, resolved = await run_end_to_end(
        registry_type="in_memory",
        instances=None,
        service_modules=["tests.fixtures_service_module"],
        call_service_name="FixtureService",
        server_kwargs={"startup_delay": 0.0},
        default_scheme=TransportSchemes.JSONRPC,
        default_port_start=0,
        auto_mode="single_endpoint",
        start_server=False,
    )

    assert resolved.instance.service_name == "FixtureService"
    assert resolved.instance.host == "127.0.0.1"
    assert isinstance(resolved.instance.port, int)
    assert resolved.instance.port > 0

    # No server started in this unit test.
    assert running == []
