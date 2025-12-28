import asyncio

import pytest

from aduib_rpc.server.request_handlers.default_request_handler import DefaultRequestHandler
from aduib_rpc.server.rpc_execution.service_call import service
from aduib_rpc.types import AduibRpcRequest


@service("LongTaskSvc")
class LongTaskSvc:
    async def slow_add(self, a: int, b: int, delay_ms: int = 30) -> int:
        await asyncio.sleep(delay_ms / 1000)
        return a + b

    async def slow_fail(self, delay_ms: int = 10) -> int:
        await asyncio.sleep(delay_ms / 1000)
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_task_submit_and_poll_result_success():
    handler = DefaultRequestHandler()

    submit = AduibRpcRequest(
        method="task/submit",
        data={
            "target_method": "LongTaskSvc.slow_add",
            "params": {"a": 1, "b": 2, "delay_ms": 20},
        },
    )
    submit_resp = await handler.on_message(submit)
    assert submit_resp.is_success()
    task_id = submit_resp.result["task_id"]

    # poll until succeeded
    for _ in range(50):
        res = await handler.on_message(AduibRpcRequest(method="task/result", data={"task_id": task_id}))
        assert res.is_success()
        if res.result["status"] == "succeeded":
            assert res.result["value"] == 3
            return
        await asyncio.sleep(0.01)

    raise AssertionError("task did not finish in time")


@pytest.mark.asyncio
async def test_task_subscribe_receives_completed_event():
    handler = DefaultRequestHandler()

    submit_resp = await handler.on_message(
        AduibRpcRequest(
            method="task/submit",
            data={
                "target_method": "LongTaskSvc.slow_add",
                "params": {"a": 10, "b": 5, "delay_ms": 20},
            },
        )
    )
    task_id = submit_resp.result["task_id"]

    events = []
    async for r in handler.on_stream_message(AduibRpcRequest(method="task/subscribe", data={"task_id": task_id})):
        assert r.is_success()
        events.append(r.result)

    assert any(e["event"] == "completed" for e in events)
    completed = [e for e in events if e["event"] == "completed"][0]
    assert completed["task"]["status"] == "succeeded"
    assert completed["task"]["value"] == 15


@pytest.mark.asyncio
async def test_task_failure_surfaces_error():
    handler = DefaultRequestHandler()

    submit_resp = await handler.on_message(
        AduibRpcRequest(
            method="task/submit",
            data={
                "target_method": "LongTaskSvc.slow_fail",
                "params": {"delay_ms": 10},
            },
        )
    )
    task_id = submit_resp.result["task_id"]

    for _ in range(50):
        res = await handler.on_message(AduibRpcRequest(method="task/result", data={"task_id": task_id}))
        if res.result["status"] == "failed":
            assert "error" in res.result
            assert res.result["error"]["code"] == 500
            return
        await asyncio.sleep(0.01)

    raise AssertionError("task did not fail in time")

