from aduib_rpc.server.rpc_execution.service_call import FuncCallContext, service


def test_runtime_reset_clears_registrations() -> None:
    FuncCallContext.reset()

    @service("TmpService")
    class TmpService:
        def add(self, x: int, y: int) -> int:
            return x + y

    assert any(name.startswith("TmpService.") for name in FuncCallContext.get_service_func_names())

    FuncCallContext.reset()
    assert FuncCallContext.get_service_func_names() == []

