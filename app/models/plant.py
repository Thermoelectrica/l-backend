"""Plant aggregate models"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from app.utils.claim_utils import is_claim_stale


class ExternalPlantType(str, Enum):
    """Kind of externally managed plant. Tells the client which inspection procedure is available."""

    IESK = "iesk"  # Plant is listed in lesiv.iesk_plant -> IESK inspections (/iesk-inspection)


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
    # Derived by the server from lesiv.iesk_plant, never written from a request body - any client value is ignored.
    # None for ordinary plants.
    external_plant_type: Optional[ExternalPlantType] = None
    facilities: list[Facility] = Field(default_factory=list)

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
    # Derived by the server from lesiv.iesk_plant. None for ordinary plants.
    external_plant_type: Optional[ExternalPlantType] = None

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
