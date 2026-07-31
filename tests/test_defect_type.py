"""Integration tests for DefectType API"""

from fastapi.testclient import TestClient


def test_get_all_defect_types(client: TestClient):
    """Test retrieving all defect types"""
    response = client.get("/defect-type/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    items = data["items"]

    # Should have 13 defect types from init_db.sql
    assert len(items) == 13

    # Verify structure of first item
    assert all(
        key in items[0]
        for key in [
            "id",
            "name",
            "short_name",
            "t_max",
            "t_excess",
            "server_modified_at",
        ]
    )


def test_defect_type_with_t_excess(client: TestClient):
    """Test defect type with t_excess value"""
    response = client.get("/defect-type/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find defect type 1 (Неизолированная токоведущая часть)
    defect = next((item for item in items if item["id"] == 1), None)
    assert defect is not None
    assert "Неизолированная" in defect["name"]
    assert defect["short_name"] == "Ток.вед часть (Неизол)"
    assert defect["t_max"] == 120
    assert defect["t_excess"] == 80


def test_defect_type_without_t_excess(client: TestClient):
    """Test defect type without t_excess value (bearing types)"""
    response = client.get("/defect-type/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find defect type 12 (Подшипник скольжения)
    bearing_slide = next((item for item in items if item["id"] == 12), None)
    assert bearing_slide is not None
    assert bearing_slide["name"] == "Подшипник скольжения"
    assert bearing_slide["short_name"] == "Скольжение"
    assert bearing_slide["t_max"] == 80
    assert bearing_slide["t_excess"] is None

    # Find defect type 13 (Подшипник качения)
    bearing_roll = next((item for item in items if item["id"] == 13), None)
    assert bearing_roll is not None
    assert bearing_roll["name"] == "Подшипник качения"
    assert bearing_roll["short_name"] == "Качение"
    assert bearing_roll["t_max"] == 100
    assert bearing_roll["t_excess"] is None


def test_defect_type_values(client: TestClient):
    """Test specific defect type values are correct"""
    response = client.get("/defect-type/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Check copper contact defect type
    copper_contact = next((item for item in items if item["id"] == 5), None)
    assert copper_contact is not None
    assert copper_contact["name"] == "Контакт из меди или сплавов меди без покрытия, на воздухе"
    assert copper_contact["short_name"] == "Контакт (Cu)"
    assert copper_contact["t_max"] == 75
    assert copper_contact["t_excess"] == 35

    # Check cable defect type
    cable_pvc = next((item for item in items if item["id"] == 9), None)
    assert cable_pvc is not None
    assert cable_pvc["name"] == "Токоведущая жила силового кабеля из поливинилхлоридного пластика и полиэтилена"
    assert cable_pvc["short_name"] == "Каб. нак. (ПВХ)"
    assert cable_pvc["t_max"] == 70
    assert cable_pvc["t_excess"] == 30


def test_multiple_defect_types_with_different_values(client: TestClient):
    """Test that different defect types have different temperature values"""
    response = client.get("/defect-type/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Verify we have variety in t_max values
    t_max_values = set(item["t_max"] for item in items)
    assert len(t_max_values) > 5  # Should have multiple different t_max values

    # Verify some have t_excess and some don't
    with_t_excess = [item for item in items if item["t_excess"] is not None]
    without_t_excess = [item for item in items if item["t_excess"] is None]
    assert len(with_t_excess) > 0
    assert len(without_t_excess) > 0


# Tests for modified_since filter


def test_get_all_defect_types_with_modified_since_filter(client: TestClient):
    """Test filtering defect types by modified_since parameter"""
    # Get all defect types without filter
    response = client.get("/defect-type/all")
    assert response.status_code == 200
    all_types = response.json()["items"]
    assert len(all_types) == 13

    # Get defect types with a very old timestamp - should return all
    response = client.get("/defect-type/all?modified_since=1900-01-01T00:00:00Z")
    assert response.status_code == 200
    filtered_types = response.json()["items"]
    assert len(filtered_types) == 13

    # Get defect types with a future timestamp - should return none
    response = client.get("/defect-type/all?modified_since=2099-12-31T23:59:59Z")
    assert response.status_code == 200
    filtered_types = response.json()["items"]
    assert len(filtered_types) == 0
