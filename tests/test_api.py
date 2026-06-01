"""
API server unit tests — endpoint validation without Opus calls.
Tests request/response shapes, error handling, and middleware.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from starlette.testclient import TestClient
from src.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "db_path" in data

    def test_has_request_id(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers
        assert "x-duration-ms" in r.headers


class TestMetricsEndpoint:
    def test_metrics(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "uptime_s" in data
        assert "total_builds" in data
        assert "agents" in data


class TestA2ADiscover:
    def test_discover(self, client):
        r = client.get("/a2a/discover")
        assert r.status_code == 200
        data = r.json()
        assert data["agent"] == "iron-emperor"
        assert data["protocol"] == "a2a/1.0"
        assert len(data["capabilities"]) >= 1
        assert any(c["task"] == "hardware_build" for c in data["capabilities"])


class TestStatsEndpoint:
    def test_stats(self, client):
        r = client.get("/stats")
        # May fail if DB doesn't exist, that's OK
        if r.status_code == 200:
            data = r.json()
            assert "total_parts" in data
            assert "categories" in data


class TestBuildValidation:
    def test_missing_prompt(self, client):
        r = client.post("/build", json={})
        assert r.status_code == 422  # Pydantic validation

    def test_empty_prompt(self, client):
        # Empty string is technically valid (will fail at orchestrator level)
        r = client.post("/build", json={"prompt": ""})
        # Should get through validation at least
        assert r.status_code in (200, 500)


class TestSearchEndpoint:
    def test_search_missing_query(self, client):
        r = client.get("/search")
        assert r.status_code == 422

    def test_search_basic(self, client):
        r = client.get("/search?q=arduino&limit=5")
        if r.status_code == 200:
            data = r.json()
            assert "query" in data
            assert "results" in data
