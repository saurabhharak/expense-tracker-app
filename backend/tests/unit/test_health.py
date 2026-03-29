import pytest


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")
    assert "checks" in data


@pytest.mark.asyncio
async def test_health_endpoint_has_check_keys(client):
    response = await client.get("/api/v1/health")
    data = response.json()
    checks = data["checks"]
    assert "db" in checks
    assert "redis" in checks
    assert "s3" in checks
