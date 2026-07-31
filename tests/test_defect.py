"""Integration tests for Defect API"""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PUT_BODY_TEMPLATE = {
    "equipment_id": None,  # Will be set in fixture
    "unit_name": "Test Unit",
    "defect_type_id": None,
    "detected_at": "2024-01-01T00:00:00Z",
    "resolved_at": None,
    "status": "DETECTED",
    "is_deleted": False,
    "server_modified_at": "2024-01-01T00:00:00Z",
}


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
def setup_plant_and_equipment(client: TestClient, plant_id, facility_id, equipment_id):
    """Setup plant and equipment for defect tests"""
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
    client.put("/plant", json=plant_data)

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
    client.put("/equipment", json=equipment_data)


@pytest.fixture
def defect_data(defect_id, equipment_id):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(defect_id)
    data["equipment_id"] = str(equipment_id)
    return data


def test_create_defect(client: TestClient, defect_data, defect_id, setup_plant_and_equipment):
    """Test creating a new defect (server_modified_at ignored for new defects)"""
    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(defect_id)
    assert data["unit_name"] == "Test Unit"
    assert data["status"] == "DETECTED"
    assert "server_modified_at" in data


def test_create_defect_with_null_server_modified_at(
    client: TestClient, defect_id, equipment_id, setup_plant_and_equipment
):
    """Test creating a new defect with null server_modified_at (typical for new defects)"""
    defect_data = {
        "id": str(defect_id),
        "equipment_id": str(equipment_id),
        "unit_name": "New Defect",
        "defect_type_id": None,
        "detected_at": "2024-01-01T00:00:00Z",
        "resolved_at": None,
        "status": "DETECTED",
        "is_deleted": False,
        "server_modified_at": None,  # Null for new defects
    }

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(defect_id)
    assert data["unit_name"] == "New Defect"
    assert data["status"] == "DETECTED"
    assert data["server_modified_at"] is not None  # Server should set it


def test_get_defect(client: TestClient, defect_data, defect_id, setup_plant_and_equipment):
    """Test retrieving a defect using by_id endpoint"""
    client.put("/defect", json=defect_data)

    response = client.get(f"/defect/by_id/{defect_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(defect_id)
    assert data["unit_name"] == "Test Unit"


def test_get_nonexistent_defect(client: TestClient):
    """Test retrieving a non-existent defect"""
    defect_id = uuid4()
    response = client.get(f"/defect/by_id/{defect_id}")
    assert response.status_code == 404


def test_get_all_defects(client: TestClient, defect_data, setup_plant_and_equipment, equipment_id):
    """Test retrieving all defects using /all endpoint"""
    defect_id_2 = uuid4()

    defect_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    defect_data_2["id"] = str(defect_id_2)
    defect_data_2["equipment_id"] = str(equipment_id)
    defect_data_2["unit_name"] = "Test Unit 2"

    client.put("/defect", json=defect_data)
    client.put("/defect", json=defect_data_2)

    # Get all defects
    response = client.get("/defect/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 2

    # Check that our defects are in the list
    defect_ids = [d["id"] for d in data["items"]]
    assert str(defect_data["id"]) in defect_ids
    assert str(defect_id_2) in defect_ids


def test_get_defects_by_plant_id(client: TestClient, defect_data, plant_id, setup_plant_and_equipment):
    """Test retrieving defects by plant ID"""
    client.put("/defect", json=defect_data)

    response = client.get(f"/defect/by_plant_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Check that our defect is in the list
    defect_ids = [d["id"] for d in data]
    assert str(defect_data["id"]) in defect_ids


def test_update_defect_with_correct_timestamp(client: TestClient, defect_data, setup_plant_and_equipment):
    """Test updating a defect with correct server_modified_at"""
    create_response = client.put("/defect", json=defect_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Update with correct timestamp
    defect_data["server_modified_at"] = server_modified_at
    defect_data["unit_name"] = "Updated Unit"
    defect_data["status"] = "RESOLVED"
    defect_data["resolved_at"] = "2024-01-02T00:00:00Z"

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["unit_name"] == "Updated Unit"
    assert data["status"] == "RESOLVED"
    assert data["resolved_at"] is not None
    assert data["server_modified_at"] != server_modified_at


def test_concurrent_modification_detected(client: TestClient, defect_data, setup_plant_and_equipment):
    """Test that concurrent modification is detected with 409 error"""
    create_response = client.put("/defect", json=defect_data)
    assert create_response.status_code == 200

    # Try to update with wrong timestamp
    defect_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    defect_data["unit_name"] = "Updated Unit"

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "modified by another client" in error_data["message"].lower()
    assert "server_modified_at" in error_data


def test_force_mode_ignores_timestamp(client: TestClient, defect_data, setup_plant_and_equipment):
    """Test that force=true ignores server_modified_at validation"""
    client.put("/defect", json=defect_data)

    # Update with wrong timestamp but force=true
    defect_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    defect_data["unit_name"] = "Updated Unit"

    response = client.put("/defect?force=true", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["unit_name"] == "Updated Unit"


def test_defect_with_defect_type_id(client: TestClient, defect_data, setup_plant_and_equipment):
    """Test creating a defect with defect_type_id"""
    defect_data["defect_type_id"] = 1

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["defect_type_id"] == 1


def test_is_deleted_honored_for_defect(client: TestClient, defect_data, setup_plant_and_equipment):
    """Test that is_deleted value is honored for defects"""
    defect_data["unit_name"] = "Deleted Defect"
    defect_data["is_deleted"] = True

    response = client.put("/defect", json=defect_data)
    assert response.status_code == 200

    data = response.json()
    assert data["is_deleted"] is True

    # Verify by retrieving
    get_response = client.get(f"/defect/by_id/{defect_data['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["is_deleted"] is True


def test_get_defects_by_plant_with_modified_since_filter(
    client: TestClient, defect_data, plant_id, setup_plant_and_equipment, equipment_id
):
    """Test filtering defects by modified_since parameter"""
    # Create first defect
    defect_id_1 = uuid4()
    defect_data["id"] = str(defect_id_1)
    defect_data["unit_name"] = "Defect One"
    response1 = client.put("/defect", json=defect_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second defect
    import time

    time.sleep(0.1)

    defect_id_2 = uuid4()
    defect_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    defect_data_2["id"] = str(defect_id_2)
    defect_data_2["equipment_id"] = str(equipment_id)
    defect_data_2["unit_name"] = "Defect Two"
    response2 = client.put("/defect", json=defect_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all defects without filter - should return both
    response = client.get(f"/defect/by_plant_id/{plant_id}")
    assert response.status_code == 200
    all_defects = response.json()
    defect_ids = [d["id"] for d in all_defects]
    assert str(defect_id_1) in defect_ids
    assert str(defect_id_2) in defect_ids

    # Get defects modified after timestamp1 - should only return defect 2
    response = client.get(f"/defect/by_plant_id/{plant_id}?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_defects = response.json()
    filtered_ids = [d["id"] for d in filtered_defects]
    assert str(defect_id_1) not in filtered_ids
    assert str(defect_id_2) in filtered_ids

    # Get defects modified after timestamp2 - should return none
    response = client.get(f"/defect/by_plant_id/{plant_id}?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_defects = response.json()
    filtered_ids = [d["id"] for d in filtered_defects]
    assert str(defect_id_1) not in filtered_ids
    assert str(defect_id_2) not in filtered_ids


def test_equipment_defects_always_empty(client: TestClient, defect_data, equipment_id, setup_plant_and_equipment):
    """Test that equipment endpoint always returns empty defects list for backwards compatibility"""
    # Create a defect via defect router
    client.put("/defect", json=defect_data)

    # Get equipment - defects should be empty
    response = client.get(f"/equipment/by_id/{equipment_id}")
    assert response.status_code == 200

    data = response.json()
    assert "defects" in data
    assert data["defects"] == []  # Should always be empty
