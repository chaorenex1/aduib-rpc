import collections
from dataclasses import Field
from typing import Any

from pydantic import BaseModel, ConfigDict

State=collections.abc.MutableMapping[str, Any]

class ServerContext(BaseModel):
    """Context for the server, including configuration and state information."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    state: State = Field(default={})

    metadata: dict[str,Any] = Field(default_factory={})
