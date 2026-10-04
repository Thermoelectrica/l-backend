"""Verification aggregate models"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VerificationStatus(str, Enum):
    """Verification status enum"""

    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class VerificationEventType(str, Enum):
    """Verification event type enum"""

    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REASSIGNED = "REASSIGNED"


class VerificationImageLink(BaseModel):
    """Image link within verification (child entity)"""

    image_id: UUID
    is_deleted: bool = False


class VerificationEvent(BaseModel):
    """Verification event (append-only log entry)"""

    id: UUID
    verification_id: UUID
    event_type: VerificationEventType
    inspector_id: int
    comment: Optional[str] = None
    created_at: datetime


class Verification(BaseModel):
    """Verification aggregate root"""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    inspection_step_id: UUID
    plant_id: UUID
    inspector_id: int
    verifier_id: int
    status: VerificationStatus
    server_modified_at: datetime
    is_deleted: bool = False

    # Copied fields from InspectionStep
    step_type: str  # InspectionStepType value
    defect_id: Optional[UUID] = None
    unit_name: Optional[str] = None
    description: Optional[str] = None
    is_resolved: Optional[bool] = None
    sticker_type_id: Optional[int] = None
    t_sticker: Optional[str] = None
    t_environment: Optional[Decimal] = None
    t_similar_unit: Optional[Decimal] = None
    epsilon: Decimal = Decimal("0.95")
    t_observed: Optional[Decimal] = None
    measured_current: Optional[int] = None
    nominal_current: Optional[int] = None
    defect_type_id: Optional[int] = None
    is_sticker_present: Optional[bool] = None
    is_test_ready: Optional[bool] = None
    is_attention_required: bool = False

    # Child entities
    image_links: list[VerificationImageLink] = Field(default_factory=list)
    events: list[VerificationEvent] = Field(default_factory=list)

    @field_validator("t_observed")
    @classmethod
    def validate_t_observed(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate t_observed is within DECIMAL(5,1) range: -273.15 to 9999.9"""
        if v is not None:
            if v < Decimal("-273.15") or v > Decimal("9999.9"):
                raise ValueError("t_observed must be between -273.15 and 9999.9")
        return v

    @field_validator("t_environment")
    @classmethod
    def validate_t_environment(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate t_environment is within DECIMAL(5,1) range: -273.15 to 9999.9"""
        if v is not None:
            if v < Decimal("-273.15") or v > Decimal("9999.9"):
                raise ValueError("t_environment must be between -273.15 and 9999.9")
        return v

    @field_validator("t_similar_unit")
    @classmethod
    def validate_t_similar_unit(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Validate t_similar_unit is within DECIMAL(5,1) range: -273.15 to 9999.9"""
        if v is not None:
            if v < Decimal("-273.15") or v > Decimal("9999.9"):
                raise ValueError("t_similar_unit must be between -273.15 and 9999.9")
        return v

    @field_validator("epsilon")
    @classmethod
    def validate_epsilon(cls, v: Decimal) -> Decimal:
        """Validate epsilon is within DECIMAL(3,2) range: 0 to 1 inclusive"""
        if v < Decimal("0") or v > Decimal("1"):
            raise ValueError("epsilon must be between 0 and 1 inclusive")
        return v


class VerificationListResponse(BaseModel):
    """Wrapped response for verification list with items key"""

    items: list[Verification]


class CreateVerificationRequest(BaseModel):
    """Request body for creating a verification"""

    inspection_step_id: UUID
    verifier_id: int


class ReviewVerificationRequest(BaseModel):
    """Request body for reviewing (approve/reject) a verification"""

    approved: bool
    server_modified_at: datetime
    comment: Optional[str] = None
