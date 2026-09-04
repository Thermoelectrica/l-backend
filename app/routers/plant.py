"""Plant router - implements new API design principles"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.auth import get_token_payload
from app.dependencies.ownership import get_ownership_validator
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.auth import TokenPayload
from app.models.inspector import AccessLevel
from app.models.plant import Plant, PlantListResponse
from app.repositories.plant import PlantRepository
from app.services.ownership_validator import OwnershipValidator
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plant", tags=["plant"])
plant_repo = PlantRepository()


@router.get("/all", response_model=PlantListResponse)
async def get_all_plants(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return plants modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all plant IDs (lightweight list), optionally filtered by modification date and accessible to current user"""
    all_plants = await plant_repo.get_all(conn, modified_since=modified_since)

    # Filter to only plants accessible to current user
    accessible_ids = await permission_service.filter_accessible_plants([p.id for p in all_plants.items])
    accessible_plants = [p for p in all_plants.items if p.id in accessible_ids]

    return PlantListResponse(items=accessible_plants)


@router.get("/by_id/{plant_id}", response_model=Plant)
async def get_plant_by_id(
    plant_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get specific plant with facilities and equipment IDs"""
    # Check plant access
    await permission_service.require_plant_access(plant_id)

    plant = await plant_repo.get_by_id(conn, plant_id)
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.put("", response_model=Plant)
async def upsert_plant(
    plant: Plant,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and mark extra children as deleted",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    ownership_validator: OwnershipValidator = Depends(get_ownership_validator),
):
    """
    Create or replace plant with facilities.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing plants
      - Rejects if extra child facilities exist on server (409)
      - Ignores server_modified_at for new plants
    - force=true:
      - Ignores server_modified_at validation
      - Marks extra child facilities as deleted
    - Never allows "stealing" facilities from other plants
    - Pessimistic lock: Only the user who claimed the plant can modify it
    - Permission: User must have access to the plant
    - New plants become accessible to all active internal inspectors with MODIFY access
      level or higher, plus the creator (who may be external)
    - created_by_user_id is set by the server on creation and cannot be changed by clients
    """
    try:
        async with conn.transaction():
            # Check access level (MODIFY required)
            permission_service.require_access_level(AccessLevel.MODIFY)

            # Check if plant exists
            existing_plant = await plant_repo.get_by_id(conn, plant.id)
            is_new_plant = existing_plant is None

            # For existing plants, check plant access
            # For new plants, we'll grant access after creation
            if not is_new_plant:
                await permission_service.require_plant_access(plant.id)

            # Validate ownership before saving
            await ownership_validator.validate_plant_ownership(plant)

            # created_by_user_id is server-authoritative: discard whatever the client sent.
            # Anonymous user (auth disabled) has no inspector row, so leave the creator NULL.
            if existing_plant is None:
                creator_id = permission_service.current_user.id
                plant.created_by_user_id = creator_id if creator_id != -1 else None
            else:
                plant.created_by_user_id = existing_plant.created_by_user_id

            result = await plant_repo.save(conn, plant, force=force)

            if is_new_plant:
                # Internal MODIFY+ inspectors see every new plant.
                await permission_service.grant_plant_access_to_internal_inspectors(plant.id)
                # The broadcast above skips external creators, so grant the creator explicitly.
                # No-op for internal creators (ON CONFLICT DO NOTHING) and for anonymous (id == -1).
                await permission_service.grant_plant_access(plant.id)

        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for plant",
            extra={
                "plant_id": str(plant.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning("Invalid plant data", extra={"plant_id": str(plant.id), "error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/by_id/{plant_id}/claim", response_model=Plant)
async def claim_plant(
    plant_id: UUID,
    token_payload: TokenPayload = Depends(get_token_payload),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Claim plant for editing (user_id and device_id extracted from auth token).

    Allows claiming if:
    - Plant is not claimed
    - Plant is already claimed by the same user
    - Claim is stale (expired at 3:00 AM Moscow time)

    Returns 409 if plant is claimed by another user and claim is not stale.
    Returns the updated plant state with claim information.
    Permission: User must already have access to the plant.
    """
    # Check access level (MODIFY required)
    permission_service.require_access_level(AccessLevel.MODIFY)

    # Claiming must not confer access: it would let anyone who can guess a plant UUID escape
    # the plant list they were granted. External users are limited to a predefined list.
    await permission_service.require_plant_access(plant_id)

    async with conn.transaction():
        success = await plant_repo.claim(
            conn,
            plant_id,
            token_payload.dev,  # device_id from token
            token_payload.sub,  # user_id (inspector_id) from token
        )

    if success is None:
        raise HTTPException(status_code=404, detail="Plant not found")

    if not success:
        # Get plant info for better error message
        plant = await plant_repo.get_by_id(conn, plant_id)
        from datetime import datetime, timezone

        from app.models import ConflictDetail, ConflictError

        raise HTTPException(
            status_code=409,
            detail=ConflictError(
                message="Plant is claimed by another user and claim is not stale",
                server_modified_at=plant.server_modified_at if plant else datetime.now(timezone.utc),
                conflicts=[
                    ConflictDetail(
                        field="claimed_by_user_id",
                        message=(
                            f"Plant is claimed by user {plant.claimed_by_user_id if plant else 'unknown'}"
                            " and claim has not expired yet"
                        ),
                    )
                ],
            ).model_dump(mode="json"),
        )

    # Return the updated plant state
    plant = await plant_repo.get_by_id(conn, plant_id)
    if not plant:
        raise HTTPException(status_code=400, detail="Plant not found after claim")
    return plant


@router.post("/by_id/{plant_id}/release", response_model=Plant)
async def release_plant(
    plant_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Release plant claim.

    Returns the updated plant state with cleared claim information.
    Permission: User must already have access to the plant.
    """
    # Check access level (MODIFY required)
    permission_service.require_access_level(AccessLevel.MODIFY)

    # Releasing must not confer access either - same reasoning as claim.
    await permission_service.require_plant_access(plant_id)

    async with conn.transaction():
        success = await plant_repo.release(conn, plant_id)

    if not success:
        raise HTTPException(status_code=404, detail="Plant not found")

    # Return the updated plant state
    plant = await plant_repo.get_by_id(conn, plant_id)
    if not plant:
        raise HTTPException(status_code=400, detail="Plant not found after release")
    return plant
