"""Stickers repository"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.sticker_installation import (
    StickerInstallaionListItem, 
    StickerInstallationModel,
)
from app.utils.async_wrapper import AsyncWrapper

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/sticker_installation.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class StickerInstallationRepository:
    """Repository of Stickers methods"""

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> List[StickerInstallaionListItem]:
        """Get all stickers, optionally filtered by modification date"""
        
        sticker_rows = [row async for row in queries.get_all_stickers(conn, modified_since=modified_since)] # type: ignore
        sticker_list = [StickerInstallaionListItem(**row) for row in sticker_rows]
        return sticker_list

    
    async def get_by_id(self, conn, sticker_id: UUID) -> Optional[StickerInstallationModel]:
        """Get sticker by id"""
        
        sticker_row = await queries.get_by_id(conn, id=sticker_id)
        if not sticker_row:
            return None
        return StickerInstallationModel(**sticker_row)

    
    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[StickerInstallationModel]:
        """Get all stickers by plant_id"""

        sticker_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]

        if not sticker_rows:
            return []
        return [StickerInstallationModel(**row) for row in sticker_rows]
    
    async def save(self, conn, sticker: StickerInstallationModel, force: bool = False) -> StickerInstallationModel:
        """
        Save sticker to database
        """

        # Список полей, которые нельзя менять
        immutable_fields = ["control_point_id", "inspector_id", "kind", "sticker_type_id", "sticker_color", "from_sticker_type_id", "count"]

        # 1. Подготовить данные
        data = sticker.model_dump(exclude={"server_modified_at"})
    
        # 2. Если kind/sticker_color — enum, распаковать .value
        if hasattr(sticker.kind, "value"):
            data["kind"] = sticker.kind.value
        if hasattr(sticker.sticker_color, "value"):
            data["sticker_color"] = sticker.sticker_color.value

        # 3. Вставить данные в таблицу
        await queries.upsert_sticker(conn, **data) # type: ignore
        
        # 4. Получить сохранённую запись
        result = await queries.get_by_id(conn, id=sticker.id)
        
        if not result:
            raise ValueError(f"Sticker {sticker.id} not found after save")
        
        if result.get("id") == data.get("id"):
            # Сравнение
            for field in immutable_fields:
                if field in data and field in result:
                    new_val = data[field]
                    old_val = result[field]

                    # Если enum — сравнить .value
                    if hasattr(new_val, "value"):
                        new_val = new_val.value
                    if hasattr(old_val, "value"):
                        old_val = old_val.value

                    if new_val != old_val:
                        raise ConcurrentModificationError(
                            ConflictError(
                                message=f"Cannot modify sticker {sticker.id}",
                                server_modified_at=result["server_modified_at"], # type: ignore
                                conflicts=[
                                    ConflictDetail(
                                        field=f"{field}",
                                        message=f"Forbidden change {field} from {old_val} to {new_val}",
                                    )
                                ],
                            )
                        )
        
        return StickerInstallationModel(**result)
    