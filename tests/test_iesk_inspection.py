"""Integration tests for IESK inspection API"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import settings
from app.services.auth import AuthService

PUT_BODY_TEMPLATE = {
    "inspector_id": 1,
    "started_at": "2024-01-01T10:00:00Z",
    "completed_at": None,
    "status": "IN_PROGRESS",
    "oil_level": 1,
    "bugs": 0,
    "dimensions": 2,
    "locks": 1,
    "stickers": 3,
    "comment": "Течь масла не обнаружена",
    "is_deleted": False,
    "server_modified_at": "2024-01-01T10:00:00Z",
    "image_links": [],
}


@pytest.fixture
def iesk_inspection_id():
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
def image_id_1():
    return uuid4()


@pytest.fixture
def image_id_2():
    return uuid4()


@pytest.fixture
def auth_service():
    return AuthService()


@pytest_asyncio.fixture
async def seed_iesk_plant(plant_id, seed_test_equipment):
    """Mark the seeded test plant as an IESK plant (lesiv.iesk_plant)."""
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute(
            "INSERT INTO lesiv.iesk_plant (plant_id) VALUES ($1) ON CONFLICT (plant_id) DO NOTHING",
            plant_id,
        )
    finally:
        await conn.close()
    yield


@pytest.fixture
def iesk_inspection_data(iesk_inspection_id, equipment_id, plant_id, facility_id, seed_iesk_plant):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(iesk_inspection_id)
    data["equipment_id"] = str(equipment_id)
    return data


async def _seed_plant_with_equipment(inspector_ids: list[int]):
    """Seed a separate plant/facility/equipment with access for the given inspectors only."""
    plant_id, facility_id, equipment_id = uuid4(), uuid4(), uuid4()
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute("INSERT INTO lesiv.plant (id, name) VALUES ($1, 'Other Plant')", plant_id)
        await conn.execute(
            "INSERT INTO lesiv.facility (id, plant_id, name) VALUES ($1, $2, 'Other Facility')", facility_id, plant_id
        )
        await conn.execute(
            "INSERT INTO lesiv.equipment (id, facility_id, parent_id, name, is_container)"
            " VALUES ($1, $2, $2, 'Other Equipment', false)",
            equipment_id,
            facility_id,
        )
        for inspector_id in inspector_ids:
            await conn.execute(
                "INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id) VALUES ($1, $2)"
                " ON CONFLICT DO NOTHING",
                inspector_id,
                plant_id,
            )
    finally:
        await conn.close()
    return plant_id, equipment_id


# ============================================================================
# CRUD
# ============================================================================


def test_create_iesk_inspection(client: TestClient, iesk_inspection_data, iesk_inspection_id, equipment_id):
    """Creating a new IESK inspection returns the stored aggregate with a server timestamp"""
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(iesk_inspection_id)
    assert data["equipment_id"] == str(equipment_id)
    assert data["status"] == "IN_PROGRESS"
    assert data["completed_at"] is None
    assert data["oil_level"] == 1
    assert data["dimensions"] == 2
    assert data["comment"] == "Течь масла не обнаружена"
    assert data["image_links"] == []
    assert data["server_modified_at"] != iesk_inspection_data["server_modified_at"]


def test_get_iesk_inspection_by_id(client: TestClient, iesk_inspection_data, iesk_inspection_id):
    """GET /by_id returns the same aggregate that PUT stored"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()

    response = client.get(f"/iesk-inspection/by_id/{iesk_inspection_id}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_nonexistent_iesk_inspection(client: TestClient):
    """GET /by_id for an unknown ID returns 404"""
    response = client.get(f"/iesk-inspection/by_id/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "IESK inspection not found"


def test_status_defaults_to_planned(client: TestClient, iesk_inspection_data):
    """status defaults to PLANNED when omitted, as for inspection"""
    del iesk_inspection_data["status"]
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 200
    assert response.json()["status"] == "PLANNED"


def test_complete_iesk_inspection(client: TestClient, iesk_inspection_data):
    """Completing the inspection stores status COMPLETED and completed_at"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()

    created["status"] = "COMPLETED"
    created["completed_at"] = "2024-01-01T10:30:00Z"
    response = client.put("/iesk-inspection", json=created)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert datetime.fromisoformat(data["completed_at"]) == datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)


def test_invalid_status_rejected(client: TestClient, iesk_inspection_data):
    """An unknown status is rejected with 422"""
    iesk_inspection_data["status"] = "DONE"
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 422
    assert response.json()["type"] == "request_validation_error"


def test_update_iesk_inspection(client: TestClient, iesk_inspection_data):
    """Updating with the current server_modified_at succeeds and moves the timestamp"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()

    created["comment"] = "Обновлено"
    created["bugs"] = 5
    response = client.put("/iesk-inspection", json=created)
    assert response.status_code == 200
    data = response.json()
    assert data["comment"] == "Обновлено"
    assert data["bugs"] == 5
    assert data["server_modified_at"] != created["server_modified_at"]


def test_logical_delete_iesk_inspection(client: TestClient, iesk_inspection_data, iesk_inspection_id):
    """is_deleted=true is stored and returned by GET"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()

    created["is_deleted"] = True
    assert client.put("/iesk-inspection", json=created).status_code == 200

    response = client.get(f"/iesk-inspection/by_id/{iesk_inspection_id}")
    assert response.status_code == 200
    assert response.json()["is_deleted"] is True


def test_nullable_checklist(client: TestClient, iesk_inspection_data):
    """Checklist marks and comment may be empty (inspection created before being filled in)"""
    for field in ("oil_level", "bugs", "dimensions", "locks", "stickers", "comment"):
        iesk_inspection_data[field] = None
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 200
    data = response.json()
    assert data["oil_level"] is None and data["comment"] is None


# ============================================================================
# Optimistic locking
# ============================================================================


def test_concurrent_modification_detected(client: TestClient, iesk_inspection_data):
    """A stale server_modified_at is rejected with 409 ConflictError"""
    client.put("/iesk-inspection", json=iesk_inspection_data)

    iesk_inspection_data["comment"] = "stale"
    iesk_inspection_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 409

    detail = response.json()["detail"]
    assert detail["type"] == "conflict"
    assert detail["message"] == "IeskInspection was modified by another client"
    assert detail["conflicts"][0]["field"] == "server_modified_at"


def test_force_overrides_stale_timestamp(client: TestClient, iesk_inspection_data):
    """force=true overwrites regardless of server_modified_at"""
    client.put("/iesk-inspection", json=iesk_inspection_data)

    iesk_inspection_data["comment"] = "forced"
    iesk_inspection_data["server_modified_at"] = "2020-01-01T00:00:00Z"
    response = client.put("/iesk-inspection?force=true", json=iesk_inspection_data)
    assert response.status_code == 200
    assert response.json()["comment"] == "forced"


# ============================================================================
# Image links
# ============================================================================


def test_image_links_sync(client: TestClient, iesk_inspection_data, iesk_inspection_id, image_id_1, image_id_2):
    """Links missing from the request become tombstones; re-adding a link revives it"""
    iesk_inspection_data["image_links"] = [{"image_id": str(image_id_1)}, {"image_id": str(image_id_2)}]
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()
    assert {link["image_id"] for link in created["image_links"]} == {str(image_id_1), str(image_id_2)}
    assert all(link["is_deleted"] is False for link in created["image_links"])

    # Remove image 2
    created["image_links"] = [{"image_id": str(image_id_1)}]
    updated = client.put("/iesk-inspection", json=created).json()
    links = {link["image_id"]: link["is_deleted"] for link in updated["image_links"]}
    assert links == {str(image_id_1): False, str(image_id_2): True}

    # Re-add image 2
    updated["image_links"] = [{"image_id": str(image_id_1)}, {"image_id": str(image_id_2)}]
    revived = client.put("/iesk-inspection", json=updated).json()
    assert all(link["is_deleted"] is False for link in revived["image_links"])

    response = client.get(f"/iesk-inspection/by_id/{iesk_inspection_id}")
    assert len(response.json()["image_links"]) == 2


# ============================================================================
# Lists and modified_since
# ============================================================================


def test_get_by_plant_id_returns_bare_list(
    client: TestClient, iesk_inspection_data, iesk_inspection_id, plant_id, image_id_1
):
    """GET /by_plant_id returns a bare list of full aggregates"""
    iesk_inspection_data["image_links"] = [{"image_id": str(image_id_1)}]
    client.put("/iesk-inspection", json=iesk_inspection_data)

    response = client.get(f"/iesk-inspection/by_plant_id/{plant_id}")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    item = next((x for x in items if x["id"] == str(iesk_inspection_id)), None)
    assert item is not None
    assert item["image_links"] == [{"image_id": str(image_id_1), "is_deleted": False}]


def test_get_by_plant_id_modified_since(client: TestClient, iesk_inspection_data, iesk_inspection_id, plant_id):
    """modified_since filters by server_modified_at (strictly greater)"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()
    created_at = created["server_modified_at"]

    response = client.get(f"/iesk-inspection/by_plant_id/{plant_id}", params={"modified_since": created_at})
    assert response.status_code == 200
    assert all(x["id"] != str(iesk_inspection_id) for x in response.json())

    created["comment"] = "changed"
    client.put("/iesk-inspection", json=created)
    response = client.get(f"/iesk-inspection/by_plant_id/{plant_id}", params={"modified_since": created_at})
    item = next((x for x in response.json() if x["id"] == str(iesk_inspection_id)), None)
    assert item is not None
    assert item["comment"] == "changed"


def test_get_by_plant_id_other_plant(client: TestClient, iesk_inspection_data, iesk_inspection_id):
    """IESK inspections of one plant are not returned for another plant"""
    client.put("/iesk-inspection", json=iesk_inspection_data)

    response = client.get(f"/iesk-inspection/by_plant_id/{uuid4()}")
    assert response.status_code == 200
    assert response.json() == []


def test_get_all(client: TestClient, iesk_inspection_data, iesk_inspection_id):
    """GET /all returns lightweight items wrapped in {'items': [...]}"""
    client.put("/iesk-inspection", json=iesk_inspection_data)

    response = client.get("/iesk-inspection/all")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    item = next((x for x in items if x["id"] == str(iesk_inspection_id)), None)
    assert item is not None
    assert item["status"] == "IN_PROGRESS"
    assert "image_links" not in item and "comment" not in item


def test_get_all_modified_since(client: TestClient, iesk_inspection_data, iesk_inspection_id):
    """GET /all honours modified_since"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()
    after = (datetime.fromisoformat(created["server_modified_at"]) + timedelta(seconds=1)).isoformat()

    response = client.get("/iesk-inspection/all", params={"modified_since": after})
    assert all(x["id"] != str(iesk_inspection_id) for x in response.json()["items"])


# ============================================================================
# Business rules
# ============================================================================


def test_plant_type_is_not_checked(client: TestClient, plant_id, facility_id, equipment_id, seed_test_equipment):
    """An IESK inspection on a plant without the IESK marker is stored as is (the client decides)"""
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(uuid4())
    data["equipment_id"] = str(equipment_id)

    response = client.put("/iesk-inspection", json=data)
    assert response.status_code == 200


def test_regular_inspection_allowed_on_iesk_plant(
    client: TestClient, plant_id, facility_id, equipment_id, seed_iesk_plant
):
    """Ordinary inspections keep working on IESK plants - nothing is blocked"""
    body = {
        "id": str(uuid4()),
        "equipment_id": str(equipment_id),
        "inspector_id": 1,
        "started_at": "2024-01-01T10:00:00Z",
        "status": "IN_PROGRESS",
        "server_modified_at": "2024-01-01T10:00:00Z",
        "steps": [],
    }
    response = client.put("/inspection", json=body)
    assert response.status_code == 200


def test_unknown_equipment_rejected(client: TestClient, iesk_inspection_data):
    """PUT with unknown equipment_id returns 400"""
    iesk_inspection_data["equipment_id"] = str(uuid4())
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_unknown_inspector_rejected(client: TestClient, iesk_inspection_data):
    """PUT with unknown inspector_id is rejected by the FK (400 foreign_key_violation)"""
    iesk_inspection_data["inspector_id"] = 999999
    response = client.put("/iesk-inspection", json=iesk_inspection_data)
    assert response.status_code == 400
    assert response.json()["type"] == "foreign_key_violation"


# ============================================================================
# Permissions
# ============================================================================


def test_read_level_cannot_put(client: TestClient, iesk_inspection_data, auth_service):
    """READ access level cannot create IESK inspections"""
    token = auth_service.create_access_token(4, uuid4(), "READ")
    response = client.put("/iesk-inspection", json=iesk_inspection_data, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_inspect_level_can_put(client: TestClient, iesk_inspection_data, auth_service):
    """MODIFY (>= INSPECT) inspector with plant access can create IESK inspections without a claim"""
    token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    response = client.put("/iesk-inspection", json=iesk_inspection_data, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_no_plant_access(client: TestClient, iesk_inspection_data, iesk_inspection_id, plant_id, auth_service):
    """An inspector without access to the plant gets 403 on PUT and GET"""
    client.put("/iesk-inspection", json=iesk_inspection_data)
    token = auth_service.create_access_token(6, uuid4(), "MODIFY")  # external, no access to this plant
    headers = {"Authorization": f"Bearer {token}"}

    assert client.put("/iesk-inspection", json=iesk_inspection_data, headers=headers).status_code == 403
    assert client.get(f"/iesk-inspection/by_id/{iesk_inspection_id}", headers=headers).status_code == 403
    assert client.get(f"/iesk-inspection/by_plant_id/{plant_id}", headers=headers).status_code == 403
    all_items = client.get("/iesk-inspection/all", headers=headers).json()["items"]
    assert all(x["id"] != str(iesk_inspection_id) for x in all_items)


async def test_cannot_move_inspection_out_of_inaccessible_plant(client: TestClient, iesk_inspection_data, auth_service):
    """An inspection cannot be moved from a plant the user has no access to into an accessible one"""
    created = client.put("/iesk-inspection", json=iesk_inspection_data).json()  # test plant, inspectors 1-3

    _, own_equipment_id = await _seed_plant_with_equipment(inspector_ids=[6])
    token = auth_service.create_access_token(6, uuid4(), "MODIFY")
    created["equipment_id"] = str(own_equipment_id)
    response = client.put("/iesk-inspection", json=created, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
