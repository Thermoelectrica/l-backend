"""Integration tests for InspectionSchedule API"""

import asyncpg
import pytest_asyncio
from fastapi.testclient import TestClient

from app.config import settings


@pytest_asyncio.fixture(scope="function", autouse=True)
async def seed_inspection_schedule():
    """Seed a test inspection schedule row directly in the DB."""
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute(
            """
            INSERT INTO lesiv.inspection_schedule (
                id, name, default_interval, severity1_interval,
                severity2_interval, severity3_interval, alert_interval,
                is_deleted, server_modified_at
            ) VALUES (
                1, 'Monthly', 30, 14, 21, 28, 7, FALSE, CURRENT_TIMESTAMP
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
    finally:
        await conn.close()
    yield


def test_get_all_inspection_schedules(client: TestClient):
    """Test retrieving all inspection schedules"""
    response = client.get("/inspection-schedule/all")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    items = data["items"]

    # Seeded row should be present
    assert len(items) >= 1

    # Verify structure of the seeded item
    schedule = next((item for item in items if item["id"] == 1), None)
    assert schedule is not None
    assert schedule["name"] == "Monthly"
    assert schedule["default_interval"] == 30
    assert schedule["severity1_interval"] == 14
    assert schedule["severity2_interval"] == 21
    assert schedule["severity3_interval"] == 28
    assert schedule["alert_interval"] == 7
    assert schedule["is_deleted"] is False
    assert "server_modified_at" in schedule


def test_get_all_inspection_schedules_modified_since(client: TestClient):
    """Test filtering inspection schedules by modified_since parameter"""
    # Future timestamp - should return none
    response = client.get("/inspection-schedule/all?modified_since=2099-12-31T23:59:59Z")
    assert response.status_code == 200
    assert response.json()["items"] == []

    # Very old timestamp - should return the seeded row
    response = client.get("/inspection-schedule/all?modified_since=1900-01-01T00:00:00Z")
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == 1 for item in items)


def test_get_all_inspection_schedules_required_fields(client: TestClient):
    """Test that all required interval fields are present in the response"""
    response = client.get("/inspection-schedule/all")
    assert response.status_code == 200

    items = response.json()["items"]
    assert len(items) >= 1

    required_keys = [
        "id",
        "name",
        "default_interval",
        "severity1_interval",
        "severity2_interval",
        "severity3_interval",
        "alert_interval",
        "server_modified_at",
    ]
    assert all(key in items[0] for key in required_keys)
