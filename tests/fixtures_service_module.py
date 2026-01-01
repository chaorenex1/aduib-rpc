from aduib_rpc.server.rpc_execution.service_call import service


@service("FixtureService")
class FixtureService:
    def ping(self) -> str:
        return "pong"

