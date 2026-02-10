import logging
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request

from aduib_rpc.protocol.v2 import AduibRpcRequest, AduibRpcResponse
from aduib_rpc.protocol.v2 import ResponseStatus
from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.server.rpc_execution import MethodName
from aduib_rpc.utils.error_handlers import exception_to_error
from aduib_rpc.utils.json_v2_utils import FromJson

logger = logging.getLogger(__name__)

class RESTV2Handler:
    """Pure v2 REST handler.

    - Input: JSON body matching AduibRpcRequest (v2).
    - Output: dict serialized from AduibRpcResponse (v2).

    This handler intentionally does *not* accept protobuf `RpcTask` payloads.
    """

    def __init__(self, request_handler: RequestHandler):
        self.request_handler = request_handler

    @staticmethod
    def _is_error_response(response: AduibRpcResponse) -> bool:
        if response.error is not None:
            return True
        return response.status == ResponseStatus.ERROR

    @staticmethod
    def _normalize_payload(payload: Any) -> Any:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json", exclude_none=True)
        if isinstance(payload, dict):
            return payload
        return payload

    @staticmethod
    def _extract_request_id(payload: Any) -> str | int | None:
        if isinstance(payload, dict):
            return payload.get("id")
        return None

    @staticmethod
    def _response_payload(response: AduibRpcResponse) -> dict[str, Any]:
        return response.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _error_payload(request_id: str | int | None, exc: Exception) -> dict[str, Any]:
        err = exception_to_error(exc)
        return AduibRpcResponse(
            id=request_id, status=ResponseStatus.ERROR, error=err
        ).model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _parse_v2_request(payload: Any) -> AduibRpcRequest:
        return AduibRpcRequest.model_validate(payload)

    async def on_message(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        request_id: str | int | None = None
        try:
            payload = await request.json()
            msg = self._parse_v2_request(payload)
            request_id = msg.id
            resp = await self.request_handler.on_message(msg, context)
            return self._response_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler on_message failed")
            return self._error_payload(request_id, e)

    async def on_stream_message(
        self, request: Request, context: ServerContext | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handle streaming requests, yielding v2 response frames.

        Yields:
            dict: Serialized AduibRpcResponse payloads for SSE transmission.
        """
        request_id: str | int | None = None
        try:
            payload = await request.json()
            msg = self._parse_v2_request(payload)
            request_id = msg.id

            async for chunk in self.request_handler.on_stream_message(msg, context):
                if isinstance(chunk, AduibRpcResponse) and self._is_error_response(chunk):
                    yield self._response_payload(chunk)
                    return
                yield self._response_payload(chunk)

        except Exception as e:
            logger.exception("RESTV2Handler on_stream_message failed")
            yield self._error_payload(request_id, e)

    async def Call(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles AduibRpcService.Call over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            msg = self._parse_v2_request(payload)
            request_id = msg.id
            resp = await self.request_handler.call(msg, context)
            return self._response_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler Call failed")
            return self._error_payload(request_id, e)

    async def CallServerStream(
        self, request: Request, context: ServerContext | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handles AduibRpcService.CallServerStream over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            msg = self._parse_v2_request(payload)
            request_id = msg.id

            async for chunk in self.request_handler.call_server_stream(msg, context):
                if isinstance(chunk, AduibRpcResponse) and self._is_error_response(chunk):
                    yield self._response_payload(chunk)
                    return
                yield self._response_payload(chunk)
        except Exception as e:
            logger.exception("RESTV2Handler CallServerStream failed")
            yield self._error_payload(request_id, e)

    async def CallClientStream(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles AduibRpcService.CallClientStream over REST v2 (not supported)."""
        err = exception_to_error(NotImplementedError("REST v2 does not support client streaming"))
        return AduibRpcResponse(id=None, status=ResponseStatus.ERROR, error=err).model_dump(mode="json", exclude_none=True)

    async def CallBidirectional(
        self, request: Request, context: ServerContext | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handles AduibRpcService.CallBidirectional over REST v2 (not supported)."""
        err = NotImplementedError("REST v2 does not support bidirectional streaming")
        yield self._error_payload(None, err)

    async def Submit(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles TaskService.Submit over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            submit = FromJson.task_submit_request(payload)
            resp = await self.request_handler.task_submit(submit, context)
            return self._normalize_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler Submit failed")
            return self._error_payload(request_id, e)

    async def Query(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles TaskService.Query over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            query = FromJson.task_query_request(payload)
            resp = await self.request_handler.task_query(query, context)
            return self._normalize_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler Query failed")
            return self._error_payload(request_id, e)

    async def Cancel(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles TaskService.Cancel over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            cancel = FromJson.task_cancel_request(payload)
            resp = await self.request_handler.task_cancel(cancel, context)
            return self._normalize_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler Cancel failed")
            return self._error_payload(request_id, e)

    async def Subscribe(
        self, request: Request, context: ServerContext | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handles TaskService.Subscribe over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            sub = FromJson.task_subscribe_request(payload)
            async for event in self.request_handler.task_subscribe(sub, context):
                yield self._normalize_payload(event)
        except Exception as e:
            logger.exception("RESTV2Handler Subscribe failed")
            yield self._error_payload(request_id, e)

    async def Check(self, request: Request, context: ServerContext | None = None) -> dict[str, Any]:
        """Handles HealthService.Check over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            health = FromJson.health_request(payload)
            resp = await self.request_handler.health_check(health, context)
            return self._normalize_payload(resp)
        except ValidationError as e:
            return self._error_payload(request_id, e)
        except Exception as e:
            logger.exception("RESTV2Handler Check failed")
            return self._error_payload(request_id, e)

    async def Watch(
        self, request: Request, context: ServerContext | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Handles HealthService.Watch over REST v2."""
        request_id: str | int | None = None
        try:
            payload = await request.json()
            request_id = self._extract_request_id(payload)
            health = FromJson.health_request(payload)
            async for event in self.request_handler.health_watch(health, context):
                yield self._normalize_payload(event)
        except Exception as e:
            logger.exception("RESTV2Handler Watch failed")
            yield self._error_payload(request_id, e)
