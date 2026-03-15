from typing import Any

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]
