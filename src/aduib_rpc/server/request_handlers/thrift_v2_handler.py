from __future__ import annotations

import logging
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.utils.anyio_compat import run as run_anyio
from aduib_rpc.utils.thrift_v2_utils import FromThrift
from aduib_rpc.utils.thrift_v2_utils import ToThrift

logger = logging.getLogger(__name__)


def _attach_tenant_id(context: ServerContext, metadata: dict[str, str]) -> None:
    tenant_id = (
        metadata.get("tenant_id")
        or metadata.get("X-Tenant-ID")
        or metadata.get("x-tenant-id")
        or metadata.get("X-Tenant")
        or metadata.get("x-tenant")
    )
    if tenant_id:
        context.state["tenant_id"] = str(tenant_id)


class ThriftV2Handler:
    """Pure v2 Thrift handler."""

    def __init__(self, request_handler: RequestHandler):
        self.request_handler = request_handler

    def Call(self, request):
        from aduib_rpc.thrift_v2.ttypes import Response as ThriftResponse

        try:
            metadata = dict(getattr(request, "metadata", None) or {})
            ctx = ServerContext(state={"headers": metadata}, metadata=metadata)
            _attach_tenant_id(ctx, metadata)
            v2_req = FromThrift.request(request)
            v2_resp = run_anyio(self.request_handler.on_message, v2_req, ctx)

            return ThriftResponse(
                aduib_rpc="2.0",
                id=v2_resp.id or "",
                status=ToThrift.response_status(v2_resp.status),
                payload=ToThrift.response_payload(v2_resp),
            )
        except Exception as e:
            logger.exception("Error processing Thrift v2 Call")
            payload = ToThrift.error_payload(e)
            return ThriftResponse(
                aduib_rpc="2.0",
                id=getattr(request, "id", ""),
                status=2,
                payload=payload,
            )

    def CallServerStream(self, request):
        """Server-streaming call.

        Thrift doesn't provide true streaming in this generated interface; our IDL
        models it as a single reply containing a list of Response messages.
        """
        from aduib_rpc.thrift_v2.ttypes import Response as ThriftResponse

        try:
            metadata = dict(getattr(request, "metadata", None) or {})
            ctx = ServerContext(state={"headers": metadata}, metadata=metadata)
            _attach_tenant_id(ctx, metadata)
            v2_req = FromThrift.request(request)

            out: list[ThriftResponse] = []

            async def _collect() -> None:
                async for item in self.request_handler.on_stream_message(v2_req, ctx):
                    out.append(
                        ThriftResponse(
                            aduib_rpc="2.0",
                            id=item.id or "",
                            status=ToThrift.response_status(item.status),
                            payload=ToThrift.response_payload(item),
                        )
                    )

            run_anyio(_collect)

            return out
        except Exception as e:
            logger.exception("Error processing Thrift v2 CallServerStream")
            payload = ToThrift.error_payload(e)
            return [
                ThriftResponse(
                    aduib_rpc="2.0",
                    id=getattr(request, "id", ""),
                    status=2,
                    payload=payload,
                ),
            ]

    def CallClientStream(self, requests):
        from aduib_rpc.thrift_v2.ttypes import Response as ThriftResponse

        try:
            first = requests[0] if requests else None
            metadata = dict(getattr(first, "metadata", None) or {})
            ctx = ServerContext(state={"headers": metadata}, metadata=metadata)
            _attach_tenant_id(ctx, metadata)

            async def _iter():
                for item in requests or []:
                    yield FromThrift.request(item)

            v2_resp = run_anyio(self.request_handler.call_client_stream, _iter(), ctx)
            return ThriftResponse(
                aduib_rpc="2.0",
                id=v2_resp.id or "",
                status=ToThrift.response_status(v2_resp.status),
                payload=ToThrift.response_payload(v2_resp),
            )
        except Exception as e:
            logger.exception("Error processing Thrift v2 CallClientStream")
            payload = ToThrift.error_payload(e)
            return ThriftResponse(
                aduib_rpc="2.0",
                id="",
                status=2,
                payload=payload,
            )

    def CallBidirectional(self, requests):
        from aduib_rpc.thrift_v2.ttypes import Response as ThriftResponse

        try:
            first = requests[0] if requests else None
            metadata = dict(getattr(first, "metadata", None) or {})
            ctx = ServerContext(state={"headers": metadata}, metadata=metadata)
            _attach_tenant_id(ctx, metadata)

            async def _iter():
                for item in requests or []:
                    yield FromThrift.request(item)

            async def _collect():
                out = []
                async for resp in self.request_handler.call_bidirectional(_iter(), ctx):
                    out.append(
                        ThriftResponse(
                            aduib_rpc="2.0",
                            id=resp.id or "",
                            status=ToThrift.response_status(resp.status),
                            payload=ToThrift.response_payload(resp),
                        )
                    )
                return out

            return run_anyio(_collect)
        except Exception as e:
            logger.exception("Error processing Thrift v2 CallBidirectional")
            payload = ToThrift.error_payload(e)
            return [
                ThriftResponse(
                    aduib_rpc="2.0",
                    id="",
                    status=2,
                    payload=payload,
                ),
            ]


class ThriftV2TaskHandler:
    """Thrift TaskService handler."""

    def __init__(self, request_handler: RequestHandler):
        self.request_handler = request_handler

    def Submit(self, request):
        from aduib_rpc.thrift_v2.ttypes import TaskSubmitResponse as ThriftTaskSubmitResponse

        try:
            submit = FromThrift.task_submit_request(request)
            resp = run_anyio(self.request_handler.task_submit, submit, None)
            return ThriftTaskSubmitResponse(
                task_id=str(getattr(resp, "task_id", "")),
                status=ToThrift.task_status(getattr(resp, "status", None)),
                created_at_ms=int(getattr(resp, "created_at_ms", 0)),
            )
        except Exception as exc:
            logger.exception("Error processing TaskService.Submit")
            ToThrift.raise_app_error(exc)

    def Query(self, request):
        from aduib_rpc.thrift_v2.ttypes import TaskQueryResponse as ThriftTaskQueryResponse

        try:
            query = FromThrift.task_query_request(request)
            resp = run_anyio(self.request_handler.task_query, query, None)
            return ThriftTaskQueryResponse(task=ToThrift.task_record(getattr(resp, "task", None)))
        except Exception as exc:
            logger.exception("Error processing TaskService.Query")
            ToThrift.raise_app_error(exc)

    def Cancel(self, request):
        from aduib_rpc.thrift_v2.ttypes import TaskCancelResponse as ThriftTaskCancelResponse

        try:
            cancel = FromThrift.task_cancel_request(request)
            resp = run_anyio(self.request_handler.task_cancel, cancel, None)
            return ThriftTaskCancelResponse(
                task_id=str(getattr(resp, "task_id", getattr(request, "task_id", ""))),
                status=ToThrift.task_status(getattr(resp, "status", None)),
                canceled=bool(getattr(resp, "canceled", False)),
            )
        except Exception as exc:
            logger.exception("Error processing TaskService.Cancel")
            ToThrift.raise_app_error(exc)

    def Subscribe(self, request):
        try:
            sub = FromThrift.task_subscribe_request(request)

            async def _collect():
                out = []
                async for item in self.request_handler.task_subscribe(sub, None):
                    out.append(ToThrift.task_event(item))
                return out

            return run_anyio(_collect)
        except Exception as exc:
            logger.exception("Error processing TaskService.Subscribe")
            ToThrift.raise_app_error(exc)


class ThriftV2HealthHandler:
    """Thrift HealthService handler."""

    def __init__(self, request_handler: RequestHandler):
        self.request_handler = request_handler

    def Check(self, request):
        try:
            health = FromThrift.health_request(request)
            result = run_anyio(self.request_handler.health_check, health, None)
            return ToThrift.health_response(result)
        except Exception as exc:
            logger.exception("Error processing HealthService.Check")
            ToThrift.raise_app_error(exc)

    def Watch(self, request):
        try:
            health = FromThrift.health_request(request)

            async def _collect():
                out = []
                async for item in self.request_handler.health_watch(health, None):
                    out.append(ToThrift.health_response(item))
                return out

            return run_anyio(_collect)
        except Exception as exc:
            logger.exception("Error processing HealthService.Watch")
            ToThrift.raise_app_error(exc)
