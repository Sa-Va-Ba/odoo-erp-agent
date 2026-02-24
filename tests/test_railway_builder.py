"""
Tests for Railway client transport behavior.

Focuses on endpoint selection/fallback and Cloudflare 1010 handling.
"""

import io
import json
import asyncio
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.builders.railway_builder import RailwayClient, RailwayAPIError, RailwayOdooBuilder
from src.builders.odoo_builder import BuildTask, TaskType, TaskStatus
from src.schemas.implementation_spec import create_spec_from_interview


class _FakeResponse:
    def __init__(self, body: dict):
        self._payload = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def _http_error(url: str, code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body.encode()),
    )


def test_defaults_to_api_then_backboard(monkeypatch):
    monkeypatch.delenv("RAILWAY_API_URL", raising=False)

    client = RailwayClient("token-123")

    assert client.api_urls == [
        "https://api.railway.app/graphql/v2",
        "https://backboard.railway.com/graphql/v2",
    ]


def test_uses_env_api_url_override(monkeypatch):
    monkeypatch.setenv("RAILWAY_API_URL", "https://custom.example/graphql")

    client = RailwayClient("token-123")

    assert client.api_urls == ["https://custom.example/graphql"]


def test_cloudflare_1010_falls_back_to_next_endpoint(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req.full_url)
        if req.full_url == "https://api.railway.app/graphql/v2":
            raise _http_error(req.full_url, 403, "error code: 1010")
        return _FakeResponse({
            "data": {
                "projectCreate": {
                    "id": "project-id",
                    "environments": {"edges": [{"node": {"id": "env-id"}}]},
                }
            }
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = RailwayClient(
        "  token-123  ",
        api_urls=[
            "https://api.railway.app/graphql/v2",
            "https://backboard.railway.com/graphql/v2",
        ],
    )

    project_id, env_id = client.create_project("test")

    assert project_id == "project-id"
    assert env_id == "env-id"
    assert calls == [
        "https://api.railway.app/graphql/v2",
        "https://backboard.railway.com/graphql/v2",
    ]


def test_cloudflare_1010_surfaces_actionable_error(monkeypatch):
    def fake_urlopen(req, timeout=30):
        raise _http_error(req.full_url, 403, "<html>error code: 1010</html>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = RailwayClient("token-123", api_urls=["https://backboard.railway.com/graphql/v2"])

    with pytest.raises(RailwayAPIError) as exc:
        client.create_project("test")

    message = str(exc.value)
    assert "Cloudflare 1010" in message
    assert "RAILWAY_API_URL=https://api.railway.app/graphql/v2" in message


class _FakeRailway:
    def __init__(self):
        self.set_vars_calls = []
        self.start_command = None

    def create_project(self, name):
        return "project-id", "env-id"

    def create_service(self, project_id, name):
        if name == "Postgres":
            return "pg-service-id"
        return "odoo-service-id"

    def set_service_source(self, service_id, image):
        return None

    def set_service_variables(self, project_id, env_id, service_id, variables):
        self.set_vars_calls.append((service_id, variables))

    def set_service_start_command(self, service_id, start_command):
        self.start_command = start_command

    def create_service_domain(self, service_id, env_id):
        return "odoo-test.up.railway.app"


def test_setup_railway_does_not_overwrite_db_port_with_http_port():
    spec = create_spec_from_interview({
        "client_name": "Port Check Co",
        "industry": "Services",
        "domains_covered": ["sales"],
        "recommended_modules": ["sale_management"],
        "scoping_responses": [],
        "domain_responses": {},
    })

    builder = RailwayOdooBuilder(spec, "token-123")
    fake_railway = _FakeRailway()
    builder.railway = fake_railway

    task = BuildTask(
        task_id="setup-1",
        task_type=TaskType.DOCKER_SETUP,
        name="Railway Setup",
        description="",
    )

    ok = asyncio.run(builder._setup_railway(task))
    assert ok is True
    assert task.status == TaskStatus.COMPLETED

    odoo_vars = [vars_map for sid, vars_map in fake_railway.set_vars_calls if sid == "odoo-service-id"][0]
    assert "HOST" in odoo_vars
    assert "USER" in odoo_vars
    assert "PASSWORD" in odoo_vars
    assert "PORT" not in odoo_vars
    assert "PGPORT" not in odoo_vars
    assert fake_railway.start_command is not None
    assert "--db_port 5432" in fake_railway.start_command
