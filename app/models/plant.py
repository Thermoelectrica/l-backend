"""Plant aggregate models"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, field_validator

from app.utils.claim_utils import is_claim_stale


class PlantExtensionType(str, Enum):
    """
    Extension (feature flag) that can be enabled for a plant. Mirrors the PostgreSQL enum
    lesiv.plant_extension_type: a new value needs a migration (ALTER TYPE ... ADD VALUE, in its own file)
    and a member here. Extensions are introduced on demand.
    """

    IESK = "IESK"  # Simplified IESK inspections are available (/iesk-inspection)


# Read models (returned from GET endpoints)
class Facility(BaseModel):
    """Energy facility (part of plant) - read model"""

    id: UUID
    name: str
    facility_template_id: Optional[int] = None
    is_deleted: bool = False
    equipment_ids: Optional[list[UUID]] = Field(default_factory=list)


class Plant(BaseModel):
    """Plant aggregate with facilities - read model"""

    id: UUID
    name: str
    # Set by the server on creation, never changed afterwards - any client value is ignored
    created_by_user_id: Optional[int] = None
    claimed_by_device_id: Optional[str] = None
    claimed_by_user_id: Optional[int] = None
    claimed_at: Optional[datetime] = None
    is_deleted: bool = False
    server_modified_at: datetime
    # Enabled extensions from lesiv.plant_extension. Read-only: never written from a request body,
    # any client value is ignored. Empty for ordinary plants.
    extensions: list[PlantExtensionType] = Field(default_factory=list)
    # None means the PUT client did not send a restriction. An empty list means
    # that no restriction is configured and all sticker types are permitted.
    sticker_type_ids: Optional[list[int]] | None = None
    facilities: list[Facility] = Field(default_factory=list)

    @field_validator("extensions", mode="before")
    @classmethod
    def drop_unknown_extensions(cls, v: object) -> list[PlantExtensionType]:
        """
        Plant is also the PUT body, and clients echo this field back. The value is ignored anyway,
        so unknown items (an extension from a newer server version, a client bug) are dropped
        instead of failing the whole request with 422.
        """
        if not isinstance(v, (list, tuple)):
            return []
        known: list[PlantExtensionType] = []
        for item in v:
            try:
                extension = PlantExtensionType(item)
            except ValueError:
                continue
            if extension not in known:
                known.append(extension)
        return known

    @computed_field
    @property
    def is_stale(self) -> bool:
        """
        Indicates if the claim is stale (can be overridden by another user).
        A claim becomes stale at 3:00 AM Moscow time each day.
        """
        return is_claim_stale(self.claimed_at)


# List models
class PlantListItem(BaseModel):
    """Lightweight plant item for list view"""

    id: UUID
    name: str
    created_by_user_id: Optional[int] = None
    claimed_by_device_id: Optional[str] = None
    claimed_by_user_id: Optional[int] = None
    claimed_at: Optional[datetime] = None
    is_deleted: bool = False
    server_modified_at: datetime
    # Enabled extensions from lesiv.plant_extension. Empty for ordinary plants.
    extensions: list[PlantExtensionType] = Field(default_factory=list)

    @computed_field
    @property
    def is_stale(self) -> bool:
        """
        Indicates if the claim is stale (can be overridden by another user).
        A claim becomes stale at 3:00 AM Moscow time each day.
        """
        return is_claim_stale(self.claimed_at)


class PlantListResponse(BaseModel):
    """Wrapped response for plant list with items key"""

    items: list[PlantListItem]
