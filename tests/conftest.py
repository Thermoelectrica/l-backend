"""Pytest configuration and fixtures"""

import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

# Load test-specific environment variables from .env.test
test_env_file = Path(__file__).parent.parent / ".env.test"
if test_env_file.exists():
    load_dotenv(test_env_file, override=True)

# Disable authentication for all tests
settings.require_auth = False


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_test_data():
    """Seed test data once per test session using Flyway migrations and test data script."""
    # Verify Flyway credentials are set in environment variables
    # These should be set to a user with schema management permissions
    if not all(
        [
            os.getenv("FLYWAY_URL"),
            os.getenv("FLYWAY_USER"),
            os.getenv("FLYWAY_PASSWORD"),
        ]
    ):
        raise ValueError(
            "Flyway credentials not found in environment variables. "
            "Please set FLYWAY_URL, FLYWAY_USER, and FLYWAY_PASSWORD in .env.test file"
        )

    # Run Flyway migrate from the db directory
    # Flyway will read credentials from environment variables
    try:
        result = subprocess.run(["flyway", "migrate"], cwd="db", capture_output=True, text=True, check=True)
        print(f"Flyway migration output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Flyway migration failed: {e.stderr}")
        raise

    # Load test-specific data (test inspectors)
    # This is separate from migrations as it's test-only data
    test_data_script = Path(__file__).parent.parent / "scripts" / "init_test_data.sql"
    if test_data_script.exists():
        conn = await asyncpg.connect(settings.get_database_url())
        try:
            with open(test_data_script, "r") as f:
                sql = f.read()
            await conn.execute(sql)
            print("Test data loaded successfully")
        except Exception as e:
            print(f"Failed to load test data: {e}")
            raise
        finally:
            await conn.close()
    else:
        print(f"Warning: Test data script not found at {test_data_script}")

    yield


@pytest_asyncio.fixture(scope="function")
async def seed_test_plant_and_facility(request):
    """Seed test plant and facility for each test function that needs them."""
    # Get plant_id if available
    plant_id = None
    facility_id = None

    if "plant_id" in request.fixturenames:
        plant_id = request.getfixturevalue("plant_id")

    if "facility_id" in request.fixturenames:
        facility_id = request.getfixturevalue("facility_id")

    # If we have a plant_id, seed the plant and facility
    if plant_id:
        conn = await asyncpg.connect(settings.get_database_url())
        try:
            # Insert test plant if not exists
            await conn.execute(
                """
                INSERT INTO lesiv.plant (id, name, server_modified_at)
                VALUES ($1, 'Test Plant', CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING
            """,
                plant_id,
            )

            # Grant access to test inspectors for this plant
            await conn.execute(
                """
                INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
                SELECT id, $1
                FROM lesiv.inspector
                WHERE id IN (1, 2, 3)
                ON CONFLICT (inspector_id, plant_id) DO NOTHING
            """,
                plant_id,
            )

            # Insert test facility if not exists (only if facility_id is provided)
            if facility_id:
                await conn.execute(
                    """
                    INSERT INTO lesiv.facility (id, plant_id, name)
                    VALUES ($1, $2, 'Test Facility')
                    ON CONFLICT (id) DO NOTHING
                """,
                    facility_id,
                    plant_id,
                )
        finally:
            await conn.close()

    yield


@pytest_asyncio.fixture(scope="function")
async def seed_test_equipment(request):
    """Seed test equipment for each test function that needs it."""
    # Only run if equipment_id fixture is available
    if "equipment_id" not in request.fixturenames:
        yield
        return

    # First ensure plant and facility exist
    if "plant_id" in request.fixturenames and "facility_id" in request.fixturenames:
        plant_id = request.getfixturevalue("plant_id")
        facility_id = request.getfixturevalue("facility_id")
        equipment_id = request.getfixturevalue("equipment_id")

        conn = await asyncpg.connect(settings.get_database_url())
        try:
            # Insert test plant if not exists
            await conn.execute(
                """
                INSERT INTO lesiv.plant (id, name, server_modified_at)
                VALUES ($1, 'Test Plant', CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING
            """,
                plant_id,
            )

            # Grant access to test inspectors for this plant
            await conn.execute(
                """
                INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
                SELECT id, $1
                FROM lesiv.inspector
                WHERE id IN (1, 2, 3)
                ON CONFLICT (inspector_id, plant_id) DO NOTHING
            """,
                plant_id,
            )

            # Insert test facility if not exists
            await conn.execute(
                """
                INSERT INTO lesiv.facility (id, plant_id, name)
                VALUES ($1, $2, 'Test Facility')
                ON CONFLICT (id) DO NOTHING
            """,
                facility_id,
                plant_id,
            )

            # Insert test equipment if not exists
            await conn.execute(
                """
                INSERT INTO lesiv.equipment (id, facility_id, parent_id, name, is_container, server_modified_at)
                VALUES ($1, $2, $2, 'Test Equipment', false, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING
            """,
                equipment_id,
                facility_id,
            )
        finally:
            await conn.close()

    yield


@pytest_asyncio.fixture(scope="function")
async def grant_plant_access():
    """Helper fixture to grant plant access to inspectors during tests."""

    async def _grant_access(plant_id, inspector_id):
        """Grant access to a plant for an inspector."""
        conn = await asyncpg.connect(settings.get_database_url())
        try:
            await conn.execute(
                """
                INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
                VALUES ($1, $2)
                ON CONFLICT (inspector_id, plant_id) DO NOTHING
                """,
                inspector_id,
                plant_id,
            )
        finally:
            await conn.close()

    return _grant_access


@pytest.fixture(scope="function")
def client():
    """Create test client - FastAPI TestClient handles lifespan events."""
    with TestClient(app) as test_client:
        yield test_client
