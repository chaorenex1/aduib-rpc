"""Local HTTP server for Rust integration tests (REST + JSON-RPC).

Starts two uvicorn servers:
- REST:    http://127.0.0.1:<rest_port>/aduib_rpc/v1/message/completion
- JSONRPC: http://127.0.0.1:<jsonrpc_port>/aduib_rpc

Usage (manual):
  python -m tests.http_server_local --rest-port 8001 --jsonrpc-port 8002
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from aduib_rpc.server.protocols.rest.fastapi_app import AduibRpcRestFastAPIApp
from aduib_rpc.server.protocols.rpc.fastapi_app import AduibRPCFastAPIApp
from aduib_rpc.server.request_handlers.default_request_handler import DefaultRequestHandler
from aduib_rpc.server.rpc_execution.service_call import service

logging.basicConfig(level=logging.INFO)


@service("CaculService")
class CaculService:
    def add(self, x: int, y: int) -> int:
        return x + y


@service("LongTaskSvc")
class LongTaskSvc:
    async def slow_add(self, a: int, b: int, delay_ms: int = 30) -> int:
        await asyncio.sleep(delay_ms / 1000)
        return a + b

    async def slow_fail(self, delay_ms: int = 10) -> int:
        await asyncio.sleep(delay_ms / 1000)
        raise RuntimeError("boom")


async def run_servers(rest_port: int, jsonrpc_port: int) -> None:
    handler = DefaultRequestHandler()

    rest_app = AduibRpcRestFastAPIApp(request_handler=handler).build()
    jsonrpc_app = AduibRPCFastAPIApp(request_handler=handler).build()

    rest_cfg = uvicorn.Config(rest_app, host="127.0.0.1", port=rest_port, log_level="warning")
    jsonrpc_cfg = uvicorn.Config(jsonrpc_app, host="127.0.0.1", port=jsonrpc_port, log_level="warning")

    rest_srv = uvicorn.Server(rest_cfg)
    jsonrpc_srv = uvicorn.Server(jsonrpc_cfg)

    await asyncio.gather(rest_srv.serve(), jsonrpc_srv.serve())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rest-port", type=int, required=True)
    p.add_argument("--jsonrpc-port", type=int, required=True)
    args = p.parse_args()

    asyncio.run(run_servers(args.rest_port, args.jsonrpc_port))


if __name__ == "__main__":
    main()
