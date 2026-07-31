"""Pydantic models for API and database"""

from datetime import datetime
from typing import Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class BaseError(BaseModel):
    """Base error model with type and message"""

    type: str
    message: str


class ConflictDetail(BaseModel):
    """Details about a specific conflict"""

    field: str
    message: str
    server_value: Optional[str] = None
    client_value: Optional[str] = None


class ConflictError(BaseError):
    """Conflict error response (409)"""

    type: str = "conflict"
    server_modified_at: datetime
    client_modified_at: Optional[datetime] = None
    conflicts: list[ConflictDetail] = Field(default_factory=list)
    extra_child_ids: list[Union[UUID, int]] = Field(default_factory=list)
