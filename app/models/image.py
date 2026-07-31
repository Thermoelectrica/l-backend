"""Image model"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ImageType(str, Enum):
    """Image type enum"""

    VISUAL = "VISUAL"
    THERMAL = "THERMAL"


class ImageUploadStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UPLOADED = "UPLOADED"
    MISSING = "MISSING"


class PresignedUploadUrlResponse(BaseModel):
    """Response model for presigned upload URL"""

    presigned_url: str
    presigned_url_expires_at: datetime


class Image(BaseModel):
    """Image aggregate"""

    id: UUID
    plant_id: UUID
    original_file_name: str
    image_type: ImageType
    metadata: Optional[dict] = None
    is_deleted: bool = False
    server_modified_at: datetime
    upload_status: ImageUploadStatus
    server_uploaded_at: Optional[datetime] = None
    presigned_url: Optional[str] = None  # Generated dynamically, not stored in DB
    presigned_url_expires_at: Optional[datetime] = None  # Expiration time for presigned URL


class PutImageRequestBody(BaseModel):
    """Image aggregate without file upload status and upload date"""

    id: UUID
    plant_id: UUID
    # HOTFIX: original_file_name is temporarily optional to handle buggy client
    # versions that omit this field in PUT /image requests. Remove this default
    # once the client is fixed and all versions in the field send the field reliably.
    original_file_name: str = "unknown.jpg"
    image_type: ImageType
    metadata: Optional[dict] = None
    is_deleted: bool = False
    server_modified_at: datetime
    presigned_url: Optional[str] = None  # Generated dynamically, not stored in DB
    presigned_url_expires_at: Optional[datetime] = None  # Expiration time for presigned URL
