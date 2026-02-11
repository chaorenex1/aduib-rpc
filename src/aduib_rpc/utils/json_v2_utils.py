from __future__ import annotations

from typing import Any

from aduib_rpc.protocol.v2.health import HealthCheckRequest
from aduib_rpc.protocol.v2.types import AduibRpcRequest as V2Request
from aduib_rpc.server.tasks.types import (
    TaskCancelRequest,
    TaskQueryRequest,
    TaskSubmitRequest,
    TaskSubscribeRequest,
)


class FromJson:
    """Utility helpers for converting JSON payloads to v2 task/health models."""

    @staticmethod
    def _payload(value: Any) -> Any:
        if isinstance(value, V2Request):
            return value.data or {}
        return value if value is not None else {}

    @classmethod
    def task_submit_request(cls, value: Any) -> TaskSubmitRequest:
        return TaskSubmitRequest.model_validate(cls._payload(value))

    @classmethod
    def task_query_request(cls, value: Any) -> TaskQueryRequest:
        return TaskQueryRequest.model_validate(cls._payload(value))

    @classmethod
    def task_cancel_request(cls, value: Any) -> TaskCancelRequest:
        return TaskCancelRequest.model_validate(cls._payload(value))

    @classmethod
    def task_subscribe_request(cls, value: Any) -> TaskSubscribeRequest:
        payload = cls._payload(value)
        if isinstance(payload, TaskSubscribeRequest):
            return payload
        if isinstance(payload, TaskQueryRequest):
            return TaskSubscribeRequest(task_id=payload.task_id)
        return TaskSubscribeRequest.model_validate(payload)

    @classmethod
    def health_request(cls, value: Any) -> HealthCheckRequest:
        payload = cls._payload(value)
        if not payload:
            return HealthCheckRequest()
        return HealthCheckRequest.model_validate(payload)
