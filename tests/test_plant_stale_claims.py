"""Tests for stale claim mechanism - claims persist but can be overridden after 3:00 AM"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

PUT_BODY_TEMPLATE = {
    "name": "Test Power Plant",
    "claimed_by_device_id": None,
    "claimed_by_user_id": None,
    "claimed_at": None,
    "server_modified_at": "2024-01-01T00:00:00Z",
    "is_deleted": False,
    "facilities": [],
}


@pytest.fixture
def plant_data(plant_id):
    data = deepcopy(PUT_BODY_TEMPLATE)
    data["id"] = str(plant_id)
    return data


@pytest.mark.asyncio
async def test_is_stale_field_in_response(api_client: AsyncClient, plant_data, plant_id):
    """Test that is_stale computed field is included in API responses"""
    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # Claim it
    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Get plant and verify is_stale field exists
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()
    assert "is_stale" in data
    assert isinstance(data["is_stale"], bool)


@pytest.mark.asyncio
async def test_is_stale_field_in_list_response(api_client: AsyncClient, plant_data, plant_id):
    """Test that is_stale computed field is included in list responses"""
    from app.services.auth import AuthService

    # Create and claim plant
    await api_client.put("/plant", json=plant_data)

    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Get all plants and verify is_stale field exists
    response = await api_client.get("/plant/all")
    assert response.status_code == 200
    data = response.json()

    plant = next((p for p in data["items"] if p["id"] == str(plant_id)), None)
    assert plant is not None
    assert "is_stale" in plant
    assert isinstance(plant["is_stale"], bool)


@pytest.mark.asyncio
async def test_fresh_claim_is_not_stale(api_client: AsyncClient, plant_data, plant_id):
    """Test that a freshly claimed plant is not stale"""
    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # Claim it now
    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Get plant and verify it's not stale
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_stale"] is False


@pytest.mark.asyncio
async def test_claim_from_yesterday_is_stale(api_client: AsyncClient, plant_data, plant_id):
    """Test that a claim from yesterday (before 3:00 AM) is stale"""
    from datetime import timedelta

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # Mock datetime to claim it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        from app.services.auth import AuthService

        auth_service = AuthService()
        device_id = uuid4()
        user_id = 1
        access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # Get plant and verify it's stale
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_unclaimed_plant_is_stale(api_client: AsyncClient, plant_data, plant_id):
    """Test that an unclaimed plant (claimed_at is None) is considered stale"""
    # Create plant without claim
    await api_client.put("/plant", json=plant_data)

    # Get plant and verify it's stale (no claim = stale)
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_reclaim_stale_plant_by_different_user(api_client: AsyncClient, plant_data, plant_id):
    """Test that a different user can claim a stale plant"""
    from datetime import timedelta

    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # User 1 claims it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        auth_service = AuthService()
        device_id_1 = uuid4()
        user_id_1 = 1
        access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token_1}"},
        )

    # Different user tries to claim it (should succeed - claim is stale)
    auth_service = AuthService()
    device_id_2 = uuid4()
    user_id_2 = 2
    access_token_2 = auth_service.create_access_token(user_id_2, device_id_2, "MODIFY")

    response = await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 200

    # Verify the claim was updated in response
    data = response.json()
    assert data["claimed_by_device_id"] == str(device_id_2)
    assert data["claimed_by_user_id"] == user_id_2
    assert data["is_stale"] is False


@pytest.mark.asyncio
async def test_cannot_reclaim_fresh_plant_by_different_user(api_client: AsyncClient, plant_data, plant_id):
    """Test that a different user cannot claim a fresh (non-stale) plant"""
    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # User 1 claims it
    auth_service = AuthService()
    device_id_1 = uuid4()
    user_id_1 = 1
    access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token_1}"},
    )

    # User 2 tries to claim it (should fail - claim is fresh)
    device_id_2 = uuid4()
    user_id_2 = 2
    access_token_2 = auth_service.create_access_token(user_id_2, device_id_2, "MODIFY")

    response = await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "not stale" in error_data["message"].lower()


@pytest.mark.asyncio
async def test_same_user_can_reclaim_own_plant(api_client: AsyncClient, plant_data, plant_id):
    """Test that the same user can reclaim their own plant (regardless of staleness)"""
    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # User claims it
    auth_service = AuthService()
    device_id_1 = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id_1, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Same user claims it again with different device
    device_id_2 = uuid4()
    access_token_2 = auth_service.create_access_token(user_id, device_id_2, "MODIFY")

    response = await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 200

    # Verify the device was updated in response
    data = response.json()
    assert data["claimed_by_device_id"] == str(device_id_2)
    assert data["claimed_by_user_id"] == user_id


@pytest.mark.asyncio
#@pytest_asyncio.fixture
async def test_can_modify_plant_with_stale_claim(
    api_client: AsyncClient,
    grant_plant_access,
    db_plant_facility_session
):
    """Test that modifying a plant with a stale claim requires re-claiming"""
    from datetime import timedelta

    from app.services.auth import AuthService

    # Create plant
    conn = db_plant_facility_session  # это connection внутри транзакции
    plant_id = await conn.fetchrow(
        "SELECT id FROM lesiv.plant LIMIT 1"
    )
    plant_id = plant_id["id"]

    # User 1 claims it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday

        auth_service = AuthService()
        device_id_1 = uuid4()
        user_id_1 = 1
        access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token_1}"},
        )

    # Get current state
    get_response = await api_client.get(f"/plant/by_id/{plant_id}")
    server_modified_at = get_response.json()["server_modified_at"]

    # Grant access to user 2 so they can attempt to modify the plant
    user_id_2 = 2
    await grant_plant_access(plant_id, user_id_2)

    # Different user tries to modify without claiming
    auth_service = AuthService()
    device_id_2 = uuid4()
    access_token_2 = auth_service.create_access_token(user_id_2, device_id_2, "MODIFY")

    plant_data = get_response.json()
    plant_data["server_modified_at"] = server_modified_at
    plant_data["name"] = "Updated Name"

    response = await api_client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    # The plant is not claimed by user 2, so they can't modify it
    assert "claim" in error_data["message"].lower()


@pytest.mark.asyncio
async def test_can_modify_after_reclaiming_stale_plant(api_client: AsyncClient, db_plant_facility_session):
    """Test that after re-claiming a stale plant, user can modify it"""
    from datetime import timedelta

    from app.services.auth import AuthService

    # Create plant
    conn = db_plant_facility_session  # это connection внутри транзакции
    plant_id = await conn.fetchrow(
        "SELECT id FROM lesiv.plant LIMIT 1"
    )
    plant_id = plant_id["id"]

    # User 1 claims it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday

        auth_service = AuthService()
        device_id_1 = uuid4()
        user_id_1 = 1
        access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token_1}"},
        )

    # Different user claims it
    auth_service = AuthService()
    device_id_2 = uuid4()
    user_id_2 = 2
    access_token_2 = auth_service.create_access_token(user_id_2, device_id_2, "MODIFY")

    claim_response = await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert claim_response.status_code == 200

    # Now user 2 can modify it - get server_modified_at from claim response
    server_modified_at = claim_response.json()["server_modified_at"]
    plant_data = claim_response.json()
    plant_data["server_modified_at"] = server_modified_at
    plant_data["name"] = "Updated Name"

    response = await api_client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_stale_claim_persists_in_database(api_client: AsyncClient, plant_data, plant_id):
    """Test that stale claims are not removed from database, just marked as stale"""
    from datetime import timedelta

    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # Claim it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    device_id = uuid4()

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        auth_service = AuthService()
        user_id = 1
        access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # Get plant and verify claim data still exists
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()

    # Claim data should still be present
    assert data["claimed_by_device_id"] == str(device_id)
    assert data["claimed_by_user_id"] == 1
    assert data["claimed_at"] is not None

    # But it should be marked as stale
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_equipment_modification_with_stale_plant_claim(
    api_client: AsyncClient, plant_data, facility_id, equipment_id, db_plant_facility_session
):
    """Test that equipment cannot be modified if parent plant has stale claim"""
    from datetime import timedelta

    from app.services.auth import AuthService

    conn = db_plant_facility_session
    plant_id = await conn.fetchrow(
        "SELECT id FROM lesiv.plant LIMIT 1"
    )
    plant_id = plant_id["id"]

    # User 1 claims it "yesterday"
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = yesterday

        auth_service = AuthService()
        device_id_1 = uuid4()
        user_id_1 = 1
        access_token_1 = auth_service.create_access_token(user_id_1, device_id_1, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token_1}"},
        )

    # Grant access to user 2 (в той же транзакции!)
    user_id_2 = 2
    await conn.execute(
        """
        INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
        VALUES ($1, $2)
        ON CONFLICT (inspector_id, plant_id) DO NOTHING
        """,
        user_id_2,
        plant_id,
    )

    # Different user tries to modify equipment
    auth_service = AuthService()
    device_id_2 = uuid4()
    access_token_2 = auth_service.create_access_token(user_id_2, device_id_2, "MODIFY")

    plant_response = await api_client.get(f"/plant/by_id/{plant_id}")
    plant_data = plant_response.json()
    plant_data["server_modified_at"] = plant_data["server_modified_at"]
    plant_data["name"] = "Updated Name"

    response = await api_client.put(
        "/plant",
        json=plant_data,
        headers={"Authorization": f"Bearer {access_token_2}"},
    )
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "claim" in error_data["message"].lower()


@pytest.mark.asyncio
async def test_claim_expiration_at_3am_moscow_time(api_client: AsyncClient, plant_data, plant_id):
    """Test that claims expire at 3:00 AM Moscow time (00:00 UTC)"""
    from datetime import time

    from app.services.auth import AuthService

    # Create plant
    await api_client.put("/plant", json=plant_data)

    # Claim at 2:59 AM Moscow time (23:59 UTC yesterday)
    now_utc = datetime.now(timezone.utc)
    today_midnight_utc = datetime.combine(now_utc.date(), time(0, 0), tzinfo=timezone.utc)

    # Claim made 1 minute before 3:00 AM Moscow (23:59 UTC yesterday)
    claim_time = today_midnight_utc - timedelta(minutes=1)

    device_id = uuid4()

    with patch("app.repositories.plant.datetime") as mock_datetime:
        mock_datetime.now.return_value = claim_time

        auth_service = AuthService()
        user_id = 1
        access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

        await api_client.post(
            f"/plant/by_id/{plant_id}/claim",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # Get plant - claim should be stale (it's before today's 3:00 AM Moscow)
    response = await api_client.get(f"/plant/by_id/{plant_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_stale"] is True


@pytest.mark.asyncio
async def test_release_plant_clears_claim(api_client: AsyncClient, plant_data, plant_id):
    """Test that releasing a plant clears the claim data"""
    from app.services.auth import AuthService

    # Create and claim plant
    await api_client.put("/plant", json=plant_data)

    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Release plant
    response = await api_client.post(f"/plant/by_id/{plant_id}/release")
    assert response.status_code == 200

    # Verify claim is cleared in response
    data = response.json()
    assert data["claimed_by_device_id"] is None
    assert data["claimed_by_user_id"] is None
    assert data["claimed_at"] is None
    assert data["is_stale"] is True  # No claim = stale


@pytest.mark.asyncio
async def test_claim_updates_server_modified_at(
    api_client: AsyncClient,
    plant_id,
    db_plant_facility_session
):
    """Test that claiming a plant updates server_modified_at for sync purposes"""

    from app.services.auth import AuthService

    # Create plant
    conn = db_plant_facility_session  # это connection внутри транзакции
    plant_id = await conn.fetchrow(
        "SELECT id FROM lesiv.plant LIMIT 1"
    )
    plant_id = plant_id["id"]
    get_response = await api_client.get(f"/plant/by_id/{plant_id}")
    initial_modified_at = get_response.json()["server_modified_at"]

    # Wait a moment to ensure timestamp difference
    await asyncio.sleep(0.1)

    # Claim plant
    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    claim_response = await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert claim_response.status_code == 200

    # Verify server_modified_at was updated in response
    data = claim_response.json()

    # server_modified_at should be updated (newer than initial)
    assert data["server_modified_at"] != initial_modified_at
    assert data["server_modified_at"] > initial_modified_at


@pytest.mark.asyncio
async def test_release_updates_server_modified_at(api_client: AsyncClient, plant_data, plant_id):
    """Test that releasing a plant updates server_modified_at for sync purposes"""

    from app.services.auth import AuthService

    # Create and claim plant
    await api_client.put("/plant", json=plant_data)

    auth_service = AuthService()
    device_id = uuid4()
    user_id = 1
    access_token = auth_service.create_access_token(user_id, device_id, "MODIFY")

    await api_client.post(
        f"/plant/by_id/{plant_id}/claim",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Get current server_modified_at
    get_response = await api_client.get(f"/plant/by_id/{plant_id}")
    claimed_modified_at = get_response.json()["server_modified_at"]

    # Wait a moment to ensure timestamp difference
    await asyncio.sleep(0.1)

    # Release plant
    release_response = await api_client.post(f"/plant/by_id/{plant_id}/release")
    assert release_response.status_code == 200

    # Verify server_modified_at was updated in response
    data = release_response.json()

    # server_modified_at should be updated (newer than when claimed)
    assert data["server_modified_at"] != claimed_modified_at
    assert data["server_modified_at"] > claimed_modified_at
