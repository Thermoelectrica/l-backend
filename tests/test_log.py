"""Integration tests for Log API"""

from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_single_log(client: TestClient):
    """Test creating a single log entry"""
    plant_id = uuid4()

    log_data = [
        {
            "logged_at": "2024-01-01T12:00:00Z",
            "plant_id": str(plant_id),
            "inspector_id": 1,
            "entity_id": "123",
            "entity_type": "EQUIPMENT",
            "op": "CREATE",
            "data": {"field": "value"},
            "message": "Equipment created",
        }
    ]

    response = client.post("/log", json=log_data)
    if response.status_code != 201:
        print(f"Error response: {response.json()}")
    assert response.status_code == 201

    data = response.json()
    assert data["inserted"] == 1


def test_create_batch_logs(client: TestClient):
    """Test batch inserting multiple log entries"""
    plant_id = uuid4()

    log_data = [
        {
            "logged_at": "2024-01-01T12:00:00Z",
            "plant_id": str(plant_id),
            "inspector_id": 1,
            "entity_id": "123",
            "entity_type": "EQUIPMENT",
            "op": "CREATE",
            "data": None,
            "message": "Equipment created",
        },
        {
            "logged_at": "2024-01-01T12:01:00Z",
            "plant_id": str(plant_id),
            "inspector_id": 1,
            "entity_id": "123",
            "entity_type": "EQUIPMENT",
            "op": "UPDATE",
            "data": {"updated_field": "new_value"},
            "message": "Equipment updated",
        },
        {
            "logged_at": "2024-01-01T12:02:00Z",
            "plant_id": str(plant_id),
            "inspector_id": 1,
            "entity_id": "456",
            "entity_type": "INSPECTION",
            "op": "CREATE",
            "data": None,
            "message": "Inspection started",
        },
    ]

    response = client.post("/log", json=log_data)
    assert response.status_code == 201

    data = response.json()
    assert data["inserted"] == 3


def test_log_all_entity_types(client: TestClient):
    """Test logging for all entity types"""
    entity_types = [
        "INSPECTOR",
        "PLANT",
        "FACILITY",
        "EQUIPMENT",
        "INSPECTION",
        "IMAGE",
    ]

    log_data = []
    for i, entity_type in enumerate(entity_types):
        log_data.append(
            {
                "logged_at": f"2024-01-01T12:0{i}:00Z",
                "plant_id": None if entity_type == "INSPECTOR" else str(uuid4()),
                "inspector_id": 1,
                "entity_id": str(i + 1),
                "entity_type": entity_type,
                "op": "CREATE",
                "data": None,
                "message": f"{entity_type} operation",
            }
        )

    response = client.post("/log", json=log_data)
    assert response.status_code == 201
    assert response.json()["inserted"] == len(entity_types)


def test_log_all_operations(client: TestClient):
    """Test all operation types"""
    operations = ["CREATE", "UPDATE", "DELETE"]
    plant_id = uuid4()

    log_data = []
    for i, op in enumerate(operations):
        log_data.append(
            {
                "logged_at": f"2024-01-01T12:0{i}:00Z",
                "plant_id": str(plant_id),
                "inspector_id": 1,
                "entity_id": "123",
                "entity_type": "EQUIPMENT",
                "op": op,
                "data": None,
                "message": f"Equipment {op.lower()}d",
            }
        )

    response = client.post("/log", json=log_data)
    assert response.status_code == 201
    assert response.json()["inserted"] == len(operations)


def test_log_without_plant_id(client: TestClient):
    """Test logging without plant_id (for inspector operations)"""
    log_data = [
        {
            "logged_at": "2024-01-01T12:00:00Z",
            "plant_id": None,
            "inspector_id": 1,
            "entity_id": "1",
            "entity_type": "INSPECTOR",
            "op": "UPDATE",
            "data": None,
            "message": "Inspector profile updated",
        }
    ]

    response = client.post("/log", json=log_data)
    assert response.status_code == 201
    assert response.json()["inserted"] == 1


def test_log_with_complex_data(client: TestClient):
    """Test logging with complex JSON data"""
    plant_id = uuid4()

    log_data = [
        {
            "logged_at": "2024-01-01T12:00:00Z",
            "plant_id": str(plant_id),
            "inspector_id": 1,
            "entity_id": "123",
            "entity_type": "EQUIPMENT",
            "op": "UPDATE",
            "data": {
                "old_values": {"name": "Old Name", "status": "active"},
                "new_values": {"name": "New Name", "status": "inactive"},
                "changed_fields": ["name", "status"],
                "nested": {"deep": {"value": 42}},
            },
            "message": "Equipment updated with complex changes",
        }
    ]

    response = client.post("/log", json=log_data)
    assert response.status_code == 201
    assert response.json()["inserted"] == 1


def test_empty_batch(client: TestClient):
    """Test posting empty log batch"""
    response = client.post("/log", json=[])
    assert response.status_code == 201
    assert response.json()["inserted"] == 0
