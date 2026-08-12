"""Pytest configuration and fixtures"""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

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
def defect_id():
    return uuid4()


class TestTransaction:
    """Контекстный менеджер для изоляции данных теста через транзакцию."""

    def __init__(self, conn):
        self.conn = conn
        self.tr = None

    async def __aenter__(self):
        self.tr = self.conn.transaction()
        await self.tr.start()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.tr is None:
            return False

        try:
            if exc_type:
                await self.tr.rollback()
            else:
                await self.tr.rollback()  # rollback для тестов
        finally:
            self.tr = None
        return False


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
        print(f"❌ Flyway migration failed with exit code {e.returncode}") # development
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        raise


@pytest_asyncio.fixture(scope="function")
async def created_plant():
    """Создает запись plant в БД и удаляет после теста."""
    plant_id = uuid4()
    facility_id = uuid4()
    equipment_id = uuid4()

    # Setup
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute(
            """
            INSERT INTO lesiv.plant (id, name, server_modified_at)
            VALUES ($1, 'Test Plant2', CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO NOTHING
            """,
            plant_id,
        )
        await conn.execute(
            """
            INSERT INTO lesiv.facility (id, plant_id, name)
            VALUES ($1, $2, 'Test Facility2')
            ON CONFLICT (id) DO NOTHING
            """,
            facility_id,
            plant_id,
        )
        await conn.execute(
            """
            INSERT INTO lesiv.equipment (id, facility_id, parent_id, name, estimated_point_count, server_modified_at)
            VALUES ($1, $2, $3, 'Test Equipment2', 10, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO NOTHING
            """,
            equipment_id,
            facility_id,
            facility_id,
        )
    finally:
        await conn.close()

    yield plant_id, facility_id, equipment_id

    # Cleanup — удаляем в обратном порядке (зависимые → родительские)
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        await conn.execute(
            "DELETE FROM lesiv.equipment WHERE id = $1",
            equipment_id,
        )
        await conn.execute(
            "DELETE FROM lesiv.facility WHERE id = $1",
            facility_id,
        )
        await conn.execute(
            "DELETE FROM lesiv.inspector_plant_access WHERE plant_id = $1",
            plant_id,
        )
        await conn.execute(
            "DELETE FROM lesiv.plant WHERE id = $1",
            plant_id,
        )
    finally:
        await conn.close()


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

    yield _grant_access


@pytest_asyncio.fixture(scope="function")
async def db_plant_facility_session(plant_id, facility_id, equipment_id):
    """Seed test plant and facility for each test function that needs them."""

    conn = await asyncpg.connect(settings.get_database_url())
    async with TestTransaction(conn) as db:
        # вставка тестовых данных
        await db.execute(
            """
            INSERT INTO lesiv.plant (id, name, server_modified_at)
            VALUES ($1, 'Test Plant1', CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO NOTHING
            """,
            plant_id,
        )
        await db.execute(
            """
            INSERT INTO lesiv.inspector_plant_access (inspector_id, plant_id)
            SELECT id, $1
            FROM lesiv.inspector
            WHERE id IN (1, 2, 3)
            ON CONFLICT (inspector_id, plant_id) DO NOTHING
            """,
            plant_id,
        )
        await db.execute(
            """
            INSERT INTO lesiv.facility (id, plant_id, name)
            VALUES ($1, $2, 'Test Facility1')
            ON CONFLICT (id) DO NOTHING
            """,
            facility_id,
            plant_id,
        )
        await db.execute(
            """
            INSERT INTO lesiv.equipment (id, facility_id, parent_id, name, estimated_point_count, server_modified_at)
            VALUES ($1, $2, $3, 'Test Equipment1', 10, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO NOTHING
            """,
            equipment_id,
            facility_id,
            facility_id,
        )
        yield db
    await conn.close()


@pytest_asyncio.fixture(scope="function")
async def api_client(db_plant_facility_session):
    """
    Асинхронный клиент для тестирования API.
    Использует dependency_overrides для подмены БД.
    """
    from app.database import get_db_connection

    async def mock_get_db():
        return db_plant_facility_session

    app.dependency_overrides[get_db_connection] = mock_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()



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
    async with TestTransaction(conn) as db:
        await db.execute(
            """INSERT INTO lesiv.sticker_installation (
                   id, control_point_id, inspector_id, kind, sticker_type_id,
                   sticker_color, from_sticker_type_id, count, installed_at
                ) VALUES (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa9', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   1, 'INSTALLATION', 0, 'YELLOW', 0, 10, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa8', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   2, 'INSTALLATION', 0, 'YELLOW', 0, 3, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa7', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   3, 'INSTALLATION', 0, 'YELLOW', 0, 1, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa1', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   1, 'INSTALLATION', 0, 'YELLOW', 0, 100, '2026-07-24T15:42:47.246Z'
                ),
                (
                   '4fa80f53-5717-4562-b3fc-2c963f66afa2', '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                   51, 'INSTALLATION', 0, 'YELLOW', 0, 100, '2026-07-24T15:42:47.246Z'
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
        yield db
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
