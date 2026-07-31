import logging
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.ownership import get_ownership_validator
from app.dependencies.permissions import get_permission_service
from app.exceptions import BusinessValidationError, ConcurrentModificationError
from app.models.inspector import AccessLevel
from app.models.work_log import (
    WorkLog,
    WorkLogListResponse,
)
from app.repositories.work_log import WorkLogRepository
from app.services.ownership_validator import OwnershipValidator
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/work_log", tags=["Work Log"])
work_log_repo = WorkLogRepository()


@router.get("/all", response_model=WorkLogListResponse)
async def get_all_work_logs(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return work logs modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
) -> WorkLogListResponse:
    """
    Get all work logs as lightweight list.
    Optionally filter by modification date and accessible plants.
    """
    all_work_logs = await work_log_repo.get_all(conn, modified_since=modified_since)

    accessible_work_logs = []
    for wl in all_work_logs.items:
        plant_id = await permission_service.get_plant_id_from_work_log(wl.id)
        if plant_id and await permission_service.check_plant_access(plant_id):
            accessible_work_logs.append(wl)

    return WorkLogListResponse(items=accessible_work_logs)


@router.get("/by_id/{work_log_id}", response_model=WorkLog)
async def get_work_log_by_id(
    work_log_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
) -> WorkLog:
    """
    Get work log by ID with inspectors.
    """
    plant_id = await permission_service.get_plant_id_from_work_log(work_log_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Work log not found")
    await permission_service.require_plant_access(plant_id)

    work_log = await work_log_repo.get_by_id(conn, work_log_id=work_log_id)

    if not work_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work log with ID {work_log_id} not found",
        )

    return work_log


@router.get("/by_plant_id/{plant_id}", response_model=List[WorkLog])
async def get_work_logs_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return work logs modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
) -> List[WorkLog]:
    """
    Get all work logs for a specific plant (full aggregates with inspectors).
    Optionally filtered by modification date.
    """
    await permission_service.require_plant_access(plant_id)

    return await work_log_repo.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)


@router.put("", response_model=WorkLog)
async def upsert_work_log(
    work_log: WorkLog,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and mark extra inspectors as deleted",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    ownership_validator: OwnershipValidator = Depends(get_ownership_validator),
) -> WorkLog:
    """
    Create or update work log with inspectors.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing work log
      - Rejects if extra inspectors exist on server (409)
      - Ignores server_modified_at for new work log
    - force=true:
      - Ignores server_modified_at validation
      - Marks extra inspectors as deleted
    - Permission: User must have access to the plant
    - Ownership validation: Only the user who created the work log can modify it
    """
    try:
        async with conn.transaction():
            permission_service.require_access_level(AccessLevel.INSPECT)

            plant_id = await permission_service.get_plant_id_from_work_log(work_log.id)
            if plant_id:
                await permission_service.require_plant_access(plant_id)

            await ownership_validator.validate_work_log_ownership(work_log)

            result = await work_log_repo.save(conn, work_log, force=force)

        return result

    except BusinessValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for work log",
            extra={
                "work_log_id": str(work_log.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid work log data",
            extra={"work_log_id": str(work_log.id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Unexpected error during work log upsert: {str(e)}",
            exc_info=True,
            extra={"work_log_id": str(work_log.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
