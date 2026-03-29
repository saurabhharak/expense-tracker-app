import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_correct_status_code(client):
    response = await client.get("/api/v1/health")
    data = response.json()
    assert "status" in data
    assert "checks" in data
    # Status code must match the reported health status
    if data["status"] == "healthy":
        assert response.status_code == 200
    elif data["status"] == "degraded":
        assert response.status_code == 207
    else:
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_health_endpoint_has_check_keys(client):
    response = await client.get("/api/v1/health")
    data = response.json()
    checks = data["checks"]
    assert "db" in checks
    assert "redis" in checks
    assert "s3" in checks
