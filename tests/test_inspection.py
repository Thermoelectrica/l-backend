"""Integration tests for Inspection API"""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PUT_BODY_TEMPLATE = {
    "inspector_id": 1,
    "started_at": "2024-01-01T10:00:00Z",
    "completed_at": None,
    "status": "IN_PROGRESS",
    "server_modified_at": "2024-01-01T10:00:00Z",
    "steps": [
        {
            "started_at": "2024-01-01T10:05:00Z",
            "step_number": 1,
            "step_type": "GENERAL_INSPECTION",
            "defect_id": None,
            "description": "Initial inspection",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    ],
}


@pytest.fixture
def inspection_id():
    return uuid4()


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
def step_id_1():
    return uuid4()


@pytest.fixture
def image_id_1():
    return uuid4()


@pytest.fixture
def inspection_data(inspection_id, equipment_id, step_id_1, plant_id, facility_id, seed_test_equipment):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(inspection_id)
    data["equipment_id"] = str(equipment_id)
    data["steps"][0]["id"] = str(step_id_1)
    return data


def test_create_inspection(client: TestClient, inspection_data, inspection_id, equipment_id):
    """Test creating a new inspection with steps"""
    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(inspection_id)
    assert data["equipment_id"] == str(equipment_id)
    assert data["status"] == "IN_PROGRESS"
    assert len(data["steps"]) == 1


def test_get_inspection(client: TestClient, inspection_data, inspection_id):
    """Test retrieving inspection"""
    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    # Then get
    response = client.get(f"/inspection/by_id/{inspection_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(inspection_id)
    assert data["status"] == "IN_PROGRESS"
    assert len(data["steps"]) == 1


def test_get_nonexistent_inspection(client: TestClient):
    """Test retrieving a non-existent inspection"""
    inspection_id = uuid4()
    response = client.get(f"/inspection/by_id/{inspection_id}")
    assert response.status_code == 404


def test_update_inspection(client: TestClient, inspection_data):
    """Test updating inspection"""
    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]

    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["status"] = "COMPLETED"
    inspection_data["completed_at"] = "2024-01-01T12:00:00Z"
    inspection_data["steps"][0]["description"] = "Updated description"

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["completed_at"] is not None
    assert data["steps"][0]["description"] == "Updated description"


def test_sync_steps_add_new(client: TestClient, inspection_data):
    """Test adding new inspection steps"""
    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at

    # Add additional step
    step_id_2 = uuid4()
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Defect found",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": 95.5,
            "measured_current": 100,
            "nominal_current": 80,
            "severity": "CRITICAL",
            "is_test_ready": True,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["steps"]) == 2


def test_sync_steps_reject_missing_child(client: TestClient, inspection_data):
    """Test rejecting when steps are missing without force"""
    step_id_2 = uuid4()
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at

    # Remove first step
    del inspection_data["steps"][0]

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 409


def test_sync_steps_force_update(client: TestClient, inspection_data):
    """Test marking steps as deleted with force=true"""
    step_id_2 = uuid4()
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at

    # Remove first step
    del inspection_data["steps"][0]

    response = client.put("/inspection?force=true", json=inspection_data)
    assert response.status_code == 200
    data = response.json()
    assert len(data["steps"]) == 2
    # One should be deleted
    deleted_steps = [s for s in data["steps"] if s["is_deleted"]]
    assert len(deleted_steps) == 1


def test_add_image_links_to_step(client: TestClient, inspection_data, image_id_1):
    """Test adding image links to inspection step"""
    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at

    # Add image link to first step
    inspection_data["steps"][0]["image_links"] = [{"image_id": str(image_id_1), "is_deleted": False}]

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["steps"][0]["image_links"]) == 1
    assert data["steps"][0]["image_links"][0]["image_id"] == str(image_id_1)
    assert data["steps"][0]["image_links"][0]["is_deleted"] is False


def test_remove_image_links_from_step(client: TestClient, inspection_data, image_id_1):
    """Test removing image links from inspection step (logical deletion)"""
    # Create with image link
    inspection_data["steps"][0]["image_links"] = [{"image_id": str(image_id_1), "is_deleted": False}]

    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at

    # Remove image link (will be marked as deleted)
    inspection_data["steps"][0]["image_links"] = []

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    # Image link should still be returned but marked as deleted
    assert len(data["steps"][0]["image_links"]) == 1
    assert data["steps"][0]["image_links"][0]["is_deleted"] is True


def test_delete_inspection(client: TestClient, inspection_data, inspection_id):
    """Test logical deletion of inspection"""
    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]
    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["is_deleted"] = True

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    # Verify it's marked as deleted
    get_response = client.get(f"/inspection/by_id/{inspection_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["is_deleted"] is True


def test_step_transfer_not_allowed(client: TestClient, inspection_data, equipment_id):
    """Test that transferring a step from one inspection to another is not allowed"""
    create_response = client.put("/inspection", json=inspection_data)
    assert create_response.status_code == 200

    inspection_id_2 = uuid4()
    inspection_data_2 = {
        "id": str(inspection_id_2),
        "equipment_id": str(equipment_id),
        "inspector_id": 1,
        "started_at": "2024-01-02T10:00:00Z",
        "completed_at": None,
        "status": "IN_PROGRESS",
        "server_modified_at": "2024-01-02T10:00:00Z",
        "is_deleted": False,
        "steps": inspection_data["steps"],  # Transfer steps
    }

    response = client.put("/inspection", json=inspection_data_2)
    assert response.status_code == 400
    assert "cannot transfer" in response.json()["detail"].lower()


def test_get_all_inspections(client: TestClient, inspection_data):
    """Test getting all inspections"""
    client.put("/inspection", json=inspection_data)

    response = client.get("/inspection/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_get_inspections_by_plant_id(client: TestClient, inspection_data, plant_id):
    """Test getting inspections for specific plant"""
    client.put("/inspection", json=inspection_data)

    # Create another inspection for different equipment in different plant
    inspection_id_2 = uuid4()
    equipment_id_2 = uuid4()

    inspection_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    inspection_data_2["id"] = str(inspection_id_2)
    inspection_data_2["equipment_id"] = str(equipment_id_2)
    inspection_data_2["steps"][0]["id"] = str(uuid4())

    client.put("/inspection", json=inspection_data_2)

    # Get inspections for first plant
    response = client.get(f"/inspection/by_plant_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    # Verify it's a full Inspection aggregate with steps
    for inspection in data:
        assert "steps" in inspection


def test_concurrent_modification_detection(client: TestClient, inspection_data):
    """Test concurrent modification detected when another client modifies inspection"""
    # Client A creates inspection
    create_response = client.put("/inspection", json=inspection_data)
    assert create_response.status_code == 200
    client_a_timestamp = create_response.json()["server_modified_at"]

    # Client B adds a step (simulating concurrent modification)
    inspection_data_b = deepcopy(inspection_data)
    inspection_data_b["server_modified_at"] = client_a_timestamp
    step_id_2 = uuid4()
    inspection_data_b["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Added by Client B",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    client_b_response = client.put("/inspection", json=inspection_data_b)
    assert client_b_response.status_code == 200
    client_b_timestamp = client_b_response.json()["server_modified_at"]

    # Client A tries to update with old timestamp
    inspection_data["server_modified_at"] = client_a_timestamp
    inspection_data["status"] = "COMPLETED"

    response = client.put("/inspection?force=false", json=inspection_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "modified by another client" in error_data["message"].lower()
    assert error_data["server_modified_at"] == client_b_timestamp


def test_multiple_operations_in_single_request(client: TestClient, inspection_data, step_id_1):
    """Test simultaneously add, update, and delete steps in one PUT"""
    step_id_2 = uuid4()

    # Start with 2 steps
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    create_response = client.put("/inspection", json=inspection_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # In one request:
    # - Update step 1 description
    # - Mark step 2 as deleted
    # - Add new step 3
    step_id_3 = uuid4()

    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["steps"][0]["description"] = "Updated first step"
    inspection_data["steps"][1]["is_deleted"] = True
    inspection_data["steps"].append(
        {
            "id": str(step_id_3),
            "started_at": "2024-01-01T10:15:00Z",
            "step_number": 3,
            "step_type": "DEFECT_FOLLOW_UP",
            "defect_id": None,
            "description": "Third step",
            "is_resolved": True,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    response = client.put("/inspection", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["steps"]) == 3

    # Verify step 1 was updated
    s1 = next((s for s in data["steps"] if s["id"] == str(step_id_1)), None)
    assert s1 is not None
    assert s1["description"] == "Updated first step"
    assert s1["is_deleted"] is False

    # Verify step 2 was marked as deleted
    s2 = next((s for s in data["steps"] if s["id"] == str(step_id_2)), None)
    assert s2 is not None
    assert s2["is_deleted"] is True

    # Verify step 3 was added
    s3 = next((s for s in data["steps"] if s["id"] == str(step_id_3)), None)
    assert s3 is not None
    assert s3["step_type"] == "DEFECT_FOLLOW_UP"
    assert s3["is_deleted"] is False


def test_get_all_inspections_with_modified_since_filter(client: TestClient, inspection_data, equipment_id):
    """Test filtering inspections by modified_since parameter"""
    import time

    # Create first inspection
    inspection_id_1 = uuid4()
    inspection_data["id"] = str(inspection_id_1)
    response1 = client.put("/inspection", json=inspection_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second inspection
    time.sleep(0.1)

    inspection_id_2 = uuid4()
    inspection_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    inspection_data_2["id"] = str(inspection_id_2)
    inspection_data_2["equipment_id"] = str(equipment_id)
    inspection_data_2["steps"][0]["id"] = str(uuid4())
    response2 = client.put("/inspection", json=inspection_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all inspections without filter - should return both
    response = client.get("/inspection/all")
    assert response.status_code == 200
    all_inspections = response.json()["items"]
    inspection_ids = [i["id"] for i in all_inspections]
    assert str(inspection_id_1) in inspection_ids
    assert str(inspection_id_2) in inspection_ids

    # Get inspections modified after timestamp1 - should only return inspection 2
    response = client.get(f"/inspection/all?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_inspections = response.json()["items"]
    filtered_ids = [i["id"] for i in filtered_inspections]
    assert str(inspection_id_1) not in filtered_ids
    assert str(inspection_id_2) in filtered_ids

    # Get inspections modified after timestamp2 - should return none
    response = client.get(f"/inspection/all?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_inspections = response.json()["items"]
    filtered_ids = [i["id"] for i in filtered_inspections]
    assert str(inspection_id_1) not in filtered_ids
    assert str(inspection_id_2) not in filtered_ids


def test_get_inspections_by_plant_with_modified_since_filter(
    client: TestClient, inspection_data, plant_id, equipment_id
):
    """Test filtering inspections by plant and modified_since parameter"""
    import time

    # Create first inspection
    inspection_id_1 = uuid4()
    inspection_data["id"] = str(inspection_id_1)
    response1 = client.put("/inspection", json=inspection_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second inspection
    time.sleep(0.1)

    inspection_id_2 = uuid4()
    inspection_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    inspection_data_2["id"] = str(inspection_id_2)
    inspection_data_2["equipment_id"] = str(equipment_id)
    inspection_data_2["steps"][0]["id"] = str(uuid4())
    response2 = client.put("/inspection", json=inspection_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all inspections for plant without filter - should return both
    response = client.get(f"/inspection/by_plant_id/{plant_id}")
    assert response.status_code == 200
    all_inspections = response.json()
    inspection_ids = [i["id"] for i in all_inspections]
    assert str(inspection_id_1) in inspection_ids
    assert str(inspection_id_2) in inspection_ids

    # Get inspections modified after timestamp1 - should only return inspection 2
    response = client.get(f"/inspection/by_plant_id/{plant_id}?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_inspections = response.json()
    filtered_ids = [i["id"] for i in filtered_inspections]
    assert str(inspection_id_1) not in filtered_ids
    assert str(inspection_id_2) in filtered_ids

    # Get inspections modified after timestamp2 - should return none
    response = client.get(f"/inspection/by_plant_id/{plant_id}?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_inspections = response.json()
    assert len(filtered_inspections) == 0


def test_empty_steps_list_without_force(client: TestClient, inspection_data):
    """Test updating from non-empty to empty steps with force=false should reject"""
    step_id_2 = uuid4()

    # Add second step
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    create_response = client.put("/inspection", json=inspection_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Try to update with empty steps list (force=false)
    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["steps"] = []

    response = client.put("/inspection?force=false", json=inspection_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "extra child" in error_data["message"].lower()


def test_empty_steps_list_with_force(client: TestClient, inspection_data):
    """Test updating from non-empty to empty steps with force=true should mark all as deleted"""
    step_id_2 = uuid4()

    # Add second step
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    client.put("/inspection", json=inspection_data)

    # Update with empty steps list (force=true)
    inspection_data["steps"] = []

    response = client.put("/inspection?force=true", json=inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["steps"]) == 2

    # Both steps should be marked as deleted
    for step in data["steps"]:
        assert step["is_deleted"] is True


def test_deleted_steps_persist_through_updates(client: TestClient, inspection_data, step_id_1):
    """Test deleted steps remain in GET response after updates"""
    step_id_2 = uuid4()

    # Add second step
    inspection_data["steps"].append(
        {
            "id": str(step_id_2),
            "started_at": "2024-01-01T10:10:00Z",
            "step_number": 2,
            "step_type": "DEFECT_REPORT",
            "defect_id": None,
            "description": "Second step",
            "is_resolved": None,
            "sticker_type_id": None,
            "t_sticker": None,
            "t_environment": None,
            "t_similar_unit": None,
            "epsilon": 0.95,
            "t_max": None,
            "t_excess": None,
            "t_observed": None,
            "measured_current": None,
            "nominal_current": None,
            "severity": None,
            "is_test_ready": None,
            "is_attention_required": False,
            "step_status": None,
            "is_deleted": False,
            "image_links": [],
        }
    )

    create_response = client.put("/inspection", json=inspection_data)
    server_modified_at = create_response.json()["server_modified_at"]

    # Mark step 2 as deleted
    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["steps"][1]["is_deleted"] = True

    update_response = client.put("/inspection", json=inspection_data)
    assert update_response.status_code == 200
    server_modified_at = update_response.json()["server_modified_at"]

    # Do another update (just change status)
    inspection_data["server_modified_at"] = server_modified_at
    inspection_data["status"] = "COMPLETED"

    final_response = client.put("/inspection", json=inspection_data)
    assert final_response.status_code == 200

    # Verify deleted step is still returned
    get_response = client.get(f"/inspection/by_id/{inspection_data['id']}")
    assert get_response.status_code == 200

    data = get_response.json()
    assert len(data["steps"]) == 2

    deleted_step = next((s for s in data["steps"] if s["id"] == str(step_id_2)), None)
    assert deleted_step is not None
    assert deleted_step["is_deleted"] is True
