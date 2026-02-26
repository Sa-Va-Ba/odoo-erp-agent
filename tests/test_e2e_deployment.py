"""
End-to-end integration test: Interview → PRD → Deployment pipeline.

Covers the complete flow a real user goes through:
  1. Start an interview session
  2. Answer all questions (Scoping → Domain Expert → Summary phases)
  3. Receive a complete interview summary
  4. Generate a PRD (implementation spec) from the summary
  5. Submit the spec to the build/deploy API
  6. Verify build job starts and returns a valid, pollable status

No live server or Odoo instance required — uses Flask test client + mocks.

Run:
    pytest tests/test_e2e_deployment.py -v
    pytest tests/test_e2e_deployment.py -v -s    # also show print output
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import web_interview
from web_interview import app


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def use_tmp_output(monkeypatch):
    """Route interview file output to /tmp so tests don't write to ./outputs."""
    monkeypatch.setenv("VERCEL", "1")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    web_interview.agents.clear()
    with web_interview.builds_lock:
        web_interview.builds.clear()
    with app.test_client() as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Realistic canned responses (signal-rich, short, cycling)
# ─────────────────────────────────────────────────────────────────────────────

_ANSWERS = [
    # Scoping — company overview
    "We are a mid-size manufacturing company producing custom metal parts. About 80 employees across two factory sites.",
    # Scoping — pain points
    "Main pain points: inventory tracking across warehouses, production scheduling, manual purchase orders, and accounting is still in Excel.",
    # Scoping — order flow
    "B2B customers send RFQs, our sales team creates quotations. Once confirmed, manufacturing builds, warehouse ships, and we invoice on delivery.",
    # Scoping — team size
    "About 30 users: 5 sales, 3 accountants, 2 managers, 15 factory floor, 5 warehouse.",
    # Domain — Sales
    "We use a basic CRM for leads. Quotes are created manually in Word. Payment terms are net-30.",
    # Domain — Inventory
    "Two warehouses. We track stock in a spreadsheet. Monthly manual counts. FIFO costing. Raw material lead time is 2-4 weeks.",
    # Domain — Finance
    "Accounting in Excel. Multi-currency needed (USD and EUR). 21% VAT. Fiscal year ends December.",
    # Domain — Manufacturing
    "We use bills of materials for production orders. Work centres are manual presses and CNC machines.",
    # Domain — Purchase
    "3-4 regular suppliers. We issue purchase orders manually by email. Want automatic reordering.",
    # Domain — HR
    "We have 80 staff. Payroll is outsourced. We need basic leave management and org chart.",
    # Catch-all for any remaining questions
    "Yes, that applies to our situation.",
    "Not decided yet, we can configure this later during implementation.",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: drive the interview to completion
# ─────────────────────────────────────────────────────────────────────────────

def _complete_interview(client, session_id: str, max_questions: int = 50) -> dict:
    """
    Loop through questions, answering each with a canned response.
    Returns the summary dict when the interview reaches complete=True.
    Fails the test if it doesn't complete within max_questions.
    """
    for i in range(max_questions):
        resp = client.get(f"/api/question?session_id={session_id}")
        assert resp.status_code == 200, f"GET /api/question returned {resp.status_code}"
        data = resp.get_json()

        if data.get("complete"):
            assert "summary" in data, "complete=True but no summary in response"
            return data["summary"]

        answer = _ANSWERS[i % len(_ANSWERS)]
        post = client.post(
            "/api/respond",
            json={"session_id": session_id, "response": answer, "question": data},
            content_type="application/json",
        )
        assert post.status_code == 200, f"POST /api/respond returned {post.status_code}"

    pytest.fail(f"Interview did not complete within {max_questions} questions")


def _start(client, name="TestCorp", industry="Manufacturing") -> str:
    resp = client.post(
        "/api/start",
        json={"client_name": name, "industry": industry},
        content_type="application/json",
    )
    assert resp.status_code == 200
    return resp.get_json()["session_id"]


def _full_summary(client, name="MetalWorks", industry="Manufacturing") -> dict:
    return _complete_interview(client, _start(client, name, industry))


def _full_prd(client, name="MetalWorks", industry="Manufacturing") -> dict:
    summary = _full_summary(client, name, industry)
    resp = client.post(
        "/api/generate-prd",
        json={"summary": summary},
        content_type="application/json",
    )
    assert resp.status_code == 200
    return resp.get_json()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Session management
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionManagement:
    def test_start_creates_session_id(self, client):
        resp = client.post(
            "/api/start",
            json={"client_name": "AcmeCorp", "industry": "Manufacturing"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0
        assert data["client_name"] == "AcmeCorp"

    def test_first_question_has_expected_shape(self, client):
        sid = _start(client)
        q = client.get(f"/api/question?session_id={sid}").get_json()
        assert q["complete"] is False
        assert isinstance(q["question"], str) and len(q["question"]) > 5
        assert "phase" in q
        assert "progress" in q

    def test_invalid_session_returns_400(self, client):
        assert client.get("/api/question?session_id=fake-xyz").status_code == 400

    def test_respond_with_invalid_session_returns_400(self, client):
        resp = client.post(
            "/api/respond",
            json={"session_id": "bad", "response": "hello", "question": {}},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_skip_question_returns_skipped_true(self, client):
        sid = _start(client, "SkipCo")
        q = client.get(f"/api/question?session_id={sid}").get_json()
        assert not q["complete"]
        skip = client.post(
            "/api/skip",
            json={"session_id": sid, "question": q},
            content_type="application/json",
        )
        assert skip.status_code == 200
        assert skip.get_json()["skipped"] is True

    def test_early_end_returns_summary(self, client):
        sid = _start(client, "EarlyCo", "Services")
        q = client.get(f"/api/question?session_id={sid}").get_json()
        if not q["complete"]:
            client.post(
                "/api/respond",
                json={"session_id": sid, "response": "We are a small IT consultancy.", "question": q},
                content_type="application/json",
            )
        end = client.post("/api/end", json={"session_id": sid}, content_type="application/json")
        assert end.status_code == 200
        assert "summary" in end.get_json()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Interview completion
# ─────────────────────────────────────────────────────────────────────────────

class TestInterviewCompletion:
    def test_interview_runs_to_completion(self, client):
        summary = _full_summary(client)
        assert summary is not None

    def test_summary_contains_required_fields(self, client):
        summary = _full_summary(client)
        for field in ["client_name", "industry", "recommended_modules", "domains_covered"]:
            assert field in summary, f"Summary missing field: '{field}'"

    def test_summary_client_name_matches_input(self, client):
        summary = _full_summary(client, name="PrecisionParts Ltd")
        assert summary["client_name"] == "PrecisionParts Ltd"

    def test_manufacturing_interview_recommends_relevant_modules(self, client):
        summary = _full_summary(client, industry="Manufacturing")
        modules = summary.get("recommended_modules", [])
        assert len(modules) > 0, "No modules recommended for a manufacturing company"

    def test_progress_increments_across_questions(self, client):
        sid = _start(client)
        percentages = []
        for i in range(5):
            q = client.get(f"/api/question?session_id={sid}").get_json()
            if q.get("complete"):
                break
            prog = q.get("progress", {})
            if "percentage" in prog:
                percentages.append(prog["percentage"])
            client.post(
                "/api/respond",
                json={"session_id": sid, "response": _ANSWERS[i], "question": q},
                content_type="application/json",
            )
        # Progress should generally move forward (or at least not go backwards significantly)
        if len(percentages) >= 2:
            assert percentages[-1] >= percentages[0], "Progress percentage went backwards"


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRD generation
# ─────────────────────────────────────────────────────────────────────────────

class TestPRDGeneration:
    def test_generate_prd_returns_200(self, client):
        summary = _full_summary(client)
        resp = client.post("/api/generate-prd", json={"summary": summary}, content_type="application/json")
        assert resp.status_code == 200

    def test_prd_has_all_output_fields(self, client):
        prd = _full_prd(client)
        for field in ["markdown", "json", "company_name", "module_count", "estimated_minutes"]:
            assert field in prd, f"PRD missing field: '{field}'"

    def test_prd_company_name_correct(self, client):
        prd = _full_prd(client, name="MetalWorks")
        assert prd["company_name"] == "MetalWorks"

    def test_prd_includes_multiple_modules(self, client):
        prd = _full_prd(client)
        assert prd["module_count"] >= 2, f"Expected ≥2 modules, got {prd['module_count']}"

    def test_prd_estimated_time_positive(self, client):
        prd = _full_prd(client)
        assert prd["estimated_minutes"] > 0

    def test_prd_markdown_non_empty(self, client):
        prd = _full_prd(client)
        assert len(prd["markdown"]) > 100, "PRD markdown output is suspiciously short"

    def test_prd_always_includes_accounting_module(self, client):
        """Accounting is always required — every Odoo install needs it."""
        prd = _full_prd(client)
        module_names = {m["module_name"] for m in prd["json"]["modules"]}
        assert "account" in module_names, f"Expected 'account' module in {module_names}"

    def test_generate_prd_without_summary_returns_400(self, client):
        resp = client.post("/api/generate-prd", json={}, content_type="application/json")
        assert resp.status_code == 400

    def test_prd_spec_json_has_builder_required_keys(self, client):
        spec = _full_prd(client)["json"]
        for key in ["spec_id", "company", "modules", "user_roles", "estimated_setup_minutes"]:
            assert key in spec, f"Spec JSON missing builder-required key: '{key}'"

    def test_prd_modules_have_required_fields(self, client):
        spec = _full_prd(client)["json"]
        for mod in spec["modules"]:
            assert "module_name" in mod
            assert "install" in mod
            assert mod["install"] is True
            assert mod.get("priority") in ("critical", "high", "medium", "low"), (
                f"Invalid priority '{mod.get('priority')}' for module '{mod['module_name']}'"
            )

    def test_demo_result_available_after_prd(self, client):
        _full_prd(client)
        demo = client.get("/api/demo-result").get_json()
        assert demo["available"] is True
        assert "prd" in demo


# ─────────────────────────────────────────────────────────────────────────────
# 4. Build / deployment
# ─────────────────────────────────────────────────────────────────────────────

class TestDeploymentPipeline:
    def _spec(self, client, industry="Manufacturing"):
        return _full_prd(client, industry=industry)["json"]

    def test_build_start_accepts_interview_spec(self, client):
        spec = self._spec(client)
        with patch("web_interview.threading.Thread") as t:
            t.return_value.start = MagicMock()
            resp = client.post(
                "/api/build/start",
                json={"spec": spec},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "build_id" in data
        assert data["build_id"].startswith("build-")

    def test_build_status_returns_valid_state(self, client):
        spec = self._spec(client)
        with patch("web_interview.threading.Thread") as t:
            t.return_value.start = MagicMock()
            build_id = client.post(
                "/api/build/start",
                json={"spec": spec},
                content_type="application/json",
            ).get_json()["build_id"]

        status = client.get(f"/api/build/status?build_id={build_id}").get_json()
        assert status["build_id"] == build_id
        assert "tasks" in status
        assert "overall_progress" in status
        assert isinstance(status["overall_progress"], (int, float))
        assert 0 <= status["overall_progress"] <= 100

    def test_build_stop_acknowledged(self, client):
        spec = self._spec(client)
        with patch("web_interview.threading.Thread") as t, patch("subprocess.run"):
            t.return_value.start = MagicMock()
            build_id = client.post(
                "/api/build/start",
                json={"spec": spec},
                content_type="application/json",
            ).get_json()["build_id"]

            stop = client.post(
                "/api/build/stop",
                json={"build_id": build_id},
                content_type="application/json",
            )
        assert stop.status_code == 200
        assert stop.get_json()["stopped"] is True

    def test_build_status_unknown_id_returns_404(self, client):
        assert client.get("/api/build/status?build_id=nonexistent-999").status_code == 404

    def test_build_status_missing_param_returns_400(self, client):
        assert client.get("/api/build/status").status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full end-to-end (single chain test across all stages)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullE2EPipeline:
    @pytest.mark.parametrize("industry", ["Manufacturing", "E-commerce", "Professional Services"])
    def test_full_pipeline(self, client, industry):
        """
        Complete pipeline for three industry types:
          session → answer all questions → summary → PRD → build job
        """
        # 1. Start session
        sid = _start(client, name=f"{industry} Co", industry=industry)

        # 2. Complete interview
        summary = _complete_interview(client, sid)
        assert "recommended_modules" in summary, f"[{industry}] No recommended_modules in summary"

        # 3. Generate PRD
        prd_resp = client.post(
            "/api/generate-prd",
            json={"summary": summary},
            content_type="application/json",
        )
        assert prd_resp.status_code == 200, f"[{industry}] PRD generation failed"
        prd = prd_resp.get_json()
        assert prd["module_count"] >= 1, f"[{industry}] PRD has no modules"

        # 4. Validate spec is builder-compatible
        spec = prd["json"]
        assert "account" in {m["module_name"] for m in spec["modules"]}, (
            f"[{industry}] Accounting module missing from spec"
        )

        # 5. Submit to build
        with patch("web_interview.threading.Thread") as t:
            t.return_value.start = MagicMock()
            build_resp = client.post(
                "/api/build/start",
                json={"spec": spec},
                content_type="application/json",
            )
        assert build_resp.status_code == 200, f"[{industry}] Build start failed"
        build_id = build_resp.get_json()["build_id"]

        # 6. Poll status
        status = client.get(f"/api/build/status?build_id={build_id}").get_json()
        assert status["build_id"] == build_id
        assert 0 <= status["overall_progress"] <= 100
