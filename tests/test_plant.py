"""Integration tests for Plant API - New API Design"""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PUT_BODY_TEMPLATE = {
    "name": "Test Power Plant",
    "claimed_by_device_id": None,
    "claimed_by_user_id": None,
    "claimed_at": None,
    "server_modified_at": "2024-01-01T00:00:00Z",
    "is_deleted": False,
    "facilities": [{"name": "Building A", "is_deleted": False}],
}


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def facility_id_1():
    return uuid4()


@pytest.fixture
def facility_id_2():
    return uuid4()


@pytest.fixture
def facility_id_3():
    return uuid4()


@pytest.fixture
def plant_data(plant_id, facility_id_1):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(plant_id)
    data["facilities"][0]["id"] = str(facility_id_1)
    return data


def test_create_plant(client: TestClient, plant_data, plant_id, facility_id_1):
    """Test creating a new plant with facilities (server_modified_at ignored for new plants)"""
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(plant_id)
    assert data["name"] == "Test Power Plant"
    assert len(data["facilities"]) == 1
    assert data["facilities"][0]["id"] == str(facility_id_1)
    assert "server_modified_at" in data


def test_get_plant(client: TestClient, plant_data, plant_id):
    """Test retrieving a plant using new by_id endpoint"""
    client.put("/plant", json=plant_data)

    # Then get
    response = client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(plant_id)
    assert data["name"] == "Test Power Plant"
    assert len(data["facilities"]) == 1


def test_get_nonexistent_plant(client: TestClient):
    """Test retrieving a non-existent plant"""
    plant_id = uuid4()
    response = client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 404


def test_get_all_plants(client: TestClient, plant_data):
    """Test retrieving all plants using new /all endpoint"""
    plant_id_2 = uuid4()
    facility_id_2 = uuid4()

    plant_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    plant_data_2["id"] = str(plant_id_2)
    plant_data_2["name"] = "Plant Two"
    plant_data_2["facilities"][0]["id"] = str(facility_id_2)

    client.put("/plant", json=plant_data)
    client.put("/plant", json=plant_data_2)

    # Get all plants
    response = client.get("/plant/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 2

    # Check that our plants are in the list
    plant_ids = [p["id"] for p in data["items"]]
    assert str(plant_data["id"]) in plant_ids
    assert str(plant_id_2) in plant_ids


def test_update_plant_with_correct_timestamp(client: TestClient, plant_data, facility_id_1):
    """Test updating a plant with correct server_modified_at"""
    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Update with correct timestamp
    plant_data["server_modified_at"] = server_modified_at
    plant_data["name"] = "Updated Name"
    plant_data["facilities"][0]["name"] = "Updated Facility"

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["facilities"][0]["name"] == "Updated Facility"
    assert data["server_modified_at"] != server_modified_at  # Should be updated


def test_concurrent_modification_detected(client: TestClient, plant_data):
    """Test that concurrent modification is detected with 409 error"""
    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200

    # Try to update with wrong timestamp
    plant_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    plant_data["name"] = "Updated Name"

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "modified by another client" in error_data["message"].lower()
    assert "server_modified_at" in error_data


def test_extra_facilities_rejected_without_force(client: TestClient, plant_data, facility_id_2):
    """Test that extra facilities on server are rejected when force=false"""
    # Add second facility
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with only one facility (force=false)
    plant_data["server_modified_at"] = server_modified_at
    del plant_data["facilities"][1]

    response = client.put("/plant?force=false", json=plant_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child facilities" in error_data["message"].lower()
    assert len(error_data["extra_child_ids"]) == 1
    assert str(facility_id_2) in error_data["extra_child_ids"]


def test_extra_facilities_deleted_with_force(client: TestClient, plant_data, facility_id_2):
    """Test that extra facilities are marked as deleted when force=true"""
    # Add second facility
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    client.put("/plant", json=plant_data)

    # Update with only one facility (force=true)
    del plant_data["facilities"][1]

    response = client.put("/plant?force=true", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["facilities"]) == 2

    # Facility 1 should not be deleted
    facility_1 = next(
        (f for f in data["facilities"] if f["id"] == plant_data["facilities"][0]["id"]),
        None,
    )
    assert facility_1 is not None
    assert facility_1["is_deleted"] is False

    # Facility 2 should be marked as deleted
    facility_2 = next((f for f in data["facilities"] if f["id"] == str(facility_id_2)), None)
    assert facility_2 is not None
    assert facility_2["is_deleted"] is True


def test_missing_timestamp_for_update(client: TestClient, plant_data):
    """Test that outdated server_modified_at is rejected for existing plants"""
    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200

    # Try to update with old/wrong timestamp (simulating outdated timestamp)
    plant_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    plant_data["name"] = "Updated Name"

    response = client.put("/plant?force=false", json=plant_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert "modified by another client" in error_data["message"].lower()


def test_claim_plant(client: TestClient, plant_data, plant_id):
    """Test claiming a plant using new by_id path (user_id and device_id from token)"""
    from app.services.auth import AuthService

    plant_data["facilities"] = []
    client.put("/plant", json=plant_data)

    # Create a token with user_id and device_id
    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    # Claim plant (no body needed, user_id and device_id extracted from token)
    response = client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    # Response should contain the updated plant
    data = response.json()
    assert data["id"] == str(plant_id)
    assert data["claimed_by_device_id"] == str(device_id)
    assert data["claimed_by_user_id"] == user_id
    assert data["claimed_at"] is not None


def test_release_plant(client: TestClient, plant_data, plant_id):
    """Test releasing a plant using new by_id path"""
    device_id = uuid4()
    plant_data["facilities"] = []
    plant_data["claimed_by_device_id"] = str(device_id)
    plant_data["claimed_by_user_id"] = 1
    plant_data["claimed_at"] = "2024-01-01T00:00:00Z"

    client.put("/plant", json=plant_data)

    # Release plant
    response = client.post(f"/plant/by_id/{plant_id}/release")
    assert response.status_code == 200

    # Response should contain the updated plant
    data = response.json()
    assert data["id"] == str(plant_id)
    assert data["claimed_by_device_id"] is None
    assert data["claimed_by_user_id"] is None
    assert data["claimed_at"] is None


def test_facility_transfer_not_allowed(client: TestClient, plant_data, facility_id_1):
    """Test that transferring a facility from one plant to another is not allowed (never allow stealing)"""
    client.put("/plant", json=plant_data)

    # Try to create second plant and "steal" the facility
    plant_id_2 = uuid4()
    plant_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    plant_data_2["id"] = str(plant_id_2)
    plant_data_2["name"] = "Plant Two"
    plant_data_2["facilities"][0]["id"] = str(facility_id_1)  # Same facility ID from plant 1

    # This should fail with 400 error (stealing never allowed, even with force=true)
    response = client.put("/plant", json=plant_data_2)
    assert response.status_code == 400
    assert "cannot transfer" in response.json()["detail"].lower()


def test_force_mode_ignores_timestamp(client: TestClient, plant_data):
    """Test that force=true ignores server_modified_at validation"""
    client.put("/plant", json=plant_data)

    # Update with wrong timestamp but force=true
    plant_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    plant_data["name"] = "Updated Name"

    response = client.put("/plant?force=true", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"


def test_is_deleted_honored_for_plant(client: TestClient, plant_data):
    """Test that is_deleted value is honored for plants"""
    plant_data["name"] = "Deleted Plant"
    plant_data["is_deleted"] = True
    plant_data["facilities"] = []

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert data["is_deleted"] is True

    # Verify by retrieving
    get_response = client.get(f"/plant/by_id/{plant_data['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["is_deleted"] is True


def test_is_deleted_honored_for_facility(client: TestClient, plant_data, facility_id_2):
    """Test that is_deleted value is honored for facilities"""
    # Add second facility marked as deleted
    plant_data["facilities"].append(
        {
            "id": str(facility_id_2),
            "name": "Deleted Facility",
            "is_deleted": True,
        }
    )

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["facilities"]) == 2

    # Find facilities by ID
    facility_1 = next(
        (f for f in data["facilities"] if f["id"] == plant_data["facilities"][0]["id"]),
        None,
    )
    facility_2 = next((f for f in data["facilities"] if f["id"] == str(facility_id_2)), None)

    assert facility_1 is not None
    assert facility_1["is_deleted"] is False

    assert facility_2 is not None
    assert facility_2["is_deleted"] is True

    # Verify by retrieving
    get_response = client.get(f"/plant/by_id/{plant_data['id']}")
    assert get_response.status_code == 200

    retrieved_data = get_response.json()
    facility_1_retrieved = next(
        (f for f in retrieved_data["facilities"] if f["id"] == plant_data["facilities"][0]["id"]),
        None,
    )
    facility_2_retrieved = next((f for f in retrieved_data["facilities"] if f["id"] == str(facility_id_2)), None)

    assert facility_1_retrieved is not None
    assert facility_1_retrieved["is_deleted"] is False
    assert facility_2_retrieved is not None
    assert facility_2_retrieved["is_deleted"] is True


def test_child_aggregate_ids_in_get_response(client: TestClient, plant_data, plant_id, facility_id_1):
    """Test #1: GET response includes child aggregate IDs (equipment_ids)"""
    # Create plant with facility
    client.put("/plant", json=plant_data)

    # Create equipment for the facility
    equipment_id_1 = uuid4()
    equipment_id_2 = uuid4()

    equipment_data_1 = {
        "id": str(equipment_id_1),
        "facility_id": str(facility_id_1),
        "parent_id": str(facility_id_1),
        "name": "Motor 1",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }

    equipment_data_2 = {
        "id": str(equipment_id_2),
        "facility_id": str(facility_id_1),
        "parent_id": str(facility_id_1),
        "name": "Motor 2",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }

    client.put("/equipment", json=equipment_data_1)
    client.put("/equipment", json=equipment_data_2)

    # Get plant and verify equipment IDs are included
    response = client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert len(data["facilities"]) == 1
    facility = data["facilities"][0]
    assert "equipment_ids" in facility
    assert len(facility["equipment_ids"]) == 2
    assert str(equipment_id_1) in facility["equipment_ids"]
    assert str(equipment_id_2) in facility["equipment_ids"]


def test_mismatched_child_ids_rejection(
    client: TestClient,
    plant_data,
    facility_id_1,
    facility_id_2,
    facility_id_3,
):
    """Test #2: Reject when server and client have same count but different IDs"""
    # Create plant with 3 facilities [A, B, C]
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility B", "is_deleted": False})
    plant_data["facilities"].append({"id": str(facility_id_3), "name": "Facility C", "is_deleted": False})

    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with 3 facilities [A, B, D] - D is new, C is missing
    facility_id_d = uuid4()
    plant_data["server_modified_at"] = server_modified_at
    plant_data["facilities"][2] = {
        "id": str(facility_id_d),
        "name": "Facility D",
        "is_deleted": False,
    }

    response = client.put("/plant?force=false", json=plant_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child facilities" in error_data["message"].lower()
    assert str(facility_id_3) in error_data["extra_child_ids"]


def test_deleted_children_persist_through_updates(client: TestClient, plant_data, facility_id_2):
    """Test #3: Deleted children remain in GET response after updates"""
    # Add second facility
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    create_response = client.put("/plant", json=plant_data)
    server_modified_at = create_response.json()["server_modified_at"]

    # Mark facility 2 as deleted
    plant_data["server_modified_at"] = server_modified_at
    plant_data["facilities"][1]["is_deleted"] = True

    update_response = client.put("/plant", json=plant_data)
    assert update_response.status_code == 200
    server_modified_at = update_response.json()["server_modified_at"]

    # Do another update (just change plant name)
    plant_data["server_modified_at"] = server_modified_at
    plant_data["name"] = "Updated Plant Name"

    final_response = client.put("/plant", json=plant_data)
    assert final_response.status_code == 200

    # Verify deleted facility is still returned
    get_response = client.get(f"/plant/by_id/{plant_data['id']}")
    assert get_response.status_code == 200

    data = get_response.json()
    assert len(data["facilities"]) == 2

    deleted_facility = next((f for f in data["facilities"] if f["id"] == str(facility_id_2)), None)
    assert deleted_facility is not None
    assert deleted_facility["is_deleted"] is True


def test_force_mode_with_stealing_attempt(client: TestClient, plant_data, facility_id_1):
    """Test #4: Stealing never allowed even with force=true"""
    client.put("/plant", json=plant_data)

    # Try to steal facility with force=true
    plant_id_2 = uuid4()
    plant_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    plant_data_2["id"] = str(plant_id_2)
    plant_data_2["name"] = "Plant Two"
    plant_data_2["facilities"][0]["id"] = str(facility_id_1)

    response = client.put("/plant?force=true", json=plant_data_2)
    assert response.status_code == 400
    assert "cannot transfer" in response.json()["detail"].lower()


def test_empty_facilities_list_without_force(client: TestClient, plant_data, facility_id_2):
    """Test #5a: Updating from non-empty to empty facilities with force=false should reject"""
    # Add second facility
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with empty facilities list (force=false)
    plant_data["server_modified_at"] = server_modified_at
    plant_data["facilities"] = []

    response = client.put("/plant?force=false", json=plant_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child facilities" in error_data["message"].lower()


def test_empty_facilities_list_with_force(client: TestClient, plant_data, facility_id_2):
    """Test #5b: Updating from non-empty to empty facilities with force=true should mark all as deleted"""
    # Add second facility
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    client.put("/plant", json=plant_data)

    # Update with empty facilities list (force=true)
    plant_data["facilities"] = []

    response = client.put("/plant?force=true", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["facilities"]) == 2

    # Both facilities should be marked as deleted
    for facility in data["facilities"]:
        assert facility["is_deleted"] is True


def test_multiple_facility_operations_in_single_request(
    client: TestClient,
    plant_data,
    facility_id_1,
    facility_id_2,
    facility_id_3,
):
    """Test #6: Simultaneously add, update, and delete facilities in one PUT"""
    # Start with 2 facilities
    plant_data["facilities"].append({"id": str(facility_id_2), "name": "Facility 2", "is_deleted": False})

    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # In one request:
    # - Update facility 1 name
    # - Mark facility 2 as deleted
    # - Add new facility 3
    plant_data["server_modified_at"] = server_modified_at
    plant_data["facilities"][0]["name"] = "Updated Facility 1"
    plant_data["facilities"][1]["is_deleted"] = True
    plant_data["facilities"].append({"id": str(facility_id_3), "name": "New Facility 3", "is_deleted": False})

    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["facilities"]) == 3

    # Verify facility 1 was updated
    facility_1 = next((f for f in data["facilities"] if f["id"] == str(facility_id_1)), None)
    assert facility_1 is not None
    assert facility_1["name"] == "Updated Facility 1"
    assert facility_1["is_deleted"] is False

    # Verify facility 2 was marked as deleted
    facility_2 = next((f for f in data["facilities"] if f["id"] == str(facility_id_2)), None)
    assert facility_2 is not None
    assert facility_2["is_deleted"] is True

    # Verify facility 3 was added
    facility_3 = next((f for f in data["facilities"] if f["id"] == str(facility_id_3)), None)
    assert facility_3 is not None
    assert facility_3["name"] == "New Facility 3"
    assert facility_3["is_deleted"] is False


# Tests for modified_since filter


def test_get_all_plants_with_modified_since_filter(client: TestClient, plant_data):
    """Test filtering plants by modified_since parameter"""

    # Create first plant
    plant_id_1 = uuid4()
    plant_data["id"] = str(plant_id_1)
    plant_data["name"] = "Plant One"
    response1 = client.put("/plant", json=plant_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second plant
    import time

    time.sleep(0.1)

    plant_id_2 = uuid4()
    facility_id_2 = uuid4()
    plant_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    plant_data_2["id"] = str(plant_id_2)
    plant_data_2["name"] = "Plant Two"
    plant_data_2["facilities"][0]["id"] = str(facility_id_2)
    response2 = client.put("/plant", json=plant_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all plants without filter - should return both
    response = client.get("/plant/all")
    assert response.status_code == 200
    all_plants = response.json()["items"]
    plant_ids = [p["id"] for p in all_plants]
    assert str(plant_id_1) in plant_ids
    assert str(plant_id_2) in plant_ids

    # Get plants modified after timestamp1 - should only return plant 2
    response = client.get(f"/plant/all?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_plants = response.json()["items"]
    filtered_ids = [p["id"] for p in filtered_plants]
    assert str(plant_id_1) not in filtered_ids
    assert str(plant_id_2) in filtered_ids

    # Get plants modified after timestamp2 - should return none
    response = client.get(f"/plant/all?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_plants = response.json()["items"]
    filtered_ids = [p["id"] for p in filtered_plants]
    assert str(plant_id_1) not in filtered_ids
    assert str(plant_id_2) not in filtered_ids


def test_get_all_plants_modified_since_default(client: TestClient, plant_data):
    """Test that without modified_since parameter, all plants are returned"""
    # Create a plant
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    # Get all plants without modified_since parameter
    response = client.get("/plant/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    plant_ids = [p["id"] for p in data["items"]]
    assert str(plant_data["id"]) in plant_ids
