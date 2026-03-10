import pytest
from httpx import AsyncClient

from crewinsight.api.main import app


def test_health_endpoint():
    assert app.title == "crewinsight"


@pytest.mark.asyncio
async def test_metrics_schema():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200
        payload = response.json()
        assert "average_cost" in payload


@pytest.mark.asyncio
async def test_research_flow():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/research", json={"company": "TestCo", "segment": "Tech"})
        assert response.status_code == 200
        payload = response.json()
        assert "run_id" in payload
        assert payload["status"] == "pending"
        run_id = payload["run_id"]
        
        response = await client.get(f"/api/v1/status/{run_id}")
        assert response.status_code == 200
        status_payload = response.json()
        assert status_payload["run_id"] == run_id
        assert status_payload["status"] in ["pending", "running", "complete", "failed"]

        response = await client.get("/api/v1/report/invalid_id")
        assert response.status_code == 404
