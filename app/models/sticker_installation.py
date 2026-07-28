"""Sticker_installation aggregate models"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StickerEventKind(str, Enum):
    """Sticker event kind enum"""

    INSTALLATION = "INSTALLATION"
    REPLACEMENT = "REPLACEMENT"
    ADJUSTMENT = "ADJUSTMENT"


class StickerColor(str, Enum):
    """Sticker color enum"""

    YELLOW = "YELLOW"
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    REFLECTIVE = "REFLECTIVE"


class StickerInstallationModel(BaseModel):
    """Sticker Installation Model"""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    control_point_id: UUID
    inspector_id: int
    kind: StickerEventKind
    sticker_type_id: int
    sticker_color: StickerColor
    from_sticker_type_id: int
    count: int
    installed_at: datetime
    server_modified_at: datetime = Field(default_factory=datetime.utcnow)


class StickerInstallaionListItem(BaseModel):
    """Lightweight sticker installation item for list view"""

    id: UUID
    control_point_id: UUID
    inspector_id: int
    kind: StickerEventKind
    sticker_type_id: int
    sticker_color: StickerColor
    from_sticker_type_id: int
    count: int
    installed_at: datetime


class StickerInstallaionListResponse(BaseModel):
    """Wrapped response for sticker installation list with items key"""

    items: list[StickerInstallaionListItem]
