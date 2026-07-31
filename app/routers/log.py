"""Log router"""

from fastapi import APIRouter, Depends

from app.database import get_db_connection
from app.models.log import LogEntry
from app.repositories.log import LogRepository

router = APIRouter(prefix="/log", tags=["log"])
log_repo = LogRepository()


@router.post("", status_code=201)
async def create_logs(logs: list[LogEntry], conn=Depends(get_db_connection)):
    """Batch insert log entries"""
    async with conn.transaction():
        count = await log_repo.insert_batch(conn, logs)
    return {"inserted": count}
