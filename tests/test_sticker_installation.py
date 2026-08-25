import copy
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.config import settings


@pytest.fixture(scope="session")
def fresh_sticker():
    return {
        "id": "1fa80f53-5717-4162-b3fc-2c963f66afa9",
        "control_point_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "inspector_id": 8,
        "kind": "INSTALLATION",
        "sticker_type_id": 0,
        "sticker_color": "YELLOW",
        "count": 0,
        "installed_at": "2026-07-24T15:42:47.246Z"
    }


@pytest.mark.asyncio
async def test_get_all_stickers(
    sticker_client: AsyncClient,
):
    """
    Тест проверяет, что GET запрос к /sticker-installation/all возвращает список стикеров
    """
    # Выполняем GET запрос к API
    response = await sticker_client.get("/sticker-installation/all")

    # Проверяем статус код
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Проверяем структуру ответа
    data = response.json()

    # Ожидаемый формат ответа по response_model=StickerInstallaionListResponse
    assert "items" in data
    assert isinstance(data["items"], list), "Response items should be a list"
    assert len(data["items"]) == 5, "Length of data should be 5"


@pytest.mark.asyncio
async def test_get_sticker_by_id_success(
    sticker_client: AsyncClient,
):
    """
    Тест проверяет успешное получение стикера по его ID.
    """
    # UUID первого стикера
    test_sticker_id = "4fa80f53-5717-4562-b3fc-2c963f66afa9"

    # Выполняем GET запрос
    response = await sticker_client.get(f"/sticker-installation/by_id/{test_sticker_id}")

    # Проверяем статус код
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Проверяем структуру ответа
    data = response.json()

    # Проверяем, что вернулся объект, а не список
    assert "id" in data, "Response should contain 'id'"

    # Проверяем, что ID в ответе совпадает с запрошенным
    assert str(data["id"]) == test_sticker_id, f"ID mismatch: expected {test_sticker_id}, got {data['id']}"


@pytest.mark.asyncio
async def test_get_sticker_by_id_not_found(
    sticker_client: AsyncClient
):
    """
    Тест проверяет, что запрос к несуществующему ID возвращает 404.
    """
    # Генерируем случайный UUID, который точно не существует в тестовой базе
    fake_id = uuid4()

    response = await sticker_client.get(f"/sticker-installation/by_id/{fake_id}")

    # Проверяем статус код
    assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"

    # Проверяем сообщение об ошибке
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_stickers_by_plant_id(
    sticker_client: AsyncClient,
):
    """
    Тест проверяет получение стикеров для конкретного plant_id.
    """
    # Указываем созданный в фикстурах plant_id
    plant_id = "15b28768-8bca-4c3b-89a1-ed92d9a8efe2"

    # Выполняем запрос
    response = await sticker_client.get(f"/sticker-installation/by_plant_id/{plant_id}")

    # Проверяем статус код
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Проверяем структуру ответа
    data = response.json()
    assert isinstance(data, list), "Response should be a list"
    assert len(data) == 0, "Length of data should be 2"

    # Используем неккоректный plant_id
    plant_id = "15b28768-8bca-4c3b-19a1-ed92d9a8efe2"

    # Выполняем запрос
    response = await sticker_client.get(f"/sticker-installation/by_plant_id/{plant_id}")

    # Проверяем статус код
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Проверяем структуру ответа
    data = response.json()
    assert len(data) == 0, "Length of data should be 0"


@pytest.mark.asyncio
async def test_upsert_sticker_create_success(
    client: TestClient,
    fresh_sticker,
):
    """
    Тест на создание нового стикера. Использует PUT запрос к эндпоинту.
    """
    # Создание нового стикера
    id_sticker = str(uuid4())
    new_sticker_data = copy.deepcopy(fresh_sticker)
    new_sticker_data["id"] = id_sticker

    # Выполняем PUT запрос
    response = client.put(
        "/sticker-installation/",
        json=new_sticker_data,
    )

    # Проверяем статус код (должно быть 200 OK при успехе)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Проверяем структуру ответа
    data = response.json()
    assert "id" in data, "Response should contain 'id'"
    assert data["id"] == new_sticker_data["id"], "Returned ID should match the created ID"

    # Удаляем вставленную запись, чтобы очистить базу после теста
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        # Проверяем, что запись появилась в БД (после PUT запроса)
        row = await conn.fetchrow(
            "SELECT * FROM lesiv.sticker_installation WHERE id = $1",
            id_sticker
        )
        assert row is not None, "Sticker should exist in DB"
        await conn.execute(
            "DELETE FROM lesiv.sticker_installation WHERE id = $1",
            id_sticker
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_upsert_sticker_conflict_409(
    client: TestClient,
    fresh_sticker,
):
    """
    Тест на конфликт модификации (409 Conflict).
    Симуляция попытки изменения неизменяемого поля (inspector_id) у существующего стикера.
    """
    # Выполняем PUT запрос
    response = client.put(
        "/sticker-installation/",
        json=fresh_sticker,
    )

    # Проверяем статус код
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Модифицируем inspector_id
    modified_sticker = copy.deepcopy(fresh_sticker)
    modified_sticker["inspector_id"] = 3

    # Выполняем повторный PUT запрос
    response = client.put(
        "/sticker-installation/",
        json=modified_sticker,
    )

    # Проверяем статус код конфликта
    assert response.status_code == 409, f"Expected 409 Conflict, got {response.status_code}: {response.text}"

    # Проверяем, что в ответе есть деталь ошибки (convention FastAPI)
    data = response.json()
    assert "detail" in data or "conflict" in data

    # Удаляем вставленную запись, чтобы очистить базу после теста
    conn = await asyncpg.connect(settings.get_database_url())
    try:
        # Проверяем, что запись появилась в БД (после PUT запроса)
        row = await conn.fetchrow(
            "SELECT * FROM lesiv.sticker_installation WHERE id = $1",
            fresh_sticker["id"]
        )
        assert row is not None, "Sticker should exist in DB"
        await conn.execute(
            "DELETE FROM lesiv.sticker_installation WHERE id = $1",
            fresh_sticker["id"]
        )
    finally:
        await conn.close()
