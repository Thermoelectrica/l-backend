"""Image router - implements API design principles"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.permissions import get_permission_service
from app.models.image import (
    Image,
    ImageUploadStatus,
    PresignedUploadUrlResponse,
    PutImageRequestBody,
)
from app.models.inspector import AccessLevel
from app.models.s3_event import StorageEventPayload
from app.repositories.image import ConcurrentModificationError, ImageRepository
from app.services.permission_service import PermissionService
from app.services.s3_service import s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/image", tags=["image"])
image_repo = ImageRepository()


@router.get("/by_id/{image_id}", response_model=Image)
async def get_image_by_id(
    image_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get specific image by ID"""
    # Check plant access via image
    plant_id = await permission_service.get_plant_id_from_image(image_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Image not found")
    await permission_service.require_plant_access(plant_id)

    image = await image_repo.get_by_id(conn, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Generate presigned URL for the image
    url_result = s3_service.generate_presigned_url(image.id)
    if url_result:
        image.presigned_url, image.presigned_url_expires_at = url_result

    return image


@router.get("/by_plant_id/{plant_id}", response_model=list[Image])
async def get_images_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return images modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all images for a plant, optionally filtered by modification date"""
    # Check plant access
    await permission_service.require_plant_access(plant_id)

    images = await image_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)

    # Generate presigned URLs for all images
    for image in images:
        url_result = s3_service.generate_presigned_url(image.id)
        if url_result:
            image.presigned_url, image.presigned_url_expires_at = url_result

    return images


@router.put("", response_model=Image)
async def upsert_image(
    image_body: PutImageRequestBody,
    force: bool = Query(default=False, description="If true, ignore server_modified_at validation"),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Create or replace image.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing images
      - Ignores server_modified_at for new images
    - force=true:
      - Ignores server_modified_at validation
    - Logical deletion via is_deleted flag (not implemented yet)
    - Permission: User must have access to the plant
    """
    # Convert PutImageRequestBody to Image with default upload status fields.
    # upload_status and server_uploaded_at are not settable via PUT — the repo
    # will preserve the existing values for updates, or use defaults for inserts.
    image = Image(
        id=image_body.id,
        plant_id=image_body.plant_id,
        original_file_name=image_body.original_file_name,
        image_type=image_body.image_type,
        metadata=image_body.metadata,
        is_deleted=image_body.is_deleted,
        server_modified_at=image_body.server_modified_at,
        upload_status=ImageUploadStatus.UNKNOWN,  # This is correct, see repo query
    )
    try:
        async with conn.transaction():
            # Check access level (INSPECT required)
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Check plant access
            await permission_service.require_plant_access(image.plant_id)

            result = await image_repo.save(conn, image, force=force)

        # Generate upload presigned URL
        url_result = s3_service.generate_upload_presigned_url(result.id)
        if url_result:
            result.presigned_url, result.presigned_url_expires_at = url_result

        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for image",
            extra={
                "image_id": str(image.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning("Invalid image data", extra={"image_id": str(image.id), "error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{image_id}/upload_url", response_model=PresignedUploadUrlResponse)
async def get_upload_url(
    image_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Get a presigned URL for uploading an image to S3.

    This endpoint generates a PUT presigned URL that allows clients to upload
    an image directly to S3. The URL is valid for a limited time as configured
    in the S3 service settings.

    Args:
        image_id: UUID of the image to upload

    Returns:
        PresignedUploadUrlResponse with the presigned URL and expiration time

    Raises:
        HTTPException: 500 if URL generation fails
        HTTPException: 403 if user lacks plant access
    """
    # Check plant access via image
    plant_id = await permission_service.get_plant_id_from_image(image_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Image not found")
    await permission_service.require_plant_access(plant_id)

    url_result = s3_service.generate_upload_presigned_url(image_id)
    if not url_result:
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")

    presigned_url, expires_at = url_result
    return PresignedUploadUrlResponse(presigned_url=presigned_url, presigned_url_expires_at=expires_at)


@router.get("/{image_id}/exists", response_model=dict)
async def check_image_exists(
    image_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Check if an image file exists in S3 storage.

    This endpoint issues a HEAD request to S3 to verify if the image file
    exists without downloading the actual file content.

    Args:
        image_id: UUID of the image to check

    Returns:
        Dictionary with 'exists' boolean field

    Raises:
        HTTPException: 403 if user lacks plant access
    """
    # Check plant access via image
    plant_id = await permission_service.get_plant_id_from_image(image_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Image not found")
    await permission_service.require_plant_access(plant_id)

    exists = s3_service.check_exists(image_id)
    return {"exists": exists}


@router.post("/s3-upload-callback")
async def handle_s3_upload_callback(payload: StorageEventPayload, conn=Depends(get_db_connection)) -> dict:
    """
    Handle storage events from Yandex Cloud.
    Processes ObjectCreate events and updates image upload status in database.
    """
    if not payload.messages:
        logger.info("Empty messages list, skipping processing")
        return {"status": "skipped", "reason": "empty messages list"}

    processed_count = 0
    errors = []

    for idx, message in enumerate(payload.messages):
        try:
            event_metadata = message.event_metadata
            details = message.details

            if event_metadata.event_type != "yandex.cloud.events.storage.ObjectCreate":
                logger.info(f"Skipping event {idx}: not ObjectCreate event, type={event_metadata.event_type}")
                continue

            if "." in details.object_id:
                object_id = details.object_id.split(".")[0]
            else:
                object_id = details.object_id
            created_at = event_metadata.created_at

            try:
                server_uploaded_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError as e:
                logger.error(f"Error parsing created_at '{created_at}': {e}")
                errors.append(f"Event {idx}: invalid created_at format")
                continue

            await image_repo.update_upload_status(
                conn=conn,
                image_id=UUID(object_id),
                upload_status=ImageUploadStatus.UPLOADED,
                server_uploaded_at=server_uploaded_at,
            )

            processed_count += 1
            logger.info(f"Successfully processed image {object_id} with upload status 'uploaded'")

        except Exception as e:
            error_msg = f"Error processing event {idx}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    return {
        "status": "processed",
        "processed_count": processed_count,
        "total_messages": len(payload.messages),
        "errors": errors if errors else None,
    }
