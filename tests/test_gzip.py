"""Tests for GZip response compression"""


def test_large_response_is_gzipped(client):
    """Responses over minimum_size are compressed when the client accepts gzip."""
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in response.headers.get("vary", "").lower()

    # TestClient decompresses transparently, so the body must still parse
    assert "paths" in response.json()


def test_gzipped_response_keeps_content_length(client):
    """
    Compressed responses must still carry a Content-Length.

    Regression guard for middleware ordering: GZipMiddleware has to be registered
    *before* AuthMiddleware in app/main.py so it sits inside it. AuthMiddleware is a
    BaseHTTPMiddleware, which re-streams responses with more_body=True; if GZip wrapped
    it from the outside, Starlette would take its streaming branch and delete
    Content-Length, turning every response chunked.
    """
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.headers.get("content-encoding") == "gzip"
    assert "content-length" in response.headers

    # Content-Length describes the compressed payload, which must be smaller
    compressed_size = int(response.headers["content-length"])
    assert compressed_size < len(response.content)


def test_response_not_gzipped_without_accept_encoding(client):
    """Clients that don't accept gzip get an uncompressed response."""
    response = client.get("/openapi.json", headers={"Accept-Encoding": "identity"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert "paths" in response.json()


def test_small_response_is_not_gzipped(client):
    """Responses below minimum_size are left uncompressed."""
    response = client.get("/", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.json() == {"status": "ok", "message": "L-Inspector Backend API"}
