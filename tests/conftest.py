"""Pytest configuration and fixtures"""

import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

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
        # Выводим подробную ошибку для отладки
        print(f"❌ Flyway migration failed with exit code {e.returncode}")  # development
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
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
                WHERE id IN (1, 2, 3, 5)
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
                WHERE id IN (1, 2, 3, 5)
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


@pytest_asyncio.fixture(scope="function")
async def db_sticker_session():
    """
    Асинхронная фикстура для тестирования, обеспечивающая изоляцию данных.
    1. Создает новое соединение с базой данных.
    2. Начинает новую транзакцию.
    3. Заполняет базу тестовыми данными.
    4. Возвращает (yield) объект соединения, чтобы тесты могли его использовать.
    5. После завершения теста (выхода из yield) явно выполняет ROLLBACK,
    чтобы откатить все изменения и не загрязнить БД.
    6. Закрывает соединение в блоке finally.
    """
    conn = await asyncpg.connect(settings.get_database_url())
    tr = conn.transaction()
    await tr.start()

    try:
        await conn.execute(
            """INSERT INTO lesiv.sticker_installation (
                   id, control_point_id, inspector_id, kind, sticker_type_id,
                   sticker_color, count, installed_at
                ) VALUES (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa9', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   1, 'INSTALLATION', 0, 'YELLOW', 10, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa8', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   2, 'INSTALLATION', 0, 'YELLOW', 3, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa7', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   3, 'INSTALLATION', 0, 'YELLOW', 1, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa1', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   1, 'INSTALLATION', 0, 'YELLOW', 100, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa2', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   51, 'INSTALLATION', 0, 'YELLOW', 100, '2026-07-24T15:42:47.246Z'
                )
                ON CONFLICT (id) DO NOTHING;

               INSERT INTO lesiv.plant (
                   id, name, server_modified_at
                ) VALUES ('15b28768-8bca-4c3b-89a1-ed92d9a8efe2', 'Test Plant', CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO NOTHING;

               INSERT INTO lesiv.inspector_plant_access (
                   inspector_id, plant_id
                ) VALUES (1, '15b28768-8bca-4c3b-89a1-ed92d9a8efe2')
                ON CONFLICT (inspector_id, plant_id) DO NOTHING;
            """
        )
        yield conn

    except Exception:
        await tr.rollback()
        raise
    else:
        await tr.rollback()
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="function")
async def sticker_client(db_sticker_session):
    """
    Асинхронный клиент для тестирования API.
    Использует dependency_overrides для подмены БД.
    """
    from app.database import get_db_connection

    async def mock_get_db():
        return db_sticker_session

    app.dependency_overrides[get_db_connection] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
