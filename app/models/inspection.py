"""Inspection aggregate models"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InspectionStatus(str, Enum):
    """Inspection status enum"""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class InspectionStepType(str, Enum):
    """Inspection step type enum"""

    GENERAL_INSPECTION = "GENERAL_INSPECTION"
    DEFECT_REPORT = "DEFECT_REPORT"
    DEFECT_FOLLOW_UP = "DEFECT_FOLLOW_UP"
    DEFECT_UNDECIDED = "DEFECT_UNDECIDED"


class StepStatus(str, Enum):
    """Step status enum"""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FORCE_COMPLETED = "FORCE_COMPLETED"


class ImageLink(BaseModel):
    """Image link within inspection step (child entity)"""

    image_id: UUID
    is_deleted: bool = False


class InspectionStep(BaseModel):
    """Inspection step within inspection (child entity)"""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    started_at: datetime
    step_number: int
    step_type: InspectionStepType
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
    step_status: Optional[StepStatus] = None
    is_deleted: bool = False
    image_links: list[ImageLink] = Field(default_factory=list)

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


class Inspection(BaseModel):
    """Inspection aggregate root"""

    id: UUID
    equipment_id: UUID
    inspector_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: InspectionStatus = InspectionStatus.PLANNED
    is_deleted: bool = False
    server_modified_at: datetime
    steps: list[InspectionStep] = Field(default_factory=list)


class InspectionListItem(BaseModel):
    """Lightweight inspection item for list view"""

    id: UUID
    equipment_id: UUID
    inspector_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: InspectionStatus
    is_deleted: bool


class InspectionListResponse(BaseModel):
    """Wrapped response for inspection list with items key"""

    items: list[InspectionListItem]
