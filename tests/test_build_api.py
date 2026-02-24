"""
Tests for the build API endpoints (/api/build/*).

Uses Flask test client — no live Odoo or Docker needed.
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import web_interview
from web_interview import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    # Clear builds between tests
    with web_interview.builds_lock:
        web_interview.builds.clear()
    with app.test_client() as client:
        yield client


def _valid_spec_payload():
    """Minimal ImplementationSpec dict that passes from_dict()."""
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


class TestBuildStart:
    def test_returns_build_id(self, client):
        with patch("web_interview.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post(
                "/api/build/start",
                json=_valid_spec_payload(),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert "build_id" in data
        assert data["build_id"].startswith("build-")

    def test_rejects_invalid_spec(self, client):
        resp = client.post(
            "/api/build/start",
            json={"spec": {"bad": "data"}},
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_rejects_missing_spec(self, client):
        resp = client.post(
            "/api/build/start",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rejects_non_json_body(self, client):
        resp = client.post(
            "/api/build/start",
            data="not json",
            content_type="text/plain",
        )
        # Flask returns 415 for non-JSON content type
        assert resp.status_code in (400, 415)

    def test_concurrent_build_rejected(self, client):
        """Only one active build at a time."""
        with patch("web_interview.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            # First build succeeds
            resp1 = client.post(
                "/api/build/start",
                json=_valid_spec_payload(),
                content_type="application/json",
            )
            assert resp1.status_code == 200

            # Second build rejected (first is still pending/in_progress)
            resp2 = client.post(
                "/api/build/start",
                json=_valid_spec_payload(),
                content_type="application/json",
            )
            assert resp2.status_code == 409
            assert "already running" in resp2.get_json()["error"]


class TestBuildStatus:
    def test_returns_404_for_unknown(self, client):
        resp = client.get("/api/build/status?build_id=nonexistent-999")
        assert resp.status_code == 404

    def test_returns_400_for_missing_param(self, client):
        resp = client.get("/api/build/status")
        assert resp.status_code == 400

    def test_returns_state_for_known_build(self, client):
        with patch("web_interview.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            start_resp = client.post(
                "/api/build/start",
                json=_valid_spec_payload(),
                content_type="application/json",
            )
            build_id = start_resp.get_json()["build_id"]

        resp = client.get(f"/api/build/status?build_id={build_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["build_id"] == build_id
        assert "tasks" in data
        assert "overall_progress" in data


class TestBuildStop:
    def test_returns_404_for_unknown(self, client):
        resp = client.post(
            "/api/build/stop",
            json={"build_id": "nonexistent-999"},
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_returns_400_for_missing_body(self, client):
        resp = client.post(
            "/api/build/stop",
            data="not json",
            content_type="text/plain",
        )
        # Flask returns 415 for non-JSON content type
        assert resp.status_code in (400, 415)

    def test_stop_calls_builder_stop(self, client):
        with patch("web_interview.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            start_resp = client.post(
                "/api/build/start",
                json=_valid_spec_payload(),
                content_type="application/json",
            )
            build_id = start_resp.get_json()["build_id"]

        with patch("subprocess.run"):
            resp = client.post(
                "/api/build/stop",
                json={"build_id": build_id},
                content_type="application/json",
            )

        assert resp.status_code == 200
        assert resp.get_json()["stopped"] is True

        # Verify builder state was updated
        with web_interview.builds_lock:
            builder = web_interview.builds[build_id]
        assert builder._stop_event.is_set()
