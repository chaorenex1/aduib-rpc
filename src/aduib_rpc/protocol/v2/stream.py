from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, field_validator


class StreamMessageType(StrEnum):
    """Types of stream messages exchanged over the network.

    Attributes:
        DATA: Carries a data frame in the stream.
        HEARTBEAT: Liveness probe used to keep the stream active.
        ERROR: Indicates a stream-level error.
        END: Marks graceful completion of the stream.
        CANCEL: Requests cancellation of the stream.
        ACK: Acknowledges receipt of a sequence number.
    """

    DATA = "data"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    END = "end"
    CANCEL = "cancel"
    ACK = "ack"


class StreamState(StrEnum):
    """Local stream state managed by client/server, not transmitted on the wire.

    Attributes:
        CREATED: Stream is initialized but no messages have been sent.
        ACTIVE: Stream is open and exchanging messages.
        ERROR: Stream ended with an error.
        CANCELLED: Stream was cancelled by either side.
        COMPLETED: Stream completed successfully.
    """

    # State machine transitions:
    # CREATED -> ACTIVE (on first message)
    # ACTIVE -> COMPLETED (on END message)
    # ACTIVE -> ERROR (on ERROR message)
    # ACTIVE -> CANCELLED (on CANCEL message)
    CREATED = "created"
    ACTIVE = "active"
    ERROR = "error"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class StreamControl(BaseModel):
    """Control metadata for stream frames.

    Attributes:
        final: Indicates whether this is the final frame of the stream.
        total_count: Total number of data frames expected in the stream.
        ping_id: Identifier used to correlate heartbeat pings.
        reason: Reason for cancellation or error.
        ack_sequence: Sequence number being acknowledged.
    """

    final: bool = False
    total_count: int | None = None
    ping_id: str | None = None
    reason: str | None = None
    ack_sequence: int | None = None


class StreamPayload(BaseModel):
    """Payload for a stream message.

    Attributes:
        data: Content of a data frame.
        error: Error payload, which may be typed as RpcError in the future.
        control: Optional control metadata for the stream.
    """

    data: Any | None = None
    error: Any | None = None
    control: StreamControl | None = None


class StreamMessage(BaseModel):
    """Wire format for stream messages in protocol v2.0.

    Attributes:
        type: Message type for this frame.
        sequence: Monotonic sequence number starting at 0.
        payload: Optional payload for data, error, or control info.
        timestamp_ms: Unix timestamp in milliseconds for this frame.
    """

    type: StreamMessageType
    sequence: int
    payload: StreamPayload | None = None
    timestamp_ms: int

    @field_validator("sequence")
    @classmethod
    def validate_sequence(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sequence must be greater than or equal to 0")
        return value


__all__ = [
    "StreamControl",
    "StreamMessage",
    "StreamMessageType",
    "StreamPayload",
    "StreamState",
]
