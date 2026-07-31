"""Ownership validation service for plant, equipment, and inspection aggregates"""

import logging

from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.equipment import Equipment
from app.models.inspection import Inspection
from app.models.inspector import Inspector
from app.models.plant import Plant
from app.models.work_log import WorkLog
from app.repositories.equipment import EquipmentRepository
from app.repositories.equipment import queries as equipment_queries
from app.repositories.inspection import (
    InspectionRepository,
)
from app.repositories.plant import PlantRepository
from app.repositories.work_log import WorkLogRepository

logger = logging.getLogger(__name__)


class OwnershipValidator:
    """
    Service to validate ownership of plant, equipment, and inspection aggregates.
    Checks if a user has the right to modify an aggregate based on claim ownership or creator ownership.
    """

    def __init__(self, conn, current_user: Inspector, device_id: str) -> None:
        """
        Initialize the ownership validator with a database connection, current user, and device ID.

        Args:
            conn: Database connection to use for validation queries
            current_user: Current authenticated user
            device_id: Device ID from the authentication token
        """
        self.conn = conn
        self.current_user = current_user
        self.device_id = device_id
        self.plant_repo = PlantRepository()
        self.equipment_repo = EquipmentRepository()
        self.inspection_repo = InspectionRepository()
        self.work_log_repo = WorkLogRepository()

    async def validate_plant_ownership(self, plant: Plant) -> None:
        """
        Validate that the plant is claimed by the current device.
        Pessimistic locks are never bypassed, only by anonymous user (when auth is disabled).

        Args:
            plant: Plant to validate

        Raises:
            ConcurrentModificationError: If plant is not claimed by current device
        """
        # Skip validation only for anonymous user (when auth is disabled)
        if self.current_user.id == -1:
            return

        current = await self.plant_repo.get_by_id(self.conn, plant.id)
        if not current:
            return  # New plant, no validation needed

        # Check claim ownership by device_id
        if current.claimed_by_device_id is None:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Plant must be claimed before modification",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="claimed_by_device_id",
                            message="Plant is not claimed by any device",
                        )
                    ],
                )
            )

        if current.claimed_by_device_id != self.device_id:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Plant is claimed by another device",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="claimed_by_device_id",
                            message=f"Plant is claimed by device {current.claimed_by_device_id},"
                            f" not by device {self.device_id}",
                        )
                    ],
                )
            )

    async def validate_equipment_ownership(self, equipment: Equipment) -> None:
        """
        Validate that the plant (parent of equipment) is claimed by the current device.
        Pessimistic locks are never bypassed, only by anonymous user (when auth is disabled).

        Args:
            equipment: Equipment to validate

        Raises:
            ConcurrentModificationError: If plant is not claimed by current device
        """
        # Skip validation only for anonymous user (when auth is disabled)
        if self.current_user.id == -1:
            return

        current = await self.equipment_repo.get_by_id(self.conn, equipment.id)
        if not current:
            return  # New equipment, no validation needed

        # Get plant claim info for this equipment
        plant_claim_info_row = await equipment_queries.get_plant_claim_info_for_equipment(
            self.conn, equipment_id=equipment.id
        )
        if not plant_claim_info_row:
            return  # No plant found (shouldn't happen in normal flow)

        # Check claim ownership by device_id
        if plant_claim_info_row["claimed_by_device_id"] is None:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Plant must be claimed before modifying equipment",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="plant_claim",
                            message=f"Plant {plant_claim_info_row['plant_id']} is not claimed by any device",
                        )
                    ],
                )
            )

        if plant_claim_info_row["claimed_by_device_id"] != self.device_id:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Plant is claimed by another device",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="plant_claim",
                            message=f"Plant {plant_claim_info_row['plant_id']} is claimed by device"
                            f" {plant_claim_info_row['claimed_by_device_id']}, not by device {self.device_id}",
                        )
                    ],
                )
            )

    async def validate_inspection_ownership(self, inspection: Inspection) -> None:
        """
        Validate inspection ownership.
        Pessimistic locks are never bypassed, only by anonymous user (when auth is disabled).

        Args:
            inspection: Inspection to validate

        Raises:
            ConcurrentModificationError: If inspection has extra steps
        """
        # Skip validation only for anonymous user (when auth is disabled)
        if self.current_user.id == -1:
            return

        current = await self.inspection_repo.get_by_id(self.conn, inspection.id)
        if not current:
            return  # New inspection, no validation needed

        # Creator ownership check is disabled - any inspector can modify inspections

        # Check for extra steps on server
        current_step_ids = {step.id for step in current.steps if not step.is_deleted}
        incoming_step_ids = {step.id for step in inspection.steps}
        extra_step_ids = current_step_ids - incoming_step_ids

        if extra_step_ids:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Extra child entities exist on server",
                    server_modified_at=current.server_modified_at,
                    extra_child_ids=list(extra_step_ids),
                    conflicts=[
                        ConflictDetail(
                            field="steps",
                            message=f"Server has {len(extra_step_ids)} extra steps not in client request",
                        )
                    ],
                )
            )

    async def validate_work_log_ownership(self, work_log: WorkLog) -> None:
        """
        Validate that the work log is owned by the current user.
        Pessimistic locks are never bypassed, only by anonymous user (when auth is disabled).

        Args:
            work_log: Work log to validate

        Raises:
            ConcurrentModificationError: If work log is not owned by current user
        """
        # Skip validation only for anonymous user (when auth is disabled)
        if self.current_user.id == -1:
            return

        current = await self.work_log_repo.get_by_id(self.conn, work_log.id)
        if not current:
            return  # New work log, no validation needed

        # Check ownership by inspector_id (who created the work log)
        if current.inspector_id is None:
            raise ConcurrentModificationError(
                ConflictError(
                    message="Work log must have an assigned inspector",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="inspector_id",
                            message="Work log has no inspector assigned",
                        )
                    ],
                )
            )

        if current.inspector_id != self.current_user.id:
            assert current.server_modified_at is not None
            raise ConcurrentModificationError(
                ConflictError(
                    message="Work log is owned by another user",
                    server_modified_at=current.server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="inspector_id",
                            message=f"Work log is owned by inspector {current.inspector_id},"
                            f" not by user {self.current_user.id}",
                        )
                    ],
                )
            )
