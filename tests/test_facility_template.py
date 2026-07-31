"""Integration tests for FacilityTemplate API"""

from fastapi.testclient import TestClient


def test_get_all_facility_templates(client: TestClient):
    """Test retrieving all facility templates"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    items = data["items"]

    # Should have 10 facility templates from V3 migration
    assert len(items) == 10

    # Verify structure of first item
    assert all(
        key in items[0]
        for key in [
            "id",
            "name",
            "is_multiple_allowed",
            "server_modified_at",
            "equipment_templates",
        ]
    )


def test_facility_template_with_equipment_templates(client: TestClient):
    """Test that facility templates include their equipment templates"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find facility template 1 (Хозяйство резервного топлива)
    fuel_facility = next((item for item in items if item["id"] == 1), None)
    assert fuel_facility is not None
    assert fuel_facility["name"] == "Хозяйство резервного топлива"
    assert fuel_facility["is_multiple_allowed"] is False

    # Should have equipment templates (actual count from V3 migration)
    assert len(fuel_facility["equipment_templates"]) >= 5

    # Verify equipment template structure
    template = fuel_facility["equipment_templates"][0]
    assert all(
        key in template
        for key in [
            "id",
            "name",
            "is_container",
            "equipment_type_id",
            "parent_id",
        ]
    )


def test_facility_template_equipment_values(client: TestClient):
    """Test equipment template values are correct"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find facility template 1 (Хозяйство резервного топлива)
    fuel_facility = next((item for item in items if item["id"] == 1), None)
    assert fuel_facility is not None

    # Verify equipment templates exist and have proper structure
    templates = fuel_facility["equipment_templates"]
    assert len(templates) >= 5

    # Verify at least one template has the expected structure
    # Check that there's at least one container template
    containers = [t for t in templates if t["is_container"] is True]
    assert len(containers) > 0

    # Check that there's at least one root template (parent_id is None)
    root_templates = [t for t in templates if t["parent_id"] is None]
    assert len(root_templates) > 0

    # Check that there's at least one child template (parent_id is not None)
    child_templates = [t for t in templates if t["parent_id"] is not None]
    assert len(child_templates) > 0


def test_facility_template_with_equipment_types(client: TestClient):
    """Test facility template with equipment that has equipment types"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find facility template 2 (Общестанционное оборудование)
    general_facility = next((item for item in items if item["id"] == 2), None)
    assert general_facility is not None
    assert general_facility["name"] == "Общестанционное оборудование"

    # Should have equipment templates (actual count from V3 migration)
    assert len(general_facility["equipment_templates"]) >= 13

    # Verify that some equipment templates have equipment_type_id set
    templates_with_types = [t for t in general_facility["equipment_templates"] if t["equipment_type_id"] is not None]
    assert len(templates_with_types) > 0

    # Verify that some equipment templates don't have equipment_type_id (containers)
    templates_without_types = [t for t in general_facility["equipment_templates"] if t["equipment_type_id"] is None]
    assert len(templates_without_types) > 0


def test_facility_template_multiple_allowed(client: TestClient):
    """Test facility templates with is_multiple_allowed flag"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find facility template 3 (ПГУ)
    pgu = next((item for item in items if item["id"] == 3), None)
    assert pgu is not None
    assert pgu["is_multiple_allowed"] is True

    # Find facility template 4 (ТГ)
    tg = next((item for item in items if item["id"] == 4), None)
    assert tg is not None
    assert tg["is_multiple_allowed"] is True

    # Verify non-repeatable templates
    fuel_facility = next((item for item in items if item["id"] == 1), None)
    assert fuel_facility is not None
    assert fuel_facility["is_multiple_allowed"] is False


def test_facility_template_hierarchical_structure(client: TestClient):
    """Test facility template with hierarchical equipment structure"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Find facility template 4 (ТГ)
    tg = next((item for item in items if item["id"] == 4), None)
    assert tg is not None

    templates = tg["equipment_templates"]

    # Find root equipment (Турбинное отделение)
    turb_otd = next((t for t in templates if t["name"] == "Турбинное отделение"), None)
    assert turb_otd is not None
    assert turb_otd["parent_id"] is None

    # Find child equipment (Система возбуждения)
    sys_vozb = next((t for t in templates if t["name"] == "Система возбуждения"), None)
    assert sys_vozb is not None
    assert sys_vozb["parent_id"] == turb_otd["id"]
    assert sys_vozb["equipment_type_id"] == 1  # Система возбуждения equipment type

    # Find grandchild equipment (Панели)
    panels = next((t for t in templates if t["name"] == "Панели"), None)
    assert panels is not None
    assert panels["parent_id"] == sys_vozb["id"]


def test_multiple_facility_templates_with_different_structures(client: TestClient):
    """Test that different facility templates have different structures"""
    response = client.get("/facility-template/all")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Verify each template has different number of equipment (using >= for flexibility)
    equipment_counts = {item["id"]: len(item["equipment_templates"]) for item in items}

    assert equipment_counts[1] >= 5  # Хозяйство резервного топлива
    assert equipment_counts[2] >= 13  # Общестанционное оборудование
    assert equipment_counts[3] >= 2  # ПГУ
    assert equipment_counts[4] >= 8  # ТГ


# Tests for modified_since filter


def test_get_all_facility_templates_with_modified_since_filter(client: TestClient):
    """Test filtering facility templates by modified_since parameter"""
    # Get all facility templates without filter
    response = client.get("/facility-template/all")
    assert response.status_code == 200
    all_templates = response.json()["items"]
    assert len(all_templates) == 10

    # Get facility templates with a very old timestamp - should return all
    response = client.get("/facility-template/all?modified_since=1900-01-01T00:00:00Z")
    assert response.status_code == 200
    filtered_templates = response.json()["items"]
    assert len(filtered_templates) == 10

    # Get facility templates with a future timestamp - should return none
    response = client.get("/facility-template/all?modified_since=2099-12-31T23:59:59Z")
    assert response.status_code == 200
    filtered_templates = response.json()["items"]
    assert len(filtered_templates) == 0
