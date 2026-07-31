"""Tests for disabling optimistic locking via configuration"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def facility_id():
    return uuid4()


@pytest.fixture
def equipment_id():
    return uuid4()


@pytest.fixture
def defect_id():
    return uuid4()


@pytest.fixture
def disable_optimistic_locking(monkeypatch):
    """Fixture to temporarily disable optimistic locking"""
    monkeypatch.setattr(settings, "disable_optimistic_locking", True)
    yield
    monkeypatch.setattr(settings, "disable_optimistic_locking", False)


@pytest.fixture
def setup_plant_and_equipment(client: TestClient, plant_id, facility_id, equipment_id):
    """Setup plant and equipment for tests"""
    # Create plant
    plant_data = {
        "id": str(plant_id),
        "name": "Test Plant",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [
            {
                "id": str(facility_id),
                "name": "Test Facility",
                "is_deleted": False,
            }
        ],
    }
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    # Create equipment
    equipment_data = {
        "id": str(equipment_id),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Test Equipment",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }
    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200


def test_defect_update_with_stale_timestamp_when_disabled(
    client: TestClient,
    defect_id,
    equipment_id,
    setup_plant_and_equipment,
    disable_optimistic_locking,
):
    """Test that defect can be updated with stale server_modified_at when optimistic locking is disabled"""
    # Create initial defect
    defect_data = {
        "id": str(defect_id),
        "equipment_id": str(equipment_id),
        "unit_name": "Test Unit",
        "defect_type_id": None,
        "detected_at": "2024-01-01T00:00:00Z",
        "resolved_at": None,
        "status": "DETECTED",
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200
    created_defect = response.json()
    server_timestamp = created_defect["server_modified_at"]

    # Update defect with stale timestamp (should succeed when optimistic locking is disabled)
    defect_data["status"] = "RESOLVED"
    defect_data["resolved_at"] = "2024-01-02T00:00:00Z"
    defect_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Stale timestamp

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200
    updated_defect = response.json()
    assert updated_defect["status"] == "RESOLVED"
    assert updated_defect["resolved_at"] == "2024-01-02T00:00:00Z"
    # Server should have updated the timestamp
    assert updated_defect["server_modified_at"] != server_timestamp


def test_plant_update_with_stale_timestamp_when_disabled(
    client: TestClient,
    plant_id,
    facility_id,
    disable_optimistic_locking,
):
    """Test that plant can be updated with stale server_modified_at when optimistic locking is disabled"""
    # Create initial plant
    plant_data = {
        "id": str(plant_id),
        "name": "Original Plant Name",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [
            {
                "id": str(facility_id),
                "name": "Test Facility",
                "is_deleted": False,
            }
        ],
    }
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200
    created_plant = response.json()
    server_timestamp = created_plant["server_modified_at"]

    # Update plant with stale timestamp (should succeed when optimistic locking is disabled)
    plant_data["name"] = "Updated Plant Name"
    plant_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Stale timestamp

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200
    updated_plant = response.json()
    assert updated_plant["name"] == "Updated Plant Name"
    # Server should have updated the timestamp
    assert updated_plant["server_modified_at"] != server_timestamp


def test_equipment_update_with_stale_timestamp_when_disabled(
    client: TestClient,
    equipment_id,
    facility_id,
    plant_id,
    disable_optimistic_locking,
):
    """Test that equipment can be updated with stale server_modified_at when optimistic locking is disabled"""
    # Create plant and facility first
    plant_data = {
        "id": str(plant_id),
        "name": "Test Plant",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [
            {
                "id": str(facility_id),
                "name": "Test Facility",
                "is_deleted": False,
            }
        ],
    }
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    # Create initial equipment
    equipment_data = {
        "id": str(equipment_id),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Original Equipment Name",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }
    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200
    created_equipment = response.json()
    server_timestamp = created_equipment["server_modified_at"]

    # Update equipment with stale timestamp (should succeed when optimistic locking is disabled)
    equipment_data["name"] = "Updated Equipment Name"
    equipment_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Stale timestamp

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200
    updated_equipment = response.json()
    assert updated_equipment["name"] == "Updated Equipment Name"
    # Server should have updated the timestamp
    assert updated_equipment["server_modified_at"] != server_timestamp


def test_defect_update_with_stale_timestamp_when_enabled(
    client: TestClient,
    defect_id,
    equipment_id,
    setup_plant_and_equipment,
):
    """Test that defect update with stale timestamp fails when optimistic locking is enabled (default)"""
    # Create initial defect
    defect_data = {
        "id": str(defect_id),
        "equipment_id": str(equipment_id),
        "unit_name": "Test Unit",
        "defect_type_id": None,
        "detected_at": "2024-01-01T00:00:00Z",
        "resolved_at": None,
        "status": "DETECTED",
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    # Update defect with stale timestamp (should fail when optimistic locking is enabled)
    defect_data["status"] = "RESOLVED"
    defect_data["resolved_at"] = "2024-01-02T00:00:00Z"
    defect_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Stale timestamp

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 409  # Conflict
    error_data = response.json()
    # Error data is nested under 'detail' key
    assert "detail" in error_data
    detail = error_data["detail"]
    assert "server_modified_at" in detail
    assert detail["message"] == "Defect was modified by another client"


def test_force_parameter_still_works_when_locking_enabled(
    client: TestClient,
    defect_id,
    equipment_id,
    setup_plant_and_equipment,
):
    """Test that force parameter still bypasses optimistic locking even when global flag is not set"""
    # Create initial defect
    defect_data = {
        "id": str(defect_id),
        "equipment_id": str(equipment_id),
        "unit_name": "Test Unit",
        "defect_type_id": None,
        "detected_at": "2024-01-01T00:00:00Z",
        "resolved_at": None,
        "status": "DETECTED",
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    # Update defect with stale timestamp using force parameter
    defect_data["status"] = "RESOLVED"
    defect_data["resolved_at"] = "2024-01-02T00:00:00Z"
    defect_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Stale timestamp

    response = client.put("/defect?force=true", json=defect_data)
    assert response.status_code == 200
    updated_defect = response.json()
    assert updated_defect["status"] == "RESOLVED"


def test_defect_update_without_timestamp_when_disabled(
    client: TestClient,
    defect_id,
    equipment_id,
    setup_plant_and_equipment,
    disable_optimistic_locking,
):
    """Test that defect can be updated without server_modified_at when optimistic locking is disabled"""
    # Create initial defect
    defect_data = {
        "id": str(defect_id),
        "equipment_id": str(equipment_id),
        "unit_name": "Test Unit",
        "defect_type_id": None,
        "detected_at": "2024-01-01T00:00:00Z",
        "resolved_at": None,
        "status": "DETECTED",
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    # Update defect without server_modified_at (should succeed when optimistic locking is disabled)
    defect_data["status"] = "RESOLVED"
    defect_data["resolved_at"] = "2024-01-02T00:00:00Z"
    defect_data["server_modified_at"] = None  # No timestamp

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200
    updated_defect = response.json()
    assert updated_defect["status"] == "RESOLVED"
    assert updated_defect["server_modified_at"] is not None  # Server assigns new timestamp
