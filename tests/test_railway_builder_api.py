"""
Tests for Railway build API and client behavior.
"""

import io
import json
import sys
import os
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import web_interview
from web_interview import app

from src.builders.railway_builder import RailwayClient, RailwayAPIError, RailwayOdooBuilder
from src.schemas.implementation_spec import create_spec_from_interview


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with web_interview.builds_lock:
        web_interview.builds.clear()
    with app.test_client() as client:
        yield client


def _valid_spec_payload():
    return {
        "spec": {
            "spec_id": "test-123",
            "created_at": "2026-01-01T00:00:00",
            "interview_session_id": "test-session",
            "company": {
                "name": "Test Corp",
                "industry": "Technology",
                "country": "US",
                "currency": "USD",
                "timezone": "UTC",
            },
            "modules": [
                {
                    "module_name": "sale_management",
                    "display_name": "Sales",
                    "install": True,
                    "priority": "high",
                    "settings": {},
                    "depends_on": [],
                    "estimated_minutes": 5,
                    "notes": "",
                }
            ],
            "user_roles": [],
            "data_imports": [],
            "integrations": [],
        }
    }


class _FakeResponse:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


class TestBuildStartRailway:
    def test_rejects_railway_without_token(self, client):
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post(
                "/api/build/start",
                json={**_valid_spec_payload(), "deploy_target": "railway"},
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert "RAILWAY_API_TOKEN" in data["error"]

    def test_railway_with_token_creates_builder(self, client):
        with patch.dict(os.environ, {"RAILWAY_API_TOKEN": "token-123"}):
            with patch("web_interview.threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                with patch("src.builders.railway_builder.RailwayOdooBuilder") as mock_builder:
                    mock_builder.return_value.state = MagicMock(build_id="build-xyz")

                    resp = client.post(
                        "/api/build/start",
                        json={**_valid_spec_payload(), "deploy_target": "railway"},
                        content_type="application/json",
                    )

        assert resp.status_code == 200
        assert mock_builder.call_count == 1
        args, kwargs = mock_builder.call_args
        assert args[1] == "token-123"

    def test_railway_returns_build_id(self, client):
        with patch.dict(os.environ, {"RAILWAY_API_TOKEN": "token-123"}):
            with patch("web_interview.threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                with patch("src.builders.railway_builder.RailwayOdooBuilder") as mock_builder:
                    mock_builder.return_value.state = MagicMock(build_id="build-railway-1")

                    resp = client.post(
                        "/api/build/start",
                        json={**_valid_spec_payload(), "deploy_target": "railway"},
                        content_type="application/json",
                    )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["build_id"] == "build-railway-1"


class TestRailwayClient:
    def test_empty_token_raises(self):
        with pytest.raises(ValueError):
            RailwayClient("")

    def test_whitespace_token_raises(self):
        with pytest.raises(ValueError):
            RailwayClient("  ")

    def test_create_project_sends_correct_query(self, monkeypatch):
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            payload = json.loads(req.data.decode())
            captured["payload"] = payload
            assert "projectCreate" in payload["query"]
            assert payload["variables"] == {"name": "test-project"}
            return _FakeResponse({
                "data": {
                    "projectCreate": {
                        "id": "project-id",
                        "environments": {"edges": [{"node": {"id": "env-id"}}]},
                    }
                }
            })

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        client = RailwayClient("token-123")
        project_id, env_id = client.create_project("test-project")

        assert captured["url"] in RailwayClient.DEFAULT_API_URLS
        assert project_id == "project-id"
        assert env_id == "env-id"

    def test_api_error_includes_url(self, monkeypatch):
        def fake_urlopen(req, timeout=30):
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=500,
                msg="error",
                hdrs=None,
                fp=io.BytesIO(b"boom"),
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

        client = RailwayClient("token-123", api_urls=["https://railway.example/graphql"])

        with pytest.raises(RailwayAPIError) as exc:
            client.create_project("test")

        assert "https://railway.example/graphql" in str(exc.value)


class TestRailwayOdooBuilder:
    def _spec(self):
        return create_spec_from_interview({
            "client_name": "Railway Co",
            "industry": "Services",
            "domains_covered": ["sales"],
            "recommended_modules": ["sale_management"],
            "scoping_responses": [],
            "domain_responses": {},
        })

    def test_state_has_railway_deploy_target(self):
        builder = RailwayOdooBuilder(self._spec(), "token-123")
        assert builder.state.deploy_target == "railway"

    def test_stop_deletes_project(self):
        with patch("src.builders.railway_builder.RailwayClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            builder = RailwayOdooBuilder(self._spec(), "token-123")
            builder._project_id = "proj-123"

            builder.stop()

        mock_client.delete_project.assert_called_once_with("proj-123")

    def test_stop_handles_delete_failure(self):
        with patch("src.builders.railway_builder.RailwayClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.delete_project.side_effect = Exception("boom")
            mock_client_cls.return_value = mock_client

            builder = RailwayOdooBuilder(self._spec(), "token-123")
            builder._project_id = "proj-456"

            builder.stop()

        mock_client.delete_project.assert_called_once_with("proj-456")
