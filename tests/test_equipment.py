"""Integration tests for Equipment API"""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PUT_BODY_TEMPLATE = {
    "name": "Test Motor",
    "is_container": False,
    "equipment_type_id": None,
    "estimated_point_count": 50,
    "qr_code": None,
    "server_modified_at": "2024-01-01T10:00:00Z",
    "control_points": [
        {
            "control_point_type": "БКС",
            "point_count": 30,
            "sticker_count": 25,
            "sticker_type_id": None,
            "is_deleted": False,
        },
    ],
    "defects": [],  # DEPRECATED: Defects are now managed via separate defect router
}


@pytest.fixture
def equipment_id():
    return uuid4()


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def facility_id():
    return uuid4()


@pytest.fixture
def control_point_id_1():
    return uuid4()


@pytest.fixture
def defect_id_1():
    return uuid4()


@pytest.fixture
def equipment_data(
    equipment_id,
    plant_id,
    facility_id,
    control_point_id_1,
    defect_id_1,
    seed_test_plant_and_facility,
):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(equipment_id)
    data["facility_id"] = str(facility_id)
    data["parent_id"] = str(facility_id)
    data["control_points"][0]["id"] = str(control_point_id_1)
    # defects are always empty now
    return data


def test_create_equipment(client: TestClient, equipment_data, equipment_id, plant_id, facility_id):
    """Test creating a new equipment with control points (defects always empty)"""

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(equipment_id)
    assert data["name"] == "Test Motor"
    assert data["facility_id"] == str(facility_id)
    assert data["parent_id"] == str(facility_id)
    assert len(data["control_points"]) == 1
    assert len(data["defects"]) == 0  # Always empty now


def test_get_equipment(client: TestClient, equipment_data, equipment_id):
    """Test retrieving equipment"""
    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    # Then get
    response = client.get(f"/equipment/by_id/{equipment_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(equipment_id)
    assert data["name"] == "Test Motor"
    assert len(data["control_points"]) == 1


def test_get_nonexistent_equipment(client: TestClient):
    """Test retrieving a non-existent equipment"""
    equipment_id = uuid4()
    response = client.get(f"/equipment/by_id/{equipment_id}")
    assert response.status_code == 404


def test_update_equipment(client: TestClient, equipment_data):
    """Test updating equipment"""

    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]

    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["name"] = "Updated Name"
    equipment_data["control_points"][0]["point_count"] = 15
    equipment_data["control_points"][0]["is_deleted"] = True

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["control_points"][0]["point_count"] == 15
    assert data["control_points"][0]["is_deleted"]
    assert len(data["defects"]) == 0  # Always empty


def test_sync_control_points_add_new(client: TestClient, equipment_data):
    """Test adding new control points"""

    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]
    equipment_data["server_modified_at"] = server_modified_at

    # Update with additional control point
    control_point_id_2 = uuid4()

    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )
    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["control_points"]) == 2


def test_sync_control_points_reject_missing_child(client: TestClient, equipment_data):
    """Test marking control points as deleted explicitly"""
    control_point_id_2 = uuid4()
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )
    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]
    equipment_data["server_modified_at"] = server_modified_at

    del equipment_data["control_points"][0]

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 409


def test_sync_control_points_force_update(client: TestClient, equipment_data):
    """Test marking control points as deleted explicitly"""
    control_point_id_2 = uuid4()
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )
    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]
    equipment_data["server_modified_at"] = server_modified_at

    del equipment_data["control_points"][0]

    response = client.put("/equipment?force=true", json=equipment_data)
    assert response.status_code == 200
    data = response.json()
    assert len(data["control_points"]) == 2
    # This might be flaky:
    assert data["control_points"][0]["is_deleted"]
    assert not data["control_points"][1]["is_deleted"]


# DEPRECATED: Defect sync tests removed - defects are now managed via separate defect router
# See tests/test_defect.py for defect-specific tests


def test_delete_equipment(client: TestClient, equipment_data, equipment_id):
    """Test logical deletion of equipment"""
    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["is_deleted"] = True

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    # Verify it's marked as deleted
    get_response = client.get(f"/equipment/by_id/{equipment_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["is_deleted"] is True


# DEPRECATED: Defect transfer test removed - defects are now managed via separate defect router


def test_control_point_transfer_not_allowed(
    client: TestClient,
    equipment_data,
    equipment_id,
    plant_id,
    facility_id,
    control_point_id_1,
):
    """Test that transferring a control point from one equipment to another is not allowed"""
    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200

    equipment_id2 = uuid4()

    equipment_data2 = {
        "id": str(equipment_id2),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Test Motor 2",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 50,
        "server_modified_at": "2024-01-01T10:00:00Z",
        "is_deleted": False,
        "control_points": equipment_data["control_points"],  # Transfer
        "defects": [],
    }

    response = client.put("/equipment", json=equipment_data2)
    assert response.status_code == 400
    assert "cannot transfer" in response.json()["detail"].lower()


# NEW TESTS - Missing test cases 2-10


def test_mismatched_control_point_ids_rejection(client: TestClient, equipment_data, control_point_id_1):
    """Test #2: Reject when server and client have same count but different control point IDs"""
    control_point_id_2 = uuid4()
    control_point_id_3 = uuid4()

    # Add two more control points [A, B, C]
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_3),
            "control_point_type": "Контакт",
            "point_count": 10,
            "sticker_count": 8,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with 3 control points [A, B, D] - D is new, C is missing
    control_point_id_d = uuid4()
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["control_points"][2] = {
        "id": str(control_point_id_d),
        "control_point_type": "Новый тип",
        "point_count": 12,
        "sticker_count": 10,
        "sticker_type_id": None,
        "is_deleted": False,
    }

    response = client.put("/equipment?force=false", json=equipment_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child" in error_data["message"].lower()
    assert str(control_point_id_3) in error_data["extra_child_ids"]


# DEPRECATED: Defect mismatch test removed - defects are now managed via separate defect router


def test_deleted_control_points_persist_through_updates(client: TestClient, equipment_data, control_point_id_1):
    """Test #4a: Deleted control points remain in GET response after updates"""
    control_point_id_2 = uuid4()

    # Add second control point
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    create_response = client.put("/equipment", json=equipment_data)
    server_modified_at = create_response.json()["server_modified_at"]

    # Mark control point 2 as deleted
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["control_points"][1]["is_deleted"] = True

    update_response = client.put("/equipment", json=equipment_data)
    assert update_response.status_code == 200
    server_modified_at = update_response.json()["server_modified_at"]

    # Do another update (just change equipment name)
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["name"] = "Updated Equipment Name"

    final_response = client.put("/equipment", json=equipment_data)
    assert final_response.status_code == 200

    # Verify deleted control point is still returned
    get_response = client.get(f"/equipment/by_id/{equipment_data['id']}")
    assert get_response.status_code == 200

    data = get_response.json()
    assert len(data["control_points"]) == 2

    deleted_cp = next(
        (cp for cp in data["control_points"] if cp["id"] == str(control_point_id_2)),
        None,
    )
    assert deleted_cp is not None
    assert deleted_cp["is_deleted"] is True


# DEPRECATED: Deleted defects test removed - defects are now managed via separate defect router


def test_force_mode_with_control_point_stealing_attempt(
    client: TestClient,
    equipment_data,
    equipment_id,
    plant_id,
    facility_id,
    control_point_id_1,
):
    """Test #5: Stealing control points never allowed even with force=true"""
    client.put("/equipment", json=equipment_data)

    # Try to steal control point with force=true
    equipment_id_2 = uuid4()
    equipment_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    equipment_data_2["id"] = str(equipment_id_2)
    equipment_data_2["facility_id"] = str(facility_id)
    equipment_data_2["parent_id"] = str(facility_id)
    equipment_data_2["name"] = "Equipment Two"
    equipment_data_2["control_points"][0]["id"] = str(control_point_id_1)  # Steal control point

    response = client.put("/equipment?force=true", json=equipment_data_2)
    assert response.status_code == 400
    assert "cannot transfer" in response.json()["detail"].lower()


def test_empty_control_points_list_without_force(client: TestClient, equipment_data, control_point_id_1):
    """Test #6a: Updating from non-empty to empty control points with force=false should reject"""
    control_point_id_2 = uuid4()

    # Add second control point
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with empty control points list (force=false)
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["control_points"] = []

    response = client.put("/equipment?force=false", json=equipment_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child" in error_data["message"].lower()


def test_empty_control_points_list_with_force(client: TestClient, equipment_data, control_point_id_1):
    """Test #6b: Updating from non-empty to empty control points with force=true should mark all as deleted"""
    control_point_id_2 = uuid4()

    # Add second control point
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    client.put("/equipment", json=equipment_data)

    # Update with empty control points list (force=true)
    equipment_data["control_points"] = []

    response = client.put("/equipment?force=true", json=equipment_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["control_points"]) == 2

    # Both control points should be marked as deleted
    for cp in data["control_points"]:
        assert cp["is_deleted"] is True


# DEPRECATED: Empty defects list tests removed - defects are now managed via separate defect router


def test_multiple_operations_in_single_request(client: TestClient, equipment_data, control_point_id_1):
    """Test #7: Simultaneously add, update, and delete control points in one PUT"""
    control_point_id_2 = uuid4()

    # Start with 2 control points
    equipment_data["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # In one request:
    # - Update control point 1 point_count
    # - Mark control point 2 as deleted
    # - Add new control point 3
    control_point_id_3 = uuid4()

    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["control_points"][0]["point_count"] = 35  # Update
    equipment_data["control_points"][1]["is_deleted"] = True  # Delete
    equipment_data["control_points"].append(
        {  # Add
            "id": str(control_point_id_3),
            "control_point_type": "Контакт",
            "point_count": 10,
            "sticker_count": 8,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    response = client.put("/equipment", json=equipment_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["control_points"]) == 3
    assert len(data["defects"]) == 0  # Always empty

    # Verify control point 1 was updated
    cp1 = next(
        (cp for cp in data["control_points"] if cp["id"] == str(control_point_id_1)),
        None,
    )
    assert cp1 is not None
    assert cp1["point_count"] == 35
    assert cp1["is_deleted"] is False

    # Verify control point 2 was marked as deleted
    cp2 = next(
        (cp for cp in data["control_points"] if cp["id"] == str(control_point_id_2)),
        None,
    )
    assert cp2 is not None
    assert cp2["is_deleted"] is True

    # Verify control point 3 was added
    cp3 = next(
        (cp for cp in data["control_points"] if cp["id"] == str(control_point_id_3)),
        None,
    )
    assert cp3 is not None
    assert cp3["control_point_type"] == "Контакт"
    assert cp3["is_deleted"] is False


def test_get_all_equipment_includes_deleted(client: TestClient, equipment_data):
    """Test #8: GET /equipment/all includes deleted equipment"""
    # Create equipment
    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Mark as deleted
    equipment_data["server_modified_at"] = server_modified_at
    equipment_data["is_deleted"] = True

    update_response = client.put("/equipment", json=equipment_data)
    assert update_response.status_code == 200

    # Get all equipment
    response = client.get("/equipment/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data

    # Find our deleted equipment in the list
    deleted_equipment = next((e for e in data["items"] if e["id"] == equipment_data["id"]), None)
    assert deleted_equipment is not None
    assert deleted_equipment["is_deleted"] is True


def test_get_equipment_by_plant_id(client: TestClient, equipment_data, plant_id, facility_id):
    """Test #9: GET /equipment/by_plant_id/{plant_id} returns full equipment aggregates for specific plant"""
    # Create equipment for plant
    client.put("/equipment", json=equipment_data)

    # Create another equipment for different plant
    equipment_id_2 = uuid4()
    facility_id_2 = uuid4()

    equipment_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    equipment_data_2["id"] = str(equipment_id_2)
    equipment_data_2["facility_id"] = str(facility_id_2)
    equipment_data_2["parent_id"] = str(facility_id_2)
    equipment_data_2["name"] = "Equipment for Plant 2"
    equipment_data_2["control_points"][0]["id"] = str(uuid4())
    # defects is already empty in template

    client.put("/equipment", json=equipment_data_2)

    # Get equipment for first plant
    response = client.get(f"/equipment/by_plant_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Verify only equipment from first plant is returned (via facility)
    for equipment in data:
        assert equipment["facility_id"] == str(facility_id)
        # Verify it's a full Equipment aggregate with control_points and inspection_ids
        assert "control_points" in equipment
        assert "defects" in equipment  # Present but always empty
        assert "inspection_ids" in equipment

    # Verify our equipment is in the list
    our_equipment = next((e for e in data if e["id"] == equipment_data["id"]), None)
    assert our_equipment is not None
    assert len(our_equipment["control_points"]) == 1
    assert len(our_equipment["defects"]) == 0  # Always empty


def test_concurrent_modification_with_control_points(client: TestClient, equipment_data, control_point_id_1):
    """Test #10: Concurrent modification detected when another client adds control points"""
    control_point_id_2 = uuid4()

    # Client A creates equipment with 1 control point
    create_response = client.put("/equipment", json=equipment_data)
    assert create_response.status_code == 200
    client_a_timestamp = create_response.json()["server_modified_at"]

    # Client B adds a control point (simulating concurrent modification)
    equipment_data_b = deepcopy(equipment_data)
    equipment_data_b["server_modified_at"] = client_a_timestamp
    equipment_data_b["control_points"].append(
        {
            "id": str(control_point_id_2),
            "control_point_type": "Подшипник",
            "point_count": 5,
            "sticker_count": 4,
            "sticker_type_id": None,
            "is_deleted": False,
        }
    )

    client_b_response = client.put("/equipment", json=equipment_data_b)
    assert client_b_response.status_code == 200
    client_b_timestamp = client_b_response.json()["server_modified_at"]

    # Client A tries to update with old timestamp and only 1 control point
    # This should fail because timestamp doesn't match (Client B's update changed it)
    equipment_data["server_modified_at"] = client_a_timestamp
    equipment_data["name"] = "Updated by Client A"

    response = client.put("/equipment?force=false", json=equipment_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    # The error will be about timestamp mismatch, not extra children
    # because timestamp validation happens first
    assert "modified by another client" in error_data["message"].lower()
    assert error_data["server_modified_at"] == client_b_timestamp


# Tests for modified_since filter


def test_get_all_equipment_with_modified_since_filter(client: TestClient, equipment_data, plant_id, facility_id):
    """Test filtering equipment by modified_since parameter"""
    import time

    # Create first equipment
    equipment_id_1 = uuid4()
    equipment_data["id"] = str(equipment_id_1)
    equipment_data["name"] = "Equipment One"
    response1 = client.put("/equipment", json=equipment_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second equipment
    time.sleep(0.1)

    equipment_id_2 = uuid4()
    equipment_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    equipment_data_2["id"] = str(equipment_id_2)
    equipment_data_2["facility_id"] = str(facility_id)
    equipment_data_2["parent_id"] = str(facility_id)
    equipment_data_2["name"] = "Equipment Two"
    equipment_data_2["control_points"][0]["id"] = str(uuid4())
    response2 = client.put("/equipment", json=equipment_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all equipment without filter - should return both
    response = client.get("/equipment/all")
    assert response.status_code == 200
    all_equipment = response.json()["items"]
    equipment_ids = [e["id"] for e in all_equipment]
    assert str(equipment_id_1) in equipment_ids
    assert str(equipment_id_2) in equipment_ids

    # Get equipment modified after timestamp1 - should only return equipment 2
    response = client.get(f"/equipment/all?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_equipment = response.json()["items"]
    filtered_ids = [e["id"] for e in filtered_equipment]
    assert str(equipment_id_1) not in filtered_ids
    assert str(equipment_id_2) in filtered_ids

    # Get equipment modified after timestamp2 - should return none
    response = client.get(f"/equipment/all?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_equipment = response.json()["items"]
    filtered_ids = [e["id"] for e in filtered_equipment]
    assert str(equipment_id_1) not in filtered_ids
    assert str(equipment_id_2) not in filtered_ids


def test_get_equipment_by_plant_with_modified_since_filter(client: TestClient, equipment_data, plant_id, facility_id):
    """Test filtering equipment by plant and modified_since parameter"""
    import time

    # Create first equipment
    equipment_id_1 = uuid4()
    equipment_data["id"] = str(equipment_id_1)
    equipment_data["name"] = "Equipment One"
    response1 = client.put("/equipment", json=equipment_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second equipment
    time.sleep(0.1)

    equipment_id_2 = uuid4()
    equipment_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    equipment_data_2["id"] = str(equipment_id_2)
    equipment_data_2["facility_id"] = str(facility_id)
    equipment_data_2["parent_id"] = str(facility_id)
    equipment_data_2["name"] = "Equipment Two"
    equipment_data_2["control_points"][0]["id"] = str(uuid4())
    response2 = client.put("/equipment", json=equipment_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all equipment for plant without filter - should return both
    response = client.get(f"/equipment/by_plant_id/{plant_id}")
    assert response.status_code == 200
    all_equipment = response.json()
    equipment_ids = [e["id"] for e in all_equipment]
    assert str(equipment_id_1) in equipment_ids
    assert str(equipment_id_2) in equipment_ids

    # Get equipment modified after timestamp1 - should only return equipment 2
    response = client.get(f"/equipment/by_plant_id/{plant_id}?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_equipment = response.json()
    filtered_ids = [e["id"] for e in filtered_equipment]
    assert str(equipment_id_1) not in filtered_ids
    assert str(equipment_id_2) in filtered_ids

    # Get equipment modified after timestamp2 - should return none
    response = client.get(f"/equipment/by_plant_id/{plant_id}?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_equipment = response.json()
    assert len(filtered_equipment) == 0
