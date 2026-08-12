"""Integration tests for PlantGroup API — includes plant membership (plant_ids)"""

import asyncio
import time
import uuid
from copy import deepcopy

import pytest
from httpx import AsyncClient

PUT_BODY_TEMPLATE = {
    "id": None,  # filled per test
    "name": "Test Group",
    "parent_id": None,
    "is_deleted": False,
    "server_modified_at": "2024-01-01T00:00:00Z",
    "plant_ids": [],
}

PLANT_BODY_TEMPLATE = {
    "name": "Test Plant",
    "claimed_by_device_id": None,
    "claimed_by_user_id": None,
    "claimed_at": None,
    "server_modified_at": "2024-01-01T00:00:00Z",
    "is_deleted": False,
    "facilities": [],
}


@pytest.fixture
def group_id():
    return uuid.uuid4()


@pytest.fixture
def group_data(group_id):
    """Minimal valid PUT body for a group."""
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(group_id)
    return data


@pytest.mark.asyncio
async def _create_plant(api_client: AsyncClient) -> str:
    """Helper: create a plant and return its id."""
    plant_id = str(uuid.uuid4())
    body = deepcopy(PLANT_BODY_TEMPLATE)
    body["id"] = plant_id
    resp = await api_client.put("/plant", json=body)
    assert resp.status_code == 200
    return plant_id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group(api_client: AsyncClient, group_data):
    """Create a new root group and verify the response fields."""
    response = await api_client.put("/plant-group", json=group_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == group_data["id"]
    assert data["name"] == group_data["name"]
    assert data["parent_id"] is None
    assert data["is_deleted"] is False
    assert "server_modified_at" in data
    assert data["plant_ids"] == []


@pytest.mark.asyncio
async def test_create_group_with_parent(api_client: AsyncClient):
    """Create a child group referencing an existing parent."""
    parent_id = str(uuid.uuid4())
    parent_response = await api_client.put(
        "/plant-group",
        json={
            "id": parent_id,
            "name": "Parent Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert parent_response.status_code == 200

    child_id = str(uuid.uuid4())
    response = await api_client.put(
        "/plant-group",
        json={
            "id": child_id,
            "name": "Child Group",
            "parent_id": parent_id,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == child_id
    assert data["parent_id"] == parent_id
    assert data["is_deleted"] is False
    assert "server_modified_at" in data


@pytest.mark.asyncio
async def test_create_group_with_nonexistent_parent(api_client: AsyncClient):
    """Creating a group with a non-existent parent_id triggers a FK violation → 400."""
    nonexistent_id = str(uuid.uuid4())
    response = await api_client.put(
        "/plant-group",
        json={
            "id": str(uuid.uuid4()),
            "name": "Orphan Group",
            "parent_id": nonexistent_id,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["type"] == "foreign_key_violation"


@pytest.mark.asyncio
async def test_get_group(api_client: AsyncClient, group_data):
    """GET /plant-group/by_id/{id} returns the created group."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200
    group_id = create_response.json()["id"]

    response = await api_client.get(f"/plant-group/by_id/{group_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == group_id
    assert data["name"] == group_data["name"]
    assert data["parent_id"] == group_data["parent_id"]
    assert "plant_ids" in data


@pytest.mark.asyncio
async def test_get_nonexistent_group(api_client: AsyncClient):
    """GET /plant-group/by_id/{id} returns 404 for an unknown ID."""
    response = await api_client.get(f"/plant-group/by_id/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_group(api_client: AsyncClient, group_data):
    """Update an existing group name; server_modified_at must advance."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200
    created = create_response.json()
    server_modified_at = created["server_modified_at"]

    updated_data = {
        "id": created["id"],
        "name": "Updated Group Name",
        "parent_id": None,
        "is_deleted": False,
        "server_modified_at": server_modified_at,
        "plant_ids": [],
    }
    response = await api_client.put("/plant-group", json=updated_data)
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Group Name"
    assert data["is_deleted"] is False
    assert data["server_modified_at"] != server_modified_at


@pytest.mark.asyncio
async def test_logical_deletion(api_client: AsyncClient, group_data):
    """Setting is_deleted=True persists and is returned by GET."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200
    created = create_response.json()

    deleted_data = {
        "id": created["id"],
        "name": created["name"],
        "parent_id": None,
        "is_deleted": True,
        "server_modified_at": created["server_modified_at"],
        "plant_ids": [],
    }
    response = await api_client.put("/plant-group", json=deleted_data)
    assert response.status_code == 200
    assert response.json()["is_deleted"] is True

    # GET still returns the group (logical deletion, not physical)
    get_response = await api_client.get(f"/plant-group/by_id/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["is_deleted"] is True


# ---------------------------------------------------------------------------
# Plant membership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_plants_to_group(api_client: AsyncClient, group_data):
    """PUT group with plant_ids — membership is persisted and returned."""
    plant_id_1 = await _create_plant(api_client)
    plant_id_2 = await _create_plant(api_client)

    group_data["plant_ids"] = [plant_id_1, plant_id_2]
    response = await api_client.put("/plant-group", json=group_data)
    assert response.status_code == 200

    data = response.json()
    assert set(data["plant_ids"]) == {plant_id_1, plant_id_2}

    # Verify via GET
    get_resp = await api_client.get(f"/plant-group/by_id/{group_data['id']}")
    assert get_resp.status_code == 200
    assert set(get_resp.json()["plant_ids"]) == {plant_id_1, plant_id_2}


@pytest.mark.asyncio
async def test_remove_plant_from_group(api_client: AsyncClient, group_data):
    """Removing a plant_id from the list removes it from membership."""
    plant_id_1 = await _create_plant(api_client)
    plant_id_2 = await _create_plant(api_client)

    group_data["plant_ids"] = [plant_id_1, plant_id_2]
    create_resp = await api_client.put("/plant-group", json=group_data)
    assert create_resp.status_code == 200
    server_modified_at = create_resp.json()["server_modified_at"]

    # Remove plant_id_2
    group_data["server_modified_at"] = server_modified_at
    group_data["plant_ids"] = [plant_id_1]
    update_resp = await api_client.put("/plant-group", json=group_data)
    assert update_resp.status_code == 200

    data = update_resp.json()
    assert data["plant_ids"] == [plant_id_1]


@pytest.mark.asyncio
async def test_plant_ids_in_get_all_response(api_client: AsyncClient):
    """GET /plant-group/all includes plant_ids for each group."""
    plant_id = await _create_plant(api_client)
    group_id = str(uuid.uuid4())

    await api_client.put(
        "/plant-group",
        json={
            "id": group_id,
            "name": "Group With Plant",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [plant_id],
        },
    )

    response = await api_client.get("/plant-group/all")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body

    group = next((g for g in body["items"] if g["id"] == group_id), None)
    assert group is not None
    assert "plant_ids" in group
    assert plant_id in group["plant_ids"]


@pytest.mark.asyncio
async def test_membership_updates_server_modified_at(api_client: AsyncClient, group_data):
    """Changing plant_ids advances server_modified_at."""
    plant_id = await _create_plant(api_client)

    create_resp = await api_client.put("/plant-group", json=group_data)
    assert create_resp.status_code == 200
    original_ts = create_resp.json()["server_modified_at"]

    await asyncio.sleep(0.05)

    group_data["server_modified_at"] = original_ts
    group_data["plant_ids"] = [plant_id]
    update_resp = await api_client.put("/plant-group", json=group_data)
    assert update_resp.status_code == 200
    assert update_resp.json()["server_modified_at"] != original_ts


# ---------------------------------------------------------------------------
# Stealing guard (move_plants flag)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stealing_rejected_without_move_plants(api_client: AsyncClient):
    """Adding a plant already in another group returns 400 when move_plants=false."""
    plant_id = await _create_plant(api_client)

    group_a_id = str(uuid.uuid4())
    resp_a = await api_client.put(
        "/plant-group",
        json={
            "id": group_a_id,
            "name": "Group A",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [plant_id],
        },
    )
    assert resp_a.status_code == 200

    group_b_id = str(uuid.uuid4())
    resp_b = await api_client.put(
        "/plant-group",
        json={
            "id": group_b_id,
            "name": "Group B",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [plant_id],  # plant already in group A
        },
    )
    assert resp_b.status_code == 400
    assert "already belongs to group" in resp_b.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stealing_allowed_with_move_plants(api_client: AsyncClient):
    """With move_plants=true, a plant is moved from group A to group B."""
    plant_id = await _create_plant(api_client)

    group_a_id = str(uuid.uuid4())
    resp_a = await api_client.put(
        "/plant-group",
        json={
            "id": group_a_id,
            "name": "Group A",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [plant_id],
        },
    )
    assert resp_a.status_code == 200

    group_b_id = str(uuid.uuid4())
    resp_b = await api_client.put(
        "/plant-group?move_plants=true",
        json={
            "id": group_b_id,
            "name": "Group B",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [plant_id],
        },
    )
    assert resp_b.status_code == 200
    assert plant_id in resp_b.json()["plant_ids"]

    # Group A should no longer contain the plant
    get_a = await api_client.get(f"/plant-group/by_id/{group_a_id}")
    assert get_a.status_code == 200
    assert plant_id not in get_a.json()["plant_ids"]


# ---------------------------------------------------------------------------
# Optimistic locking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimistic_locking_conflict(api_client: AsyncClient, group_data):
    """PUT with a stale server_modified_at returns 409."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200

    stale_data = {
        "id": group_data["id"],
        "name": "Conflict Update",
        "parent_id": None,
        "is_deleted": False,
        "server_modified_at": "2000-01-01T00:00:00Z",  # definitely stale
        "plant_ids": [],
    }
    response = await api_client.put("/plant-group", json=stale_data)
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["type"] == "conflict"
    assert "server_modified_at" in body["detail"]


@pytest.mark.asyncio
async def test_optimistic_locking_success(api_client: AsyncClient, group_data):
    """PUT with the correct server_modified_at succeeds."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200
    created = create_response.json()

    update_data = {
        "id": created["id"],
        "name": "Correct Update",
        "parent_id": None,
        "is_deleted": False,
        "server_modified_at": created["server_modified_at"],
        "plant_ids": [],
    }
    response = await api_client.put("/plant-group", json=update_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Correct Update"


@pytest.mark.asyncio
async def test_force_bypasses_optimistic_locking(api_client: AsyncClient, group_data):
    """PUT with force=true ignores stale server_modified_at and succeeds."""
    create_response = await api_client.put("/plant-group", json=group_data)
    assert create_response.status_code == 200

    stale_data = {
        "id": group_data["id"],
        "name": "Force Update",
        "parent_id": None,
        "is_deleted": False,
        "server_modified_at": "2000-01-01T00:00:00Z",  # stale
        "plant_ids": [],
    }
    response = await api_client.put("/plant-group?force=true", json=stale_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Force Update"


# ---------------------------------------------------------------------------
# Cyclic dependency guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_reference_rejected(api_client: AsyncClient):
    """A group cannot be its own parent → 400."""
    group_id = str(uuid.uuid4())
    create_response = await api_client.put(
        "/plant-group",
        json={
            "id": group_id,
            "name": "Self Ref Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()

    response = await api_client.put(
        "/plant-group",
        json={
            "id": group_id,
            "name": "Self Ref Group",
            "parent_id": group_id,
            "is_deleted": False,
            "server_modified_at": created["server_modified_at"],
            "plant_ids": [],
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cyclic_dependency_rejected(api_client: AsyncClient):
    """Moving a group to one of its own descendants creates a cycle → 400."""
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    c_id = str(uuid.uuid4())

    a_resp = await api_client.put(
        "/plant-group",
        json={
            "id": a_id,
            "name": "A",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert a_resp.status_code == 200
    a = a_resp.json()

    b_resp = await api_client.put(
        "/plant-group",
        json={
            "id": b_id,
            "name": "B",
            "parent_id": a_id,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert b_resp.status_code == 200

    c_resp = await api_client.put(
        "/plant-group",
        json={
            "id": c_id,
            "name": "C",
            "parent_id": b_id,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert c_resp.status_code == 200

    # Try to move A under C (would create A→B→C→A cycle)
    response = await api_client.put(
        "/plant-group",
        json={
            "id": a_id,
            "name": "A",
            "parent_id": c_id,
            "is_deleted": False,
            "server_modified_at": a["server_modified_at"],
            "plant_ids": [],
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_groups(api_client: AsyncClient):
    """GET /plant-group/all returns {"items": [...]} containing created groups."""
    g1_id = str(uuid.uuid4())
    g2_id = str(uuid.uuid4())

    r1 = await api_client.put(
        "/plant-group",
        json={
            "id": g1_id,
            "name": "List Group 1",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert r1.status_code == 200

    r2 = await api_client.put(
        "/plant-group",
        json={
            "id": g2_id,
            "name": "List Group 2",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert r2.status_code == 200

    response = await api_client.get("/plant-group/all")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    ids = [g["id"] for g in body["items"]]
    assert g1_id in ids
    assert g2_id in ids


@pytest.mark.asyncio
async def test_get_all_groups_with_modified_since(api_client: AsyncClient):
    """GET /plant-group/all?modified_since=<ts> filters out groups modified before that timestamp."""
    g1_id = str(uuid.uuid4())
    r1 = await api_client.put(
        "/plant-group",
        json={
            "id": g1_id,
            "name": "Before Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert r1.status_code == 200
    timestamp_after_g1 = r1.json()["server_modified_at"]

    time.sleep(0.05)

    g2_id = str(uuid.uuid4())
    r2 = await api_client.put(
        "/plant-group",
        json={
            "id": g2_id,
            "name": "After Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert r2.status_code == 200

    response = await api_client.get(f"/plant-group/all?modified_since={timestamp_after_g1}")
    assert response.status_code == 200
    filtered_ids = [g["id"] for g in response.json()["items"]]
    assert g1_id not in filtered_ids
    assert g2_id in filtered_ids


@pytest.mark.asyncio
async def test_modified_since_reflects_membership_change(api_client: AsyncClient):
    """After a membership change, the group appears in modified_since filter results."""
    plant_id = await _create_plant(api_client)
    group_id = str(uuid.uuid4())

    create_resp = await api_client.put(
        "/plant-group",
        json={
            "id": group_id,
            "name": "Membership Test Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
            "plant_ids": [],
        },
    )
    assert create_resp.status_code == 200
    ts_after_create = create_resp.json()["server_modified_at"]

    time.sleep(0.05)

    # Update membership
    update_resp = await api_client.put(
        "/plant-group",
        json={
            "id": group_id,
            "name": "Membership Test Group",
            "parent_id": None,
            "is_deleted": False,
            "server_modified_at": ts_after_create,
            "plant_ids": [plant_id],
        },
    )
    assert update_resp.status_code == 200

    # Group should appear when filtering by ts_after_create
    response = await api_client.get(f"/plant-group/all?modified_since={ts_after_create}")
    assert response.status_code == 200
    filtered_ids = [g["id"] for g in response.json()["items"]]
    assert group_id in filtered_ids
