import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from aduib_rpc.server.context import ServerContext
from aduib_rpc.server.request_handlers.request_handler import RequestHandler
from aduib_rpc.types import (
    AduibJSONRPCResponse,
    AduibRpcRequest,
    AduibRpcResponse,
    JSONRPCError,
    JSONRPCErrorResponse,
    JsonRpcMessageRequest,
    JsonRpcMessageResponse,
    JsonRpcMessageSuccessResponse,
    JsonRpcStreamingMessageRequest,
    JsonRpcStreamingMessageResponse,
    JsonRpcStreamingMessageSuccessResponse,
)
from aduib_rpc.utils.error_handlers import exception_to_error
from aduib_rpc.utils.jsonrpc_helper import prepare_response_object
from aduib_rpc.utils.json_v2_utils import FromJson

logger = logging.getLogger(__name__)

class JSONRPCV2Handler:
    """Maps incoming JSON-RPC requests to the appropriate request handler method and formats responses."""

    def __init__(
        self,
        request_handler: RequestHandler,
    ):
        """Initializes the JSONRPCHandler.

        Args:
            request_handler: The underlying `RequestHandler` instance to delegate requests to.
        """
        self.request_handler = request_handler

    @staticmethod
    def _rpc_error_to_jsonrpc(error: Any) -> JSONRPCError:
        if hasattr(error, "model_dump"):
            payload = error.model_dump(mode="json", exclude_none=True)
        elif isinstance(error, dict):
            payload = error
        else:
            payload = {"code": 0, "name": "UNKNOWN", "message": str(error)}
        return JSONRPCError(
            code=int(payload.get("code") or 0),
            message=str(payload.get("message") or ""),
            data=payload,
        )

    def _exception_to_jsonrpc_error(self, exc: Exception, *, code: int | None = None) -> JSONRPCError:
        rpc_error = exception_to_error(exc, code=code)
        return self._rpc_error_to_jsonrpc(rpc_error)

    @staticmethod
    def _require_rpc_request(value: Any) -> AduibRpcRequest:
        if isinstance(value, AduibRpcRequest):
            return value
        return AduibRpcRequest.model_validate(value)

    async def on_message(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles the 'message/send' JSON-RPC method."""
        try:
            message = await self.request_handler.on_message(
                self._require_rpc_request(request.params), context
            )
            return prepare_response_object(
                request.id,
                message,
                (AduibRpcResponse,),
                JsonRpcMessageSuccessResponse,
                JsonRpcMessageResponse,
            )
        except Exception as e:
            logger.exception("JSONRPCHandler on_message failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def on_stream_message(
        self,
        request: JsonRpcStreamingMessageRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        """Handles the 'message/stream' JSON-RPC method."""
        try:
            async for event in self.request_handler.on_stream_message(
                self._require_rpc_request(request.params), context
            ):
                yield prepare_response_object(
                    request.id,
                    event,
                    (AduibRpcResponse,),
                    JsonRpcStreamingMessageSuccessResponse,
                    JsonRpcStreamingMessageResponse,
                )
        except Exception as e:
            logger.exception("JSONRPCHandler on_stream_message failed")
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Call(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles AduibRpcService.Call over JSON-RPC."""
        try:
            message = await self.request_handler.call(
                self._require_rpc_request(request.params), context
            )
            return prepare_response_object(
                request.id,
                message,
                (AduibRpcResponse,),
                JsonRpcMessageSuccessResponse,
                JsonRpcMessageResponse,
            )
        except Exception as e:
            logger.exception("JSONRPCHandler Call failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def CallServerStream(
        self,
        request: JsonRpcStreamingMessageRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        """Handles AduibRpcService.CallServerStream over JSON-RPC."""
        try:
            async for event in self.request_handler.call_server_stream(
                self._require_rpc_request(request.params), context
            ):
                yield prepare_response_object(
                    request.id,
                    event,
                    (AduibRpcResponse,),
                    JsonRpcStreamingMessageSuccessResponse,
                    JsonRpcStreamingMessageResponse,
                )
        except Exception as e:
            logger.exception("JSONRPCHandler CallServerStream failed")
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def CallClientStream(
        self,
        requests: AsyncIterator[JsonRpcMessageRequest],
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles AduibRpcService.CallClientStream over JSON-RPC."""
        try:
            first: JsonRpcMessageRequest | None = None
            async for item in requests:
                first = item
                break
            if first is None:
                raise ValueError("request stream is empty")

            async def _iter() -> AsyncIterator[AduibRpcRequest]:
                yield self._require_rpc_request(first.params)
                async for item in requests:
                    yield self._require_rpc_request(item.params)

            message = await self.request_handler.call_client_stream(_iter(), context)
            return prepare_response_object(
                first.id,
                message,
                (AduibRpcResponse,),
                JsonRpcMessageSuccessResponse,
                JsonRpcMessageResponse,
            )
        except Exception as e:
            logger.exception("JSONRPCHandler CallClientStream failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=None,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def CallBidirectional(
        self,
        requests: AsyncIterator[JsonRpcStreamingMessageRequest],
        context: ServerContext | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        """Handles AduibRpcService.CallBidirectional over JSON-RPC."""
        first: JsonRpcStreamingMessageRequest | None = None
        async for item in requests:
            first = item
            break
        if first is None:
            err = self._exception_to_jsonrpc_error(ValueError("request stream is empty"))
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=None,
                    error=err,
                )
            )
            return

        async def _iter() -> AsyncIterator[AduibRpcRequest]:
            yield self._require_rpc_request(first.params)
            async for item in requests:
                yield self._require_rpc_request(item.params)

        try:
            async for event in self.request_handler.call_bidirectional(_iter(), context):
                yield prepare_response_object(
                    first.id,
                    event,
                    (AduibRpcResponse,),
                    JsonRpcStreamingMessageSuccessResponse,
                    JsonRpcStreamingMessageResponse,
                )
        except Exception as e:
            logger.exception("JSONRPCHandler CallBidirectional failed")
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=first.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Submit(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles TaskService.Submit over JSON-RPC."""
        try:
            submit = FromJson.task_submit_request(request.params)
            resp = await self.request_handler.task_submit(submit, context)
            return AduibJSONRPCResponse(
                root=JsonRpcMessageSuccessResponse(
                    id=request.id,
                    result=resp,
                )
            )
        except Exception as e:
            logger.exception("JSONRPCHandler Submit failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Query(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles TaskService.Query over JSON-RPC."""
        try:
            query = FromJson.task_query_request(request.params)
            resp = await self.request_handler.task_query(query, context)
            return AduibJSONRPCResponse(
                root=JsonRpcMessageSuccessResponse(
                    id=request.id,
                    result=resp,
                )
            )
        except Exception as e:
            logger.exception("JSONRPCHandler Query failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Cancel(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles TaskService.Cancel over JSON-RPC."""
        try:
            cancel = FromJson.task_cancel_request(request.params)
            resp = await self.request_handler.task_cancel(cancel, context)
            return AduibJSONRPCResponse(
                root=JsonRpcMessageSuccessResponse(
                    id=request.id,
                    result=resp,
                )
            )
        except Exception as e:
            logger.exception("JSONRPCHandler Cancel failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Subscribe(
        self,
        request: JsonRpcStreamingMessageRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        """Handles TaskService.Subscribe over JSON-RPC."""
        try:
            sub = FromJson.task_subscribe_request(request.params)
            async for event in self.request_handler.task_subscribe(sub, context):
                yield JsonRpcStreamingMessageResponse(
                    root=JsonRpcStreamingMessageSuccessResponse(
                        id=request.id,
                        result=event,
                    )
                )
        except Exception as e:
            logger.exception("JSONRPCHandler Subscribe failed")
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Check(
        self,
        request: JsonRpcMessageRequest,
        context: ServerContext | None = None,
    ) -> AduibJSONRPCResponse:
        """Handles HealthService.Check over JSON-RPC."""
        try:
            health = FromJson.health_request(request.params)
            resp = await self.request_handler.health_check(health, context)
            return AduibJSONRPCResponse(
                root=JsonRpcMessageSuccessResponse(
                    id=request.id,
                    result=resp,
                )
            )
        except Exception as e:
            logger.exception("JSONRPCHandler Check failed")
            return AduibJSONRPCResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )

    async def Watch(
        self,
        request: JsonRpcStreamingMessageRequest,
        context: ServerContext | None = None,
    ) -> AsyncGenerator[JsonRpcStreamingMessageResponse, None]:
        """Handles HealthService.Watch over JSON-RPC."""
        try:
            health = FromJson.health_request(request.params)
            async for event in self.request_handler.health_watch(health, context):
                yield JsonRpcStreamingMessageResponse(
                    root=JsonRpcStreamingMessageSuccessResponse(
                        id=request.id,
                        result=event,
                    )
                )
        except Exception as e:
            logger.exception("JSONRPCHandler Watch failed")
            yield JsonRpcStreamingMessageResponse(
                root=JSONRPCErrorResponse(
                    id=request.id,
                    error=self._exception_to_jsonrpc_error(e),
                )
            )
