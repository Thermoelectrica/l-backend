"""Verification router - online-only review/approval workflow for inspection steps"""

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.inspection import InspectionStepType
from app.models.inspector import AccessLevel, Inspector
from app.models.verification import (
    CreateVerificationRequest,
    ReviewVerificationRequest,
    Verification,
    VerificationImageLink,
    VerificationListResponse,
    VerificationStatus,
)
from app.repositories.verification import VerificationRepository
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/verification", tags=["verification"])
verification_repo = VerificationRepository()


@router.post("", response_model=Verification)
async def create_verification(
    request: CreateVerificationRequest,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """
    Create and submit a new verification for an inspection step.

    Copies inspection step data to verification aggregate, assigns verifier, auto-submits.
    Requires INSPECT access level and plant access for the step's plant.
    """
    try:
        async with conn.transaction():
            # Check INSPECT access level
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Get inspection step data
            step_data = await verification_repo.get_inspection_step_data(
                conn, step_id=request.inspection_step_id
            )

            if not step_data:
                raise HTTPException(status_code=400, detail="Inspection step not found")

            # Check if step is deleted
            if step_data.get("is_deleted"):
                raise HTTPException(status_code=400, detail="Cannot create verification for deleted step")

            # Validate step type
            step_type = step_data["step_type"]
            if step_type not in (
                InspectionStepType.DEFECT_REPORT.value,
                InspectionStepType.DEFECT_FOLLOW_UP.value,
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Verification only supported for DEFECT_REPORT and DEFECT_FOLLOW_UP steps, got {step_type}",
                )

            # Check plant access
            plant_id = step_data["plant_id"]
            await permission_service.require_plant_access(plant_id)

            # Check for active verification
            active = await verification_repo.get_active_verification_by_step(
                conn, inspection_step_id=request.inspection_step_id
            )
            if active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Active verification already exists for this step (status: {active['status']})",
                )

            # Validate verifier
            verifier_data = await verification_repo.get_inspector_info(
                conn, inspector_id=request.verifier_id
            )

            if not verifier_data:
                raise HTTPException(status_code=400, detail="Verifier not found")

            if verifier_data.get("is_deleted"):
                raise HTTPException(status_code=400, detail="Verifier is deleted")

            if verifier_data["access_level"] != AccessLevel.VERIFY.value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Verifier must have VERIFY access level, has {verifier_data['access_level']}",
                )

            # Prevent self-verification
            if request.verifier_id == current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot assign yourself as verifier (self-verification not allowed)",
                )

            # Get inspection step image links
            image_link_rows = await verification_repo.get_inspection_step_image_links(
                conn, step_id=request.inspection_step_id
            )

            # Create verification
            image_links = [
                VerificationImageLink(image_id=row["image_id"], is_deleted=row.get("is_deleted", False))
                for row in image_link_rows
            ]

            verification = Verification(
                id=uuid4(),
                inspection_step_id=request.inspection_step_id,
                plant_id=plant_id,
                inspector_id=current_user.id,
                verifier_id=request.verifier_id,
                status=VerificationStatus.SUBMITTED,
                server_modified_at=datetime.now(timezone.utc),
                step_type=step_data["step_type"],
                defect_id=step_data.get("defect_id"),
                unit_name=step_data.get("unit_name"),
                description=step_data.get("description"),
                is_resolved=step_data.get("is_resolved"),
                sticker_type_id=step_data.get("sticker_type_id"),
                t_sticker=step_data.get("t_sticker"),
                t_environment=step_data.get("t_environment"),
                t_similar_unit=step_data.get("t_similar_unit"),
                epsilon=step_data.get("epsilon", 0.95),
                t_observed=step_data.get("t_observed"),
                measured_current=step_data.get("measured_current"),
                nominal_current=step_data.get("nominal_current"),
                defect_type_id=step_data.get("defect_type_id"),
                is_sticker_present=step_data.get("is_sticker_present"),
                is_test_ready=step_data.get("is_test_ready"),
                is_attention_required=step_data.get("is_attention_required", False),
                image_links=image_links,
                events=[],
            )

            result = await verification_repo.create(conn, verification, image_links)
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create verification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create verification: {str(e)}")


@router.get("/by_id/{verification_id}", response_model=Verification)
async def get_verification_by_id(
    verification_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get verification by ID with image links and events"""
    verification = await verification_repo.get_by_id(conn, verification_id)

    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    # Check plant access
    await permission_service.require_plant_access(verification.plant_id)

    return verification


@router.get("/submitted_by_me", response_model=VerificationListResponse)
async def get_verifications_submitted_by_me(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return verifications modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """Get all verifications submitted by current user, optionally filtered by modification date"""
    permission_service.require_access_level(AccessLevel.READ)

    verifications = await verification_repo.get_by_inspector(
        conn, inspector_id=current_user.id, modified_since=modified_since
    )

    # Filter by plant access
    accessible_items = []
    for verification in verifications.items:
        if await permission_service.check_plant_access(verification.plant_id):
            accessible_items.append(verification)

    return VerificationListResponse(items=accessible_items)


@router.get("/assigned_to_me", response_model=VerificationListResponse)
async def get_verifications_assigned_to_me(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return verifications modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """Get all verifications assigned to current user as verifier, optionally filtered by modification date"""
    permission_service.require_access_level(AccessLevel.READ)

    verifications = await verification_repo.get_by_verifier(
        conn, verifier_id=current_user.id, modified_since=modified_since
    )

    # Filter by plant access
    accessible_items = []
    for verification in verifications.items:
        if await permission_service.check_plant_access(verification.plant_id):
            accessible_items.append(verification)

    return VerificationListResponse(items=accessible_items)


@router.put("", response_model=Verification)
async def update_verification(
    verification: Verification,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and mark extra image links as deleted",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """
    Update verification data and/or reassign verifier.

    Only the original inspector (verification.inspector_id == current_user.id) may update.
    Only allowed in non-terminal states (SUBMITTED, REJECTED).
    """
    try:
        async with conn.transaction():
            # Check INSPECT access level
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Get current verification
            current_verification = await verification_repo.get_by_id(conn, verification.id)

            if not current_verification:
                raise HTTPException(status_code=404, detail="Verification not found")

            # Check plant access
            await permission_service.require_plant_access(current_verification.plant_id)

            # Check ownership
            if current_verification.inspector_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the original inspector can update verification",
                )

            # Check status
            if current_verification.status == VerificationStatus.APPROVED:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot update approved verification",
                )

            # If verifier changed, validate new verifier
            if verification.verifier_id != current_verification.verifier_id:
                verifier_data = await verification_repo.get_inspector_info(
                    conn, inspector_id=verification.verifier_id
                )

                if not verifier_data:
                    raise HTTPException(status_code=400, detail="Verifier not found")

                if verifier_data.get("is_deleted"):
                    raise HTTPException(status_code=400, detail="Verifier is deleted")

                if verifier_data["access_level"] != AccessLevel.VERIFY.value:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Verifier must have VERIFY access level, has {verifier_data['access_level']}",
                    )

                # Prevent self-verification
                if verification.verifier_id == current_verification.inspector_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Cannot assign inspector as verifier (self-verification not allowed)",
                    )

            # Update verification
            result = await verification_repo.update(
                conn, verification, current_verification, force=force
            )
            return result

    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for verification",
            extra={
                "verification_id": str(verification.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update verification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update verification: {str(e)}")


@router.post("/by_id/{verification_id}/review", response_model=Verification)
async def review_verification(
    verification_id: UUID,
    request: ReviewVerificationRequest,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """
    Approve or reject a verification.

    Requires VERIFY access level and must be the assigned verifier.
    Only allowed when verification is in SUBMITTED state.
    """
    try:
        async with conn.transaction():
            # Check VERIFY access level
            permission_service.require_access_level(AccessLevel.VERIFY)

            # Get current verification
            current_verification = await verification_repo.get_by_id(conn, verification_id)

            if not current_verification:
                raise HTTPException(status_code=404, detail="Verification not found")

            # Check plant access
            await permission_service.require_plant_access(current_verification.plant_id)

            # Check verifier ownership
            if current_verification.verifier_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the assigned verifier can review this verification",
                )

            # Check status
            if current_verification.status != VerificationStatus.SUBMITTED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Can only review SUBMITTED verifications, current status: {current_verification.status.value}",
                )

            # Validate comment for rejection
            if not request.approved and not request.comment:
                raise HTTPException(
                    status_code=400,
                    detail="Comment is required when rejecting a verification",
                )

            # Update status
            new_status = VerificationStatus.APPROVED if request.approved else VerificationStatus.REJECTED
            updated_verification = await verification_repo.update_status(
                conn,
                verification_id=verification_id,
                new_status=new_status,
                server_modified_at=request.server_modified_at,
                inspector_id=current_user.id,
                comment=request.comment,
            )

            # If approved, copy back to inspection step
            if request.approved:
                await verification_repo.copy_back_to_inspection_step(
                    conn, updated_verification, verified_at=datetime.now(timezone.utc)
                )

            return updated_verification

    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected during review",
            extra={
                "verification_id": str(verification_id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review verification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to review verification: {str(e)}")


@router.post("/by_id/{verification_id}/resubmit", response_model=Verification)
async def resubmit_verification(
    verification_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    current_user: Inspector = Depends(get_current_user),
):
    """
    Resubmit a rejected verification (REJECTED → SUBMITTED).

    Only the original inspector can resubmit.
    """
    try:
        async with conn.transaction():
            # Check INSPECT access level
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Get current verification
            current_verification = await verification_repo.get_by_id(conn, verification_id)

            if not current_verification:
                raise HTTPException(status_code=404, detail="Verification not found")

            # Check plant access
            await permission_service.require_plant_access(current_verification.plant_id)

            # Check ownership
            if current_verification.inspector_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the original inspector can resubmit verification",
                )

            # Check status
            if current_verification.status != VerificationStatus.REJECTED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Can only resubmit REJECTED verifications, current status: {current_verification.status.value}",
                )

            # Update status back to SUBMITTED
            updated_verification = await verification_repo.update_status(
                conn,
                verification_id=verification_id,
                new_status=VerificationStatus.SUBMITTED,
                server_modified_at=current_verification.server_modified_at,
                inspector_id=current_user.id,
                comment=None,
            )

            return updated_verification

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resubmit verification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resubmit verification: {str(e)}")
