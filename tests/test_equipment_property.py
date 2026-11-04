"""Integration tests for EquipmentProperty API"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.auth import AuthService

PUT_BODY_TEMPLATE = {
    "equipment_id": None,  # Will be set in fixture
    "inspection_schedule_id": 1,
    "server_modified_at": None,
}


@pytest.fixture
def auth_service():
    return AuthService()


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
def seeded_equipment(plant_id, facility_id, equipment_id, seed_test_equipment):
    """Equipment (plus its plant and facility) seeded directly in the DB.

    seed_test_equipment inspects request.fixturenames and only does its work when plant_id,
    facility_id *and* equipment_id are all in the test's fixture closure - otherwise it silently
    seeds nothing. This fixture exists to pull all three in, so tests only have to ask for it.
    """
    return equipment_id


@pytest.fixture
def equipment_property_data(seeded_equipment):
    """Minimal valid PUT body, for equipment seeded directly in the DB."""
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["equipment_id"] = str(seeded_equipment)
    return data


# ============================================================================
# CRUD
# ============================================================================


def test_create_equipment_property(client: TestClient, equipment_property_data, equipment_id):
    """Create property for equipment that has no property row yet"""
    response = client.put("/equipment-property", json=equipment_property_data)
    assert response.status_code == 200

    data = response.json()
    assert data["equipment_id"] == str(equipment_id)
    assert data["inspection_schedule_id"] == 1
    assert data["server_modified_at"] is not None  # Server sets it


def test_get_equipment_property(client: TestClient, equipment_property_data, equipment_id):
    """Read property back by equipment id"""
    client.put("/equipment-property", json=equipment_property_data)

    response = client.get(f"/equipment-property/by_id/{equipment_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["equipment_id"] == str(equipment_id)
    assert data["inspection_schedule_id"] == 1


def test_update_equipment_property(client: TestClient, equipment_property_data, equipment_id):
    """Update with the server_modified_at returned by the previous write"""
    create_response = client.put("/equipment-property", json=equipment_property_data)
    assert create_response.status_code == 200

    update = deepcopy(equipment_property_data)
    update["inspection_schedule_id"] = 2
    update["server_modified_at"] = create_response.json()["server_modified_at"]

    response = client.put("/equipment-property", json=update)
    assert response.status_code == 200
    assert response.json()["inspection_schedule_id"] == 2

    # Change is persisted
    get_response = client.get(f"/equipment-property/by_id/{equipment_id}")
    assert get_response.json()["inspection_schedule_id"] == 2


def test_clear_inspection_schedule_id(client: TestClient, equipment_property_data):
    """Setting the schedule back to null is how a property is cleared - there is no is_deleted"""
    create_response = client.put("/equipment-property", json=equipment_property_data)

    update = deepcopy(equipment_property_data)
    update["inspection_schedule_id"] = None
    update["server_modified_at"] = create_response.json()["server_modified_at"]

    response = client.put("/equipment-property", json=update)
    assert response.status_code == 200
    assert response.json()["inspection_schedule_id"] is None


# ============================================================================
# Missing row / unknown equipment
# ============================================================================


def test_get_returns_defaults_when_no_property_row(client: TestClient, seeded_equipment):
    """Equipment with no property row yields an all-default object, not a 404"""
    response = client.get(f"/equipment-property/by_id/{seeded_equipment}")
    assert response.status_code == 200

    data = response.json()
    assert data["equipment_id"] == str(seeded_equipment)
    assert data["inspection_schedule_id"] is None
    assert data["server_modified_at"] is None


def test_get_unknown_equipment_returns_404(client: TestClient):
    """A 404 means the equipment itself is unknown"""
    response = client.get(f"/equipment-property/by_id/{uuid4()}")
    assert response.status_code == 404


def test_write_accepted_before_equipment_is_synced(client: TestClient):
    """Properties may be written for equipment the server has not seen yet.

    The offline client may push the two aggregates in either order, so the router skips the plant
    access check when the equipment cannot be resolved (same as PUT /equipment and PUT /defect).
    The row stays invisible to /all and /by_plant_id until the equipment itself arrives, because
    both resolve the plant through it.
    """
    orphan_id = uuid4()
    response = client.put(
        "/equipment-property",
        json={"equipment_id": str(orphan_id), "inspection_schedule_id": 1, "server_modified_at": None},
    )
    assert response.status_code == 200
    assert response.json()["inspection_schedule_id"] == 1

    # Not readable yet: by_id resolves the plant through the equipment, which does not exist
    assert client.get(f"/equipment-property/by_id/{orphan_id}").status_code == 404

    # ...and the same reason keeps it out of /all
    body = client.get("/equipment-property/all").json()
    assert next((x for x in body["items"] if x["equipment_id"] == str(orphan_id)), None) is None


# ============================================================================
# Optimistic locking
# ============================================================================


def test_concurrent_modification_detected(client: TestClient, equipment_property_data):
    """Updating with a stale server_modified_at returns 409"""
    client.put("/equipment-property", json=equipment_property_data)

    stale = deepcopy(equipment_property_data)
    stale["inspection_schedule_id"] = 3
    stale["server_modified_at"] = "2024-01-01T00:00:00Z"

    response = client.put("/equipment-property", json=stale)
    assert response.status_code == 409

    detail = response.json()["detail"]
    assert detail["server_modified_at"] is not None
    assert detail["client_modified_at"] is not None
    assert detail["conflicts"][0]["field"] == "server_modified_at"


def test_missing_server_modified_at_on_update_detected(client: TestClient, equipment_property_data):
    """Omitting server_modified_at when a row already exists returns 409"""
    client.put("/equipment-property", json=equipment_property_data)

    without_timestamp = deepcopy(equipment_property_data)
    without_timestamp["server_modified_at"] = None

    response = client.put("/equipment-property", json=without_timestamp)
    assert response.status_code == 409
    assert response.json()["detail"]["conflicts"][0]["field"] == "server_modified_at"


def test_force_overrides_stale_timestamp(client: TestClient, equipment_property_data):
    """force=true skips the server_modified_at check"""
    client.put("/equipment-property", json=equipment_property_data)

    stale = deepcopy(equipment_property_data)
    stale["inspection_schedule_id"] = 3
    stale["server_modified_at"] = "2024-01-01T00:00:00Z"

    response = client.put("/equipment-property?force=true", json=stale)
    assert response.status_code == 200
    assert response.json()["inspection_schedule_id"] == 3


# ============================================================================
# List endpoints and sync
# ============================================================================


def test_get_all_wrapped_in_items(client: TestClient, equipment_property_data, equipment_id):
    """/all wraps the collection in an items key"""
    client.put("/equipment-property", json=equipment_property_data)

    response = client.get("/equipment-property/all")
    assert response.status_code == 200

    body = response.json()
    assert "items" in body
    created = next((x for x in body["items"] if x["equipment_id"] == str(equipment_id)), None)
    assert created is not None
    assert created["inspection_schedule_id"] == 1


def test_get_by_plant_id_returns_bare_list(client: TestClient, equipment_property_data, plant_id, equipment_id):
    """/by_plant_id returns a bare list - the documented historical shape"""
    client.put("/equipment-property", json=equipment_property_data)

    response = client.get(f"/equipment-property/by_plant_id/{plant_id}")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body, list)
    assert next((x for x in body if x["equipment_id"] == str(equipment_id)), None) is not None


def test_by_plant_id_omits_equipment_without_properties(
    client: TestClient, plant_id, facility_id, seed_test_plant_and_facility
):
    """Equipment with no property row is absent from the plant listing - nothing to sync"""
    equipment_without_properties = {
        "id": str(uuid4()),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Equipment Without Properties",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }
    assert client.put("/equipment", json=equipment_without_properties).status_code == 200

    response = client.get(f"/equipment-property/by_plant_id/{plant_id}")
    assert response.status_code == 200
    returned_ids = {x["equipment_id"] for x in response.json()}
    assert equipment_without_properties["id"] not in returned_ids


def test_modified_since_filters_list(client: TestClient, equipment_property_data, plant_id, equipment_id):
    """modified_since excludes rows written before the cutoff"""
    client.put("/equipment-property", json=equipment_property_data)

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.get(f"/equipment-property/by_plant_id/{plant_id}", params={"modified_since": future})
    assert response.status_code == 200
    assert next((x for x in response.json() if x["equipment_id"] == str(equipment_id)), None) is None

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    response = client.get(f"/equipment-property/by_plant_id/{plant_id}", params={"modified_since": past})
    assert next((x for x in response.json() if x["equipment_id"] == str(equipment_id)), None) is not None


# ============================================================================
# Claim independence - the reason this aggregate exists
# ============================================================================


def test_write_does_not_require_plant_claim(
    client: TestClient, equipment_property_data, equipment_id, facility_id, plant_id, auth_service
):
    """Properties stay writable while the plant is claimed by a different device.

    Authentication is disabled globally in conftest, and the anonymous user short-circuits both
    plant access and claim validation - so this test must present real tokens for the claim check
    to run at all, otherwise it would pass no matter what the router did.
    """
    claimer_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    other_token = auth_service.create_access_token(2, uuid4(), "MODIFY")

    # Inspector 1 claims the plant (seed_test_equipment granted access to inspectors 1-3)
    claim_response = client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {claimer_token}"},
    )
    assert claim_response.status_code == 200

    # Inspector 2, on a different device, can still set the properties
    response = client.put(
        "/equipment-property",
        json=equipment_property_data,
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 200
    assert response.json()["inspection_schedule_id"] == 1

    # ...while the equipment aggregate itself stays locked for that same device
    equipment_body = {
        "id": str(equipment_id),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Renamed Equipment",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }
    equipment_response = client.put(
        "/equipment",
        json=equipment_body,
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert equipment_response.status_code == 409


async def test_write_requires_inspect_access_level(
    client: TestClient, equipment_property_data, plant_id, auth_service, grant_plant_access
):
    """A READ-level inspector with plant access still cannot write properties"""
    reader_id = 4  # seeded with access_level READ
    await grant_plant_access(plant_id, reader_id)

    reader_token = auth_service.create_access_token(reader_id, uuid4(), "READ")
    response = client.put(
        "/equipment-property",
        json=equipment_property_data,
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 403
