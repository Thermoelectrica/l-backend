"""EntityProperty aggregate models"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EntityType(str, Enum):
    """Kind of entity an EntityProperty row describes."""

    PLANT = "plant"
    FACILITY = "facility"
    EQUIPMENT = "equipment"


class EntityProperty(BaseModel):
    """EntityProperty aggregate root.

    One row per entity at most, keyed by the entity's own id. Holds the entity attributes
    that can be changed without claiming the plant, so there is no surrogate id for the client to
    generate: entity_id identifies both the aggregate and the entity it describes, and entity_type
    says which aggregate that id belongs to (there is no FK between aggregates, so the id alone is
    not self-describing).
    """

    entity_id: UUID
    entity_type: EntityType
    inspection_schedule_id: Optional[int] = None
    # Optional so the same model can carry a not-yet-persisted aggregate: a create PUT sends null,
    # and GET /by_id returns null for an entity that has no properties row yet.
    server_modified_at: Optional[datetime] = None


class EntityPropertyListResponse(BaseModel):
    """Wrapped response for entity property list with items key"""

    # No lightweight list item model here: the aggregate is already two attributes wide, so there is
    # nothing a list projection could usefully leave out.
    items: list[EntityProperty]
