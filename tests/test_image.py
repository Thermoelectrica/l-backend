"""Integration tests for Image API"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def test_create_image(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test creating a new image"""
    image_id = uuid4()

    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test_image.jpg",
        "image_type": "VISUAL",
        "metadata": {"camera": "Canon EOS", "resolution": "1920x1080"},
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }

    response = client.put("/image", json=image_data)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(image_id)
    assert data["plant_id"] == str(plant_id)
    assert data["original_file_name"] == "test_image.jpg"
    assert data["image_type"] == "VISUAL"
    assert data["metadata"]["camera"] == "Canon EOS"
    assert data["is_deleted"] is False


def test_get_image(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test retrieving an image"""
    image_id = uuid4()

    # First create
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test_image.jpg",
        "image_type": "THERMAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    # Then get
    response = client.get(f"/image/by_id/{image_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(image_id)
    assert data["image_type"] == "THERMAL"


def test_get_nonexistent_image(client: TestClient):
    """Test retrieving a non-existent image"""
    image_id = uuid4()
    response = client.get(f"/image/by_id/{image_id}")
    assert response.status_code == 404


def test_update_image(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test updating an image with optimistic concurrency control"""
    image_id = uuid4()

    # Create initial
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "original.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    create_response = client.put("/image", json=image_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Update with correct timestamp
    updated_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "updated.jpg",
        "image_type": "THERMAL",
        "metadata": {"updated": True},
        "is_deleted": False,
        "server_modified_at": server_modified_at,
    }
    response = client.put("/image", json=updated_data)
    assert response.status_code == 200

    data = response.json()
    assert data["original_file_name"] == "updated.jpg"
    assert data["image_type"] == "THERMAL"
    assert data["metadata"]["updated"] is True


def test_logical_deletion(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test logical deletion of image via is_deleted flag"""
    image_id = uuid4()

    # Create
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    create_response = client.put("/image", json=image_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Mark as deleted
    image_data["server_modified_at"] = server_modified_at
    image_data["is_deleted"] = True
    response = client.put("/image", json=image_data)
    assert response.status_code == 200

    # Verify it's still retrievable but marked as deleted
    get_response = client.get(f"/image/by_id/{image_id}")
    assert get_response.status_code == 200
    assert get_response.json()["is_deleted"] is True


def test_image_types(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test both image types"""
    for image_type in ["VISUAL", "THERMAL"]:
        image_id = uuid4()

        image_data = {
            "id": str(image_id),
            "plant_id": str(plant_id),
            "original_file_name": f"test_{image_type.lower()}.jpg",
            "image_type": image_type,
            "metadata": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
        }

        response = client.put("/image", json=image_data)
        assert response.status_code == 200
        assert response.json()["image_type"] == image_type


def test_concurrent_modification_error(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test that concurrent modification is detected"""
    image_id = uuid4()

    # Create image
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    create_response = client.put("/image", json=image_data)
    assert create_response.status_code == 200
    server_modified_at = create_response.json()["server_modified_at"]

    # Simulate another client updating the image
    image_data["server_modified_at"] = server_modified_at
    image_data["original_file_name"] = "updated_by_client_b.jpg"
    client_b_response = client.put("/image", json=image_data)
    assert client_b_response.status_code == 200

    # Try to update with old timestamp (should fail)
    image_data["server_modified_at"] = server_modified_at
    image_data["original_file_name"] = "updated_by_client_a.jpg"
    response = client.put("/image?force=false", json=image_data)
    assert response.status_code == 409

    error_data = response.json()["detail"]
    assert error_data["type"] == "conflict"
    assert "modified by another client" in error_data["message"].lower()


def test_force_mode_ignores_timestamp(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test that force=true ignores server_modified_at validation"""
    image_id = uuid4()

    # Create image
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    create_response = client.put("/image", json=image_data)
    assert create_response.status_code == 200

    # Update with wrong timestamp but force=true (should succeed)
    image_data["server_modified_at"] = "2024-01-01T00:00:00Z"  # Old timestamp
    image_data["original_file_name"] = "forced_update.jpg"
    response = client.put("/image?force=true", json=image_data)
    assert response.status_code == 200

    data = response.json()
    assert data["original_file_name"] == "forced_update.jpg"


def test_missing_server_modified_at_on_update(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Test that updating existing image without server_modified_at fails"""
    image_id = uuid4()

    # Create image
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    # Try to update without server_modified_at (Pydantic will reject this as 422)
    # Note: server_modified_at is required in the model, so this becomes a validation error
    updated_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "updated.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        # Missing server_modified_at
    }
    response = client.put("/image", json=updated_data)
    assert response.status_code == 422  # Pydantic validation error


@pytest.fixture
def plant_id():
    return uuid4()


@pytest.fixture
def facility_id():
    return uuid4()


def test_get_images_by_plant_id(client: TestClient, plant_id, facility_id, seed_test_plant_and_facility):
    """Test retrieving all images for a plant (joins through equipment and facility)"""

    # Create equipment for the plant
    equipment_id = uuid4()
    equipment_data = {
        "id": str(equipment_id),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Test Equipment",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "control_points": [],
        "defects": [],
    }
    client.put("/equipment", json=equipment_data)

    # Create images for this equipment
    image_id_1 = uuid4()
    image_id_2 = uuid4()

    for image_id, image_type in [(image_id_1, "VISUAL"), (image_id_2, "THERMAL")]:
        image_data = {
            "id": str(image_id),
            "plant_id": str(plant_id),
            "original_file_name": f"test_{image_type.lower()}.jpg",
            "image_type": image_type,
            "metadata": None,
            "is_deleted": False,
            "server_modified_at": "2024-01-01T00:00:00Z",
        }
        client.put("/image", json=image_data)

    # Get images by plant_id
    response = client.get(f"/image/by_plant_id/{plant_id}")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    # Verify our images are in the list
    image_ids = [img["id"] for img in data]
    assert str(image_id_1) in image_ids
    assert str(image_id_2) in image_ids

    # Verify all images belong to this plant
    for image in data:
        assert image["plant_id"] == str(plant_id)


# Tests for modified_since filter


def test_get_images_by_plant_with_modified_since_filter(
    client: TestClient, plant_id, facility_id, seed_test_plant_and_facility
):
    """Test filtering images by plant and modified_since parameter"""
    import time

    # Create equipment for the plant
    equipment_id = uuid4()
    equipment_data = {
        "id": str(equipment_id),
        "facility_id": str(facility_id),
        "parent_id": str(facility_id),
        "name": "Test Equipment",
        "qr_code": None,
        "is_container": False,
        "equipment_type_id": None,
        "estimated_point_count": 10,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
        "control_points": [],
        "defects": [],
    }
    client.put("/equipment", json=equipment_data)

    # Create first image
    image_id_1 = uuid4()
    image_data_1 = {
        "id": str(image_id_1),
        "plant_id": str(plant_id),
        "original_file_name": "image1.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response1 = client.put("/image", json=image_data_1)
    assert response1.status_code == 200
    timestamp1 = response1.json()["server_modified_at"]

    # Wait a moment and create second image
    time.sleep(0.1)

    image_id_2 = uuid4()
    image_data_2 = {
        "id": str(image_id_2),
        "plant_id": str(plant_id),
        "original_file_name": "image2.jpg",
        "image_type": "THERMAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response2 = client.put("/image", json=image_data_2)
    assert response2.status_code == 200
    timestamp2 = response2.json()["server_modified_at"]

    # Get all images for plant without filter - should return both
    response = client.get(f"/image/by_plant_id/{plant_id}")
    assert response.status_code == 200
    all_images = response.json()
    image_ids = [img["id"] for img in all_images]
    assert str(image_id_1) in image_ids
    assert str(image_id_2) in image_ids

    # Get images modified after timestamp1 - should only return image 2
    response = client.get(f"/image/by_plant_id/{plant_id}?modified_since={timestamp1}")
    assert response.status_code == 200
    filtered_images = response.json()
    filtered_ids = [img["id"] for img in filtered_images]
    assert str(image_id_1) not in filtered_ids
    assert str(image_id_2) in filtered_ids

    # Get images modified after timestamp2 - should return none
    response = client.get(f"/image/by_plant_id/{plant_id}?modified_since={timestamp2}")
    assert response.status_code == 200
    filtered_images = response.json()
    assert len(filtered_images) == 0


def test_invalid_plant_id(client: TestClient):
    """Test that creating image with non-existent plant_id fails"""
    image_id = uuid4()
    non_existent_plant_id = uuid4()

    image_data = {
        "id": str(image_id),
        "plant_id": str(non_existent_plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }

    response = client.put("/image", json=image_data)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"].lower()


# ── upload_status tests ────────────────────────────────────────────────────────


def test_new_image_has_unknown_upload_status(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Newly created image must have upload_status == UNKNOWN"""
    image_data = {
        "id": str(uuid4()),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    response = client.put("/image", json=image_data)
    assert response.status_code == 200
    assert response.json()["upload_status"] == "UNKNOWN"


def test_put_does_not_overwrite_upload_status(client: TestClient, plant_id, seed_test_plant_and_facility):
    """PUT /image must never overwrite upload_status set by the S3 callback"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }

    # Create image
    create_resp = client.put("/image", json=image_data)
    assert create_resp.status_code == 200
    server_modified_at = create_resp.json()["server_modified_at"]

    # Simulate S3 callback setting status to UPLOADED
    callback_payload = {
        "messages": [
            {
                "event_metadata": {
                    "event_id": "test-event-id",
                    "event_type": "yandex.cloud.events.storage.ObjectCreate",
                    "created_at": "2024-06-01T10:00:00Z",
                    "tracing_context": {},
                    "cloud_id": "cloud-123",
                    "folder_id": "folder-123",
                },
                "details": {
                    "bucket_id": "test-bucket",
                    "object_id": f"{image_id}.jpg",
                },
            }
        ]
    }
    cb_resp = client.post("/image/s3-upload-callback", json=callback_payload)
    assert cb_resp.status_code == 200

    # Verify upload_status is now UPLOADED
    get_resp = client.get(f"/image/by_id/{image_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["upload_status"] == "UPLOADED"

    # Now do a regular PUT update
    image_data["server_modified_at"] = server_modified_at
    image_data["original_file_name"] = "updated.jpg"
    update_resp = client.put("/image", json=image_data)
    assert update_resp.status_code == 200

    # upload_status must still be UPLOADED — not reset to UNKNOWN
    assert update_resp.json()["upload_status"] == "UPLOADED"


def test_s3_upload_callback_sets_uploaded_status(client: TestClient, plant_id, seed_test_plant_and_facility):
    """POST /image/s3-upload-callback sets upload_status=UPLOADED and server_uploaded_at"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    uploaded_at = "2024-06-01T10:00:00Z"
    callback_payload = {
        "messages": [
            {
                "event_metadata": {
                    "event_id": "evt-001",
                    "event_type": "yandex.cloud.events.storage.ObjectCreate",
                    "created_at": uploaded_at,
                    "tracing_context": {},
                    "cloud_id": "cloud-1",
                    "folder_id": "folder-1",
                },
                "details": {
                    "bucket_id": "my-bucket",
                    "object_id": str(image_id),  # no extension — router strips it
                },
            }
        ]
    }
    response = client.post("/image/s3-upload-callback", json=callback_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed_count"] == 1
    assert body["total_messages"] == 1
    assert body["errors"] is None

    # Verify DB state
    get_resp = client.get(f"/image/by_id/{image_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["upload_status"] == "UPLOADED"
    assert data["server_uploaded_at"] is not None


def test_s3_upload_callback_with_extension_in_object_id(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Callback object_id with .jpg extension is handled correctly"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    callback_payload = {
        "messages": [
            {
                "event_metadata": {
                    "event_id": "evt-002",
                    "event_type": "yandex.cloud.events.storage.ObjectCreate",
                    "created_at": "2024-06-01T12:00:00Z",
                    "tracing_context": {},
                    "cloud_id": "cloud-1",
                    "folder_id": "folder-1",
                },
                "details": {
                    "bucket_id": "my-bucket",
                    "object_id": f"{image_id}.jpg",  # with extension
                },
            }
        ]
    }
    response = client.post("/image/s3-upload-callback", json=callback_payload)
    assert response.status_code == 200
    assert response.json()["processed_count"] == 1

    get_resp = client.get(f"/image/by_id/{image_id}")
    assert get_resp.json()["upload_status"] == "UPLOADED"


def test_s3_upload_callback_skips_non_object_create_events(client: TestClient, plant_id, seed_test_plant_and_facility):
    """Non-ObjectCreate events are skipped and not counted as processed"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    callback_payload = {
        "messages": [
            {
                "event_metadata": {
                    "event_id": "evt-003",
                    "event_type": "yandex.cloud.events.storage.ObjectDelete",
                    "created_at": "2024-06-01T12:00:00Z",
                    "tracing_context": {},
                    "cloud_id": "cloud-1",
                    "folder_id": "folder-1",
                },
                "details": {
                    "bucket_id": "my-bucket",
                    "object_id": str(image_id),
                },
            }
        ]
    }
    response = client.post("/image/s3-upload-callback", json=callback_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["processed_count"] == 0
    assert body["total_messages"] == 1

    # upload_status must remain UNKNOWN
    get_resp = client.get(f"/image/by_id/{image_id}")
    assert get_resp.json()["upload_status"] == "UNKNOWN"


def test_s3_upload_callback_empty_messages(client: TestClient):
    """Empty messages list returns skipped status"""
    response = client.post("/image/s3-upload-callback", json={"messages": []})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skipped"


def test_get_upload_url_returns_presigned_url(client: TestClient, plant_id, seed_test_plant_and_facility):
    """GET /image/{id}/upload_url returns a presigned upload URL"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    fake_url = "https://s3.example.com/upload/test"
    fake_expires = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch("app.routers.image.s3_service") as mock_s3:
        mock_s3.generate_upload_presigned_url.return_value = (fake_url, fake_expires)
        mock_s3.generate_presigned_url.return_value = None

        response = client.get(f"/image/{image_id}/upload_url")

    assert response.status_code == 200
    data = response.json()
    assert data["presigned_url"] == fake_url
    assert "presigned_url_expires_at" in data


def test_get_upload_url_for_nonexistent_image(client: TestClient):
    """GET /image/{id}/upload_url returns 404 for unknown image"""
    with patch("app.routers.image.s3_service") as mock_s3:
        mock_s3.generate_upload_presigned_url.return_value = None
        mock_s3.generate_presigned_url.return_value = None

        response = client.get(f"/image/{uuid4()}/upload_url")

    assert response.status_code == 404


def test_check_image_exists_true(client: TestClient, plant_id, seed_test_plant_and_facility):
    """GET /image/{id}/exists returns exists=true when S3 object is present"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    with patch("app.routers.image.s3_service") as mock_s3:
        mock_s3.check_exists.return_value = True
        mock_s3.generate_presigned_url.return_value = None

        response = client.get(f"/image/{image_id}/exists")

    assert response.status_code == 200
    assert response.json()["exists"] is True


def test_check_image_exists_false(client: TestClient, plant_id, seed_test_plant_and_facility):
    """GET /image/{id}/exists returns exists=false when S3 object is absent"""
    image_id = uuid4()
    image_data = {
        "id": str(image_id),
        "plant_id": str(plant_id),
        "original_file_name": "test.jpg",
        "image_type": "VISUAL",
        "metadata": None,
        "is_deleted": False,
        "server_modified_at": "2024-01-01T00:00:00Z",
    }
    client.put("/image", json=image_data)

    with patch("app.routers.image.s3_service") as mock_s3:
        mock_s3.check_exists.return_value = False
        mock_s3.generate_presigned_url.return_value = None

        response = client.get(f"/image/{image_id}/exists")

    assert response.status_code == 200
    assert response.json()["exists"] is False


def test_check_image_exists_nonexistent_image(client: TestClient):
    """GET /image/{id}/exists returns 404 for unknown image"""
    with patch("app.routers.image.s3_service") as mock_s3:
        mock_s3.check_exists.return_value = False
        mock_s3.generate_presigned_url.return_value = None

        response = client.get(f"/image/{uuid4()}/exists")

    assert response.status_code == 404
