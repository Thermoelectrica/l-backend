"""StickerType router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.sticker_type import StickerTypeListResponse
from app.repositories.sticker_type import StickerTypeRepository

router = APIRouter(prefix="/sticker-type", tags=["sticker-type"])
sticker_type_repo = StickerTypeRepository()


@router.get("/all", response_model=StickerTypeListResponse)
async def get_all_sticker_types(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return sticker types modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all sticker types with temperature ranges, optionally filtered by modification date"""
    sticker_types = await sticker_type_repo.get_all(conn, modified_since=modified_since)
    return StickerTypeListResponse(items=sticker_types)
