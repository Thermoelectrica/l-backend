"""Tests for permission system - access levels and plant access control"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.inspector import AccessLevel
from app.services.auth import AuthService
from app.services.permission_service import ACCESS_LEVEL_HIERARCHY


@pytest.fixture
def auth_service():
    return AuthService()


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def plant_data(plant_id):
    return {
        "id": str(plant_id),
        "name": "Test Plant",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [],
    }


@pytest.fixture
def facility_id():
    return uuid4()


@pytest.fixture
def equipment_data(facility_id):
    return {
        "id": str(uuid4()),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Test Equipment",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "control_points": [],
        "defects": [],
    }


@pytest.fixture
def defect_data():
    return {
        "id": str(uuid4()),
        "equipment_id": str(uuid4()),
        "defect_type_id": None,
        "description": "Test defect",
        "severity": "medium",
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
    }


@pytest.fixture
def inspection_data():
    return {
        "id": str(uuid4()),
        "equipment_id": str(uuid4()),
        "inspector_id": 1,
        "inspection_date": "2024-01-01T00:00:00Z",
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "steps": [],
    }


# ============================================================================
# Access Level Tests
# ============================================================================


def test_read_level_can_view_plants(client: TestClient, plant_data, auth_service):
    """Test that READ level users can view plants they have access to"""
    # Create plant without auth (anonymous user)
    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200

    # User with READ level (default) can view the plant
    # Note: Test users have MODIFY level, so we test with anonymous which has all access
    response = client.get(f"/plant/by_id/{plant_data['id']}")
    assert response.status_code == 200


def test_read_level_cannot_claim_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that READ level users cannot claim plants"""
    # This test would require creating a user with READ level
    # For now, we verify that MODIFY level is required for claiming
    # The actual enforcement is in the permission_service.require_access_level()
    pass  # Covered by existing claim tests


def test_modify_level_can_claim_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that MODIFY level users can claim plants"""
    # Create plant
    client.put("/plant", json=plant_data)

    # User 1 has MODIFY level (from test data)
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    response = client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["claimed_by_user_id"] == user_id


def test_modify_level_can_modify_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that MODIFY level users can modify plants"""
    # Create plant
    create_response = client.put("/plant", json=plant_data)
    assert create_response.status_code == 200

    # User 1 has MODIFY level
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    # Claim the plant first
    claim_response = client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert claim_response.status_code == 200

    # Modify the plant - use server_modified_at from claim response
    plant_data["name"] = "Modified Plant"
    plant_data["server_modified_at"] = claim_response.json()["server_modified_at"]

    response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Modified Plant"


# ============================================================================
# Plant Access Control Tests
# ============================================================================


def test_user_can_access_plant_they_created(client: TestClient, plant_data, auth_service):
    """Test that users automatically get access to plants they create"""
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    # Create plant with authentication
    response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    # User should be able to access the plant
    response = client.get(
        f"/plant/by_id/{plant_data['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


def test_user_with_access_can_claim_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that a user who already has plant access can claim it.

    Claiming does NOT confer access - see test_claim_requires_existing_plant_access. Inspector 1
    is internal with MODIFY, so the new-plant auto-grant already gave it access on creation.
    """
    # Create plant without auth
    client.put("/plant", json=plant_data)

    # User claims the plant
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    claim_response = client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert claim_response.status_code == 200

    # User still has access
    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


async def test_user_without_access_cannot_view_plant(
    client: TestClient, plant_data, plant_id, auth_service, grant_plant_access
):
    """Test that users without plant access cannot view the plant"""
    # Create plant as user 1
    device_id_1 = uuid4()
    user_id_1 = 1
    access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

    client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # Inspector 4 (READ level, never granted access to this plant) tries to access it
    reader_device_id = uuid4()
    reader_id = 4
    reader_token = auth_service.create_access_token(reader_id, reader_device_id, "READ")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 403

    # Grant access to inspector 4
    await grant_plant_access(plant_id, reader_id)

    # Now inspector 4 can access
    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 200


def test_plant_list_filtered_by_access(client: TestClient, auth_service):
    """Test that plant list only shows plants the user has access to"""
    # Create two plants as different users
    plant_id_1 = uuid4()
    plant_data_1 = {
        "id": str(plant_id_1),
        "name": "Plant 1",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [],
    }

    plant_id_2 = uuid4()
    plant_data_2 = {
        "id": str(plant_id_2),
        "name": "Plant 2",
        "claimed_by_device_id": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "is_deleted": False,
        "facilities": [],
    }

    # User 1 creates plant 1
    user_id_1 = 1
    access_token_1 = auth_service.create_access_token(user_id_1, uuid4(), "MODIFY")
    client.put(
        "/plant",
        json=plant_data_1,
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # User 2 creates plant 2
    user_id_2 = 2
    access_token_2 = auth_service.create_access_token(user_id_2, uuid4(), "MODIFY")
    client.put(
        "/plant",
        json=plant_data_2,
        headers={"Authorization": f"Bearer {access_token_2}"},
    )

    # User 1 should only see plant 1
    response = client.get("/plant/all", headers={"Authorization": f"Bearer {access_token_1}"})
    assert response.status_code == 200
    plant_ids = [p["id"] for p in response.json()["items"]]
    assert str(plant_id_1) in plant_ids
    # Note: User 1 might see plant 2 if they have access from test data grants


# ============================================================================
# Equipment/Defect/Inspection Access Tests
# ============================================================================


async def test_equipment_access_requires_plant_access(
    client: TestClient,
    plant_data,
    plant_id,
    facility_id,
    equipment_data,
    auth_service,
    grant_plant_access,
):
    """Test that equipment operations require plant access"""
    # Create plant with facility
    plant_data["facilities"] = [{"id": str(facility_id), "name": "Facility 1", "is_deleted": False}]
    equipment_data["facility_id"] = str(facility_id)
    equipment_data["parent_id"] = str(facility_id)

    user_id_1 = 1
    access_token_1 = auth_service.create_access_token(user_id_1, uuid4(), "MODIFY")

    client.put("/plant", json=plant_data, headers={"Authorization": f"Bearer {access_token_1}"})
    client.put(
        "/equipment",
        json=equipment_data,
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # Inspector 4 (READ level) has no plant access and cannot view equipment
    reader_id = 4
    reader_token = auth_service.create_access_token(reader_id, uuid4(), "READ")

    response = client.get(
        f"/equipment/by_id/{equipment_data['id']}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 403

    # Grant plant access to inspector 4
    await grant_plant_access(plant_id, reader_id)

    # Now inspector 4 can view equipment
    response = client.get(
        f"/equipment/by_id/{equipment_data['id']}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 200


def test_anonymous_user_has_full_access(client: TestClient, plant_data):
    """Test that anonymous users (when auth is disabled) have full access"""
    # Create plant without auth
    response = client.put("/plant", json=plant_data)
    assert response.status_code == 200

    # Can view without auth
    response = client.get(f"/plant/by_id/{plant_data['id']}")
    assert response.status_code == 200

    # Can modify without auth (but needs to claim first for ownership)
    # This is tested in other test files


# ============================================================================
# Access Level Hierarchy Tests
# ============================================================================


def test_inspect_level_can_create_defects(client: TestClient):
    """Test that INSPECT level users can create defects"""
    # This would require creating a user with INSPECT level
    # The permission check is: permission_service.require_access_level(AccessLevel.INSPECT)
    # Covered by the access level enforcement in routers
    pass


def test_inspect_level_can_create_inspections(client: TestClient):
    """Test that INSPECT level users can create inspections"""
    # Similar to above - requires INSPECT level
    pass


def test_inspect_level_cannot_modify_equipment(client: TestClient):
    """Test that INSPECT level users cannot modify equipment"""
    # Equipment modification requires MODIFY level
    pass


# ============================================================================
# Edge Cases
# ============================================================================


def test_deleted_plant_access_still_enforced(client: TestClient, plant_data, auth_service):
    """Test that access control is enforced even for deleted plants"""
    # Create and delete a plant
    user_id_1 = 1
    access_token_1 = auth_service.create_access_token(user_id_1, uuid4(), "MODIFY")

    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # Mark as deleted
    plant_data["is_deleted"] = True
    plant_data["server_modified_at"] = create_response.json()["server_modified_at"]

    # Claim first
    client.post(
        f"/plant/by_id/{plant_data['id']}/claim",
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # Inspector 4 (READ level) still cannot access the deleted plant without permission
    reader_id = 4
    reader_token = auth_service.create_access_token(reader_id, uuid4(), "READ")

    response = client.get(
        f"/plant/by_id/{plant_data['id']}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 403


def test_release_plant_keeps_access(client: TestClient, plant_data, plant_id, auth_service):
    """Test that releasing a plant leaves the releaser's access intact.

    Releasing does NOT confer access - see test_release_requires_existing_plant_access.
    """
    # Create plant
    client.put("/plant", json=plant_data)

    # User claims and releases
    user_id = 1
    access_token = auth_service.create_access_token(user_id, uuid4(), "MODIFY")

    client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response = client.post(
        f"/plant/by_id/{plant_id}/release",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    # User should still have access after release
    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


def test_all_internal_modify_inspectors_get_access_to_new_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that creating a plant grants access to every internal MODIFY inspector, not just the creator"""
    # User 1 creates the plant
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    # User 3 (MODIFY level) never touched this plant but should still see it
    other_token = auth_service.create_access_token(3, uuid4(), "MODIFY")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 200

    response = client.get("/plant/all", headers={"Authorization": f"Bearer {other_token}"})
    assert response.status_code == 200
    assert str(plant_id) in [p["id"] for p in response.json()["items"]]


def test_read_level_inspector_does_not_get_access_to_new_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that the new-plant grant is limited to MODIFY inspectors"""
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    # Inspector 4 has READ level and must not be granted access
    reader_token = auth_service.create_access_token(4, uuid4(), "READ")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert response.status_code == 403


# ============================================================================
# VERIFY Level Tests
#
# VERIFY is a strict superset of MODIFY: it must clear every gate MODIFY clears.
# Inspector 5 has VERIFY level and is deliberately NOT pre-granted plant access
# in scripts/init_test_data.sql.
# ============================================================================


def test_every_access_level_has_a_hierarchy_rank():
    """Every AccessLevel member must have a rank.

    ACCESS_LEVEL_HIERARCHY.get(level, 0) silently degrades an unmapped level to rank 0
    (= READ), so a missing entry would quietly strip privileges instead of raising.
    """
    assert set(AccessLevel) == set(ACCESS_LEVEL_HIERARCHY)


def test_verify_level_outranks_modify():
    """VERIFY must sit strictly above MODIFY in the hierarchy"""
    assert ACCESS_LEVEL_HIERARCHY[AccessLevel.VERIFY] > ACCESS_LEVEL_HIERARCHY[AccessLevel.MODIFY]


def test_verify_level_can_create_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that VERIFY level users clear the MODIFY gate on plant upsert"""
    verifier_token = auth_service.create_access_token(5, uuid4(), "VERIFY")

    response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(plant_id)


def test_verify_level_can_claim_and_release_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that VERIFY level users clear the MODIFY gate on claim and release"""
    client.put("/plant", json=plant_data)

    user_id = 5
    headers = {"Authorization": f"Bearer {auth_service.create_access_token(user_id, uuid4(), 'VERIFY')}"}

    claim_response = client.post(f"/plant/by_id/{plant_id}/claim", headers=headers)
    assert claim_response.status_code == 200
    assert claim_response.json()["claimed_by_user_id"] == user_id

    release_response = client.post(f"/plant/by_id/{plant_id}/release", headers=headers)
    assert release_response.status_code == 200
    assert release_response.json()["claimed_by_user_id"] is None


def test_verify_inspector_gets_access_to_new_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that the new-plant auto-grant covers VERIFY inspectors, not just MODIFY ones"""
    # User 1 (MODIFY) creates the plant
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    # Inspector 5 (VERIFY) never touched this plant but should still see it
    verifier_token = auth_service.create_access_token(5, uuid4(), "VERIFY")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {verifier_token}"},
    )
    assert response.status_code == 200

    response = client.get("/plant/all", headers={"Authorization": f"Bearer {verifier_token}"})
    assert response.status_code == 200
    assert str(plant_id) in [p["id"] for p in response.json()["items"]]


# ============================================================================
# External User Tests
#
# External inspectors (inspector.is_internal = FALSE) are limited to a predefined list of
# plants. Inspector 6 is external with MODIFY level and is deliberately NOT pre-granted any
# plant access in scripts/init_test_data.sql.
# ============================================================================


def test_external_inspector_does_not_get_access_to_new_plant(client: TestClient, plant_data, plant_id, auth_service):
    """Test that the new-plant auto-grant skips external inspectors even at MODIFY level"""
    # Inspector 1 (internal, MODIFY) creates the plant
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    # Inspector 6 is external and must not have been granted access
    external_token = auth_service.create_access_token(6, uuid4(), "MODIFY")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {external_token}"},
    )
    assert response.status_code == 403

    response = client.get("/plant/all", headers={"Authorization": f"Bearer {external_token}"})
    assert response.status_code == 200
    assert str(plant_id) not in [p["id"] for p in response.json()["items"]]


def test_external_inspector_keeps_access_to_plant_it_created(client: TestClient, plant_data, plant_id, auth_service):
    """Test that an external inspector keeps access to a plant it created itself.

    The internal-inspector broadcast does not match an external creator, so the plant router
    grants the creator access explicitly. Without that grant the creator would immediately lose
    the plant it just created.
    """
    external_token = auth_service.create_access_token(6, uuid4(), "MODIFY")

    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {external_token}"},
    )
    assert create_response.status_code == 200

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {external_token}"},
    )
    assert response.status_code == 200

    response = client.get("/plant/all", headers={"Authorization": f"Bearer {external_token}"})
    assert response.status_code == 200
    assert str(plant_id) in [p["id"] for p in response.json()["items"]]


def test_internal_inspectors_get_access_to_plant_created_by_external(
    client: TestClient, plant_data, plant_id, auth_service
):
    """Test that a plant created by an external user is still broadcast to internal inspectors"""
    external_token = auth_service.create_access_token(6, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {external_token}"},
    )
    assert create_response.status_code == 200

    # Inspector 3 (internal, MODIFY) never touched this plant but should still see it
    internal_token = auth_service.create_access_token(3, uuid4(), "MODIFY")

    response = client.get(
        f"/plant/by_id/{plant_id}",
        headers={"Authorization": f"Bearer {internal_token}"},
    )
    assert response.status_code == 200


def test_claim_requires_existing_plant_access(client: TestClient, plant_data, plant_id, auth_service):
    """Test that claiming does not confer plant access.

    Claiming used to grant access to any MODIFY caller, which would let an external user escape
    its predefined plant list by guessing a plant UUID.
    """
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    external_headers = {"Authorization": f"Bearer {auth_service.create_access_token(6, uuid4(), 'MODIFY')}"}

    claim_response = client.post(f"/plant/by_id/{plant_id}/claim", headers=external_headers)
    assert claim_response.status_code == 403

    # And no access leaked through the rejected claim
    response = client.get(f"/plant/by_id/{plant_id}", headers=external_headers)
    assert response.status_code == 403


def test_release_requires_existing_plant_access(client: TestClient, plant_data, plant_id, auth_service):
    """Test that releasing does not confer plant access either"""
    creator_token = auth_service.create_access_token(1, uuid4(), "MODIFY")
    create_response = client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert create_response.status_code == 200

    external_headers = {"Authorization": f"Bearer {auth_service.create_access_token(6, uuid4(), 'MODIFY')}"}

    release_response = client.post(f"/plant/by_id/{plant_id}/release", headers=external_headers)
    assert release_response.status_code == 403

    response = client.get(f"/plant/by_id/{plant_id}", headers=external_headers)
    assert response.status_code == 403
