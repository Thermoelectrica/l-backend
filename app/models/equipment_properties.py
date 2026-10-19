"""EquipmentProperties aggregate models"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EquipmentProperties(BaseModel):
    """EquipmentProperties aggregate root.

    One row per equipment at most, keyed by the equipment's own id. Holds the equipment attributes
    that can be changed without claiming the plant, so there is no surrogate id for the client to
    generate: equipment_id identifies both the aggregate and the equipment it describes.
    """

    equipment_id: UUID
    next_inspection_date: Optional[date] = None
    # Optional so the same model can carry a not-yet-persisted aggregate: a create PUT sends null,
    # and GET /by_id returns null for equipment that has no properties row yet.
    server_modified_at: Optional[datetime] = None


class EquipmentPropertiesListResponse(BaseModel):
    """Wrapped response for equipment properties list with items key"""

    # No lightweight list item model here: the aggregate is already two attributes wide, so there is
    # nothing a list projection could usefully leave out.
    items: list[EquipmentProperties]
