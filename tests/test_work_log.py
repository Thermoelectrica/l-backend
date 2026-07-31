"""Integration tests for Work Log API"""

import time
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

now = datetime.now(timezone.utc)
PUT_BODY_TEMPLATE = {
    "inspector_id": 1,
    "started_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
    "completed_at": None,
    "installation_percentage": None,
    "is_deleted": False,
    "server_modified_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
}


@pytest.fixture
def work_log_id():
    return uuid4()


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def inspector_id_1():
    return 1


@pytest.fixture
def inspector_id_2():
    return 2


@pytest.fixture
def work_log_data(work_log_id, plant_id, inspector_id_1):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(work_log_id)
    data["plant_id"] = str(plant_id)
    data["inspector_id"] = inspector_id_1
    return data


@pytest.fixture
def inspectors_data(work_log_id, inspector_id_1, inspector_id_2):
    return [{"inspector_id": inspector_id_1}, {"inspector_id": inspector_id_2}]


def test_create_work_log(
    client: TestClient,
    work_log_data,
    inspectors_data,
    work_log_id,
    plant_id,
    inspector_id_1,
):
    """Test creating a new work log with inspectors"""
    work_log_data["inspectors"] = inspectors_data
    response = client.put("/work_log", json=work_log_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(work_log_id)
    assert data["plant_id"] == str(plant_id)
    assert data["inspector_id"] == inspector_id_1
    assert data["started_at"] is not None
    assert data["completed_at"] is None
    assert data["installation_percentage"] is None
    assert data["is_deleted"] is False


def test_get_work_log(client: TestClient, work_log_data, inspectors_data, work_log_id):
    """Test retrieving work log"""
    work_log_data["inspectors"] = inspectors_data
    response = client.put("/work_log", json=work_log_data)
    assert response.status_code == 200

    response = client.get(f"/work_log/by_id/{work_log_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(work_log_id)
    assert data["started_at"] is not None
    assert data["completed_at"] is None


def test_get_nonexistent_work_log(client: TestClient):
    """Test retrieving a non-existent work log"""
    work_log_id = uuid4()
    response = client.get(f"/work_log/by_id/{work_log_id}")
    assert response.status_code == 404


def test_update_work_log(client: TestClient, work_log_data, inspectors_data):
    """Test updating work log"""
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    server_modified_at = create_response.json()["server_modified_at"]

    work_log_data["server_modified_at"] = server_modified_at
    work_log_data["completed_at"] = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    work_log_data["installation_percentage"] = 75.5

    response = client.put("/work_log", json=work_log_data)
    assert response.status_code == 200

    data = response.json()
    assert data["completed_at"] is not None
    assert data["installation_percentage"] == 75.5


def test_sync_inspectors_add_new(client: TestClient, work_log_data, inspectors_data, inspector_id_1, inspector_id_2):
    """Test adding new inspectors to work log"""
    initial_inspectors = [inspectors_data[0]]
    work_log_data["inspectors"] = initial_inspectors
    create_response = client.put("/work_log", json=work_log_data)
    server_modified_at = create_response.json()["server_modified_at"]

    work_log_data["server_modified_at"] = server_modified_at
    work_log_data["inspectors"] = inspectors_data  # Add second inspector
    response = client.put("/work_log", json=work_log_data)
    assert response.status_code == 200

    data = response.json()
    assert len(data["inspectors"]) == 2
    inspector_ids = [insp["inspector_id"] for insp in data["inspectors"]]
    assert inspector_id_1 in inspector_ids
    assert inspector_id_2 in inspector_ids


def test_sync_inspectors_reject_missing_child(client: TestClient, work_log_data, inspectors_data):
    """Test rejecting when inspectors are missing without force"""
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    work_log_data["server_modified_at"] = server_modified_at
    work_log_data["inspectors"] = [inspectors_data[0]]

    response = client.put("/work_log", json=work_log_data)

    assert response.status_code == 409


def test_sync_inspectors_force_update(client: TestClient, work_log_data, inspectors_data):
    """Test marking inspectors as deleted with force=true"""
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    server_modified_at = create_response.json()["server_modified_at"]

    work_log_data["server_modified_at"] = server_modified_at
    single_inspector = [inspectors_data[0]]
    work_log_data["inspectors"] = single_inspector
    response = client.put("/work_log?force=true", json=work_log_data)
    assert response.status_code == 200


def test_get_all_work_logs(client: TestClient, work_log_data, inspectors_data):
    """Test getting all work logs"""
    work_log_data["inspectors"] = inspectors_data
    client.put("/work_log", json=work_log_data)

    response = client.get("/work_log/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1


def test_get_work_logs_by_plant_id(client: TestClient, work_log_data, inspectors_data, plant_id):
    """Test getting work logs for specific plant"""
    work_log_data["inspectors"] = inspectors_data
    client.put("/work_log", json=work_log_data)

    work_log_id_2 = uuid4()
    plant_id_2 = uuid4()
    work_log_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    work_log_data_2["id"] = str(work_log_id_2)
    work_log_data_2["plant_id"] = str(plant_id_2)
    work_log_data_2["inspector_id"] = 1

    inspectors_data_2 = [{"inspector_id": 1}]

    work_log_data_2["inspectors"] = inspectors_data_2
    client.put("/work_log", json=work_log_data_2)

    response = client.get(f"/work_log/by_plant_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_concurrent_modification_detection(client: TestClient, work_log_data, inspectors_data):
    """Test concurrent modification detected when another client modifies work log"""
    # Client A creates work log
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    assert create_response.status_code == 200
    client_a_timestamp = create_response.json()["server_modified_at"]

    # Client B updates work log (simulating concurrent modification)
    work_log_data_b = deepcopy(work_log_data)
    work_log_data_b["server_modified_at"] = client_a_timestamp
    work_log_data_b["installation_percentage"] = 50.0

    work_log_data_b["inspectors"] = inspectors_data
    client_b_response = client.put("/work_log", json=work_log_data_b)
    assert client_b_response.status_code == 200

    # Client A tries to update with old timestamp
    work_log_data["server_modified_at"] = client_a_timestamp
    work_log_data["installation_percentage"] = 75.0

    work_log_data["inspectors"] = inspectors_data
    response = client.put("/work_log?force=false", json=work_log_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"


def test_get_all_work_logs_with_modified_since_filter(client: TestClient, work_log_data, inspectors_data):
    """Test filtering work logs by modified_since parameter"""
    work_log_id_1 = uuid4()
    work_log_data["id"] = str(work_log_id_1)

    inspectors_data_1 = [{"inspector_id": 1}, {"inspector_id": 2}]

    work_log_data["inspectors"] = inspectors_data_1
    response1 = client.put("/work_log", json=work_log_data)

    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    time.sleep(0.1)

    work_log_id_2 = uuid4()
    work_log_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    work_log_data_2["id"] = str(work_log_id_2)
    work_log_data_2["plant_id"] = str(uuid4())
    work_log_data_2["inspector_id"] = 1

    inspectors_data_2 = [{"inspector_id": 1}]

    work_log_data_2["inspectors"] = inspectors_data_2
    response2 = client.put("/work_log", json=work_log_data_2)
    assert response2.status_code == 200

    response = client.get("/work_log/all")
    assert response.status_code == 200
    all_work_logs = response.json()["items"]
    work_log_ids = [i["id"] for i in all_work_logs]
    assert str(work_log_id_1) in work_log_ids
    assert str(work_log_id_2) in work_log_ids

    # Get work logs modified after timestamp1 - should only return work log 2
    response = client.get(f"/work_log/all?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_work_logs = response.json()["items"]
    filtered_ids = [i["id"] for i in filtered_work_logs]
    assert str(work_log_id_1) not in filtered_ids
    assert str(work_log_id_2) in filtered_ids


def test_get_work_logs_by_plant_with_modified_since_filter(
    client: TestClient, work_log_data, inspectors_data, plant_id
):
    """Test filtering work logs by plant and modified_since parameter"""
    work_log_id_1 = uuid4()
    work_log_data["id"] = str(work_log_id_1)

    inspectors_data_1 = [{"inspector_id": 1}, {"inspector_id": 2}]

    work_log_data["inspectors"] = inspectors_data_1
    response1 = client.put("/work_log", json=work_log_data)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    time.sleep(0.1)

    work_log_id_2 = uuid4()
    work_log_data_2 = deepcopy(PUT_BODY_TEMPLATE)
    work_log_data_2["id"] = str(work_log_id_2)
    work_log_data_2["plant_id"] = str(plant_id)
    work_log_data_2["inspector_id"] = 1

    inspectors_data_2 = [{"inspector_id": 1}]

    work_log_data_2["inspectors"] = inspectors_data_2
    response2 = client.put("/work_log", json=work_log_data_2)
    assert response2.status_code == 200

    # Get all work logs for plant without filter - should return both
    response = client.get(f"/work_log/by_plant_id/{plant_id}")
    assert response.status_code == 200
    all_work_logs = response.json()
    work_log_ids = [i["id"] for i in all_work_logs]
    assert str(work_log_id_1) in work_log_ids
    assert str(work_log_id_2) in work_log_ids

    # Get work logs modified after timestamp1 - should only return work log 2
    response = client.get(f"/work_log/by_plant_id/{plant_id}?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_work_logs = response.json()
    filtered_ids = [i["id"] for i in filtered_work_logs]
    assert str(work_log_id_1) not in filtered_ids
    assert str(work_log_id_2) in filtered_ids


def test_work_log_without_inspectors(client: TestClient, work_log_data, work_log_id):
    """Test creating work log without inspectors"""
    work_log_data["inspectors"] = []
    response = client.put("/work_log", json=work_log_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(work_log_id)


def test_inspector_mismatch_error(client: TestClient, work_log_data, inspectors_data):
    """Test error when inspector doesn't belong to work log"""
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    assert create_response.status_code == 200

    created = create_response.json()
    work_log_data["server_modified_at"] = created["server_modified_at"]

    new_inspectors = inspectors_data + [{"inspector_id": 99999}]
    work_log_data["inspectors"] = new_inspectors

    response = client.put("/work_log", json=work_log_data)

    assert response.status_code == 400
    error_detail = response.json()["detail"]
    assert "99999" in error_detail or "do not exist" in error_detail


def test_get_work_logs_by_plant_id_empty(client: TestClient):
    """Regression test: by_plant_id returns empty list (not 404) when no work logs exist for plant"""
    nonexistent_plant_id = uuid4()
    response = client.get(f"/work_log/by_plant_id/{nonexistent_plant_id}")
    assert response.status_code == 200
    assert response.json() == []


def test_force_update_with_empty_inspectors(client: TestClient, work_log_data, inspectors_data):
    """Test force update removing all inspectors"""
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    server_modified_at = create_response.json()["server_modified_at"]

    # Force update with empty inspectors list
    work_log_data["server_modified_at"] = server_modified_at
    work_log_data["inspectors"] = []
    response = client.put("/work_log?force=true", json=work_log_data)
    assert response.status_code == 200


def test_sync_inspectors_removes_extra_with_force(
    client: TestClient, work_log_data, inspectors_data, inspector_id_1, inspector_id_2
):
    """Regression test: extra inspectors are actually removed when force=true.

    Previously, _sync_inspectors() guarded the deletion with `if force:` but the
    force parameter was never passed as True from _sync_inspectors when called via
    save() — the deletion block was dead code. The bug meant that a force=true update
    with a reduced inspector list would succeed (200) but silently keep the removed
    inspector in the DB.
    """
    # Create work log with two inspectors
    work_log_data["inspectors"] = inspectors_data
    create_response = client.put("/work_log", json=work_log_data)
    assert create_response.status_code == 200

    created_data = create_response.json()
    assert len(created_data["inspectors"]) == 2

    # Force-update keeping only the first inspector (skips optimistic locking check)
    work_log_data["server_modified_at"] = created_data["server_modified_at"]
    work_log_data["inspectors"] = [{"inspector_id": inspector_id_1}]
    response = client.put("/work_log?force=true", json=work_log_data)
    assert response.status_code == 200

    # The second inspector must no longer be present in the response
    data = response.json()
    inspector_ids = [insp["inspector_id"] for insp in data["inspectors"]]
    assert inspector_id_1 in inspector_ids
    assert inspector_id_2 not in inspector_ids
    assert len(data["inspectors"]) == 1

    # Verify via GET that the deletion is persisted
    get_response = client.get(f"/work_log/by_id/{work_log_data['id']}")
    assert get_response.status_code == 200
    get_data = get_response.json()
    get_inspector_ids = [insp["inspector_id"] for insp in get_data["inspectors"]]
    assert inspector_id_2 not in get_inspector_ids
    assert len(get_data["inspectors"]) == 1
