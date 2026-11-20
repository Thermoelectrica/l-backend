"""IESK inspection aggregate models.

A simplified inspection for plants with the IESK extension (lesiv.plant_extension, plant.extensions).
There are no steps: the record itself is the only step. Images are linked the same way as to an
inspection step (see ImageLink in app.models.inspection).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IeskImageLink(BaseModel):
    """Image link within IESK inspection (child entity)"""

    image_id: UUID
    is_deleted: bool = False


class IeskInspection(BaseModel):
    """IESK inspection aggregate root"""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    equipment_id: UUID
    inspector_id: int
    # When the inspection was created on the device. Stored on creation only, later values are ignored.
    created_at: datetime
    # Checklist marks
    oil_level: Optional[int] = None
    bugs: Optional[int] = None
    dimensions: Optional[int] = None
    locks: Optional[int] = None
    stickers: Optional[int] = None
    safety_signs: Optional[int] = None
    comment: Optional[str] = None
    is_deleted: bool = False
    server_modified_at: datetime
    image_links: list[IeskImageLink] = Field(default_factory=list)


class IeskInspectionListItem(BaseModel):
    """Lightweight IESK inspection item for list view"""

    id: UUID
    equipment_id: UUID
    inspector_id: int
    created_at: datetime
    is_deleted: bool
    server_modified_at: datetime


class IeskInspectionListResponse(BaseModel):
    """Wrapped response for IESK inspection list with items key"""

    items: list[IeskInspectionListItem]
