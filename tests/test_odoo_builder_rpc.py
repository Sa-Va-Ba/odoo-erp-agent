"""
Tests for OdooBuilder XML-RPC configuration methods.

All RPC calls are mocked — no live Odoo instance needed.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import asyncio

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.builders.odoo_builder import OdooBuilder, TaskStatus, TaskType, BuildTask
from src.schemas.implementation_spec import (
    ImplementationSpec,
    CompanySetup,
    ModuleConfig,
    UserRole,
    ConfigPriority,
)


def _make_spec(**overrides):
    """Create a minimal ImplementationSpec for testing."""
    defaults = dict(
        spec_id="test-spec-001",
        created_at="2026-01-01T00:00:00",
        interview_session_id="test-session",
        company=CompanySetup(
            name="Test Corp",
            industry="Technology",
            country="US",
            currency="USD",
            timezone="America/New_York",
        ),
        modules=[
            ModuleConfig(
                module_name="sale_management",
                display_name="Sales",
                settings={"group_sale_pricelist": True, "group_discount_per_so_line": True},
                depends_on=[],
            ),
        ],
        user_roles=[
            UserRole(
                name="Sales Manager",
                description="Manages sales team",
                groups=["sale.group_sale_manager"],
                count=1,
            ),
        ],
    )
    defaults.update(overrides)
    return ImplementationSpec(**defaults)


def _make_task(task_type, module_name=None):
    return BuildTask(
        task_id="test-task",
        task_type=task_type,
        name="Test Task",
        description="test",
        module_name=module_name,
    )


def _run(coro):
    """Helper to run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def mock_rpc():
    rpc = MagicMock()
    rpc.uid = 2
    rpc._execute = MagicMock()
    return rpc


# ── _sanitize_login ──


class TestSanitizeLogin:
    def test_basic_name(self):
        assert OdooBuilder._sanitize_login("Sales Manager") == "sales_manager"

    def test_unicode_name(self):
        result = OdooBuilder._sanitize_login("Département Manager")
        # é decomposes to e in NFKD normalization
        assert result == "departement_manager"

    def test_special_chars(self):
        assert OdooBuilder._sanitize_login("HR & Payroll/Admin") == "hr_payroll_admin"

    def test_empty_fallback(self):
        assert OdooBuilder._sanitize_login("") == "user"

    def test_all_special_chars_fallback(self):
        assert OdooBuilder._sanitize_login("!!!") == "user"


# ── _connect_rpc ──


class TestConnectRpc:
    def test_caches_rpc_connection(self):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        mock_rpc_instance = MagicMock()
        builder._rpc = mock_rpc_instance
        result = builder._connect_rpc()
        assert result is mock_rpc_instance

    def test_connect_rpc_failure_raises(self):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch("src.swarm.apply.OdooRPC") as MockRPC:
            mock_instance = MockRPC.return_value
            mock_instance.login.side_effect = ConnectionRefusedError("refused")

            with pytest.raises(ConnectionRefusedError):
                builder._connect_rpc(max_retries=2, retry_delay=0)


# ── _configure_module ──


class TestConfigureModule:
    def test_applies_settings_via_rpc(self, mock_rpc):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", return_value=mock_rpc):
            mock_rpc._execute.side_effect = [42, True]  # create returns id, set_values returns True

            task = _make_task(TaskType.MODULE_CONFIG, module_name="sale_management")
            result = _run(builder._configure_module(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED

        calls = mock_rpc._execute.call_args_list
        # First call: create settings
        assert calls[0][0][0] == "res.config.settings"
        assert calls[0][0][1] == "create"
        # Second call: set_values (not "execute")
        assert calls[1][0][0] == "res.config.settings"
        assert calls[1][0][1] == "set_values"
        assert calls[1][0][2] == [[42]]

    def test_skips_when_no_settings(self, mock_rpc):
        spec = _make_spec(
            modules=[
                ModuleConfig(
                    module_name="crm",
                    display_name="CRM",
                    settings={},
                    depends_on=[],
                ),
            ]
        )
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        task = _make_task(TaskType.MODULE_CONFIG, module_name="crm")
        result = _run(builder._configure_module(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED
        # RPC should NOT have been called
        mock_rpc._execute.assert_not_called()

    def test_continues_on_rpc_error(self, mock_rpc):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", return_value=mock_rpc):
            mock_rpc._execute.side_effect = Exception("XML-RPC fault: field not found")

            task = _make_task(TaskType.MODULE_CONFIG, module_name="sale_management")
            result = _run(builder._configure_module(task))

        # Non-fatal: still COMPLETED, not FAILED
        assert result is True
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 100


# ── _setup_users ──


class TestSetupUsers:
    def test_creates_with_resolved_groups(self, mock_rpc):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", return_value=mock_rpc):
            # ir.model.data search → [10], read → [{"res_id": 55}], res.users create → 100
            mock_rpc._execute.side_effect = [
                [10],                      # ir.model.data search
                [{"res_id": 55}],          # ir.model.data read
                100,                       # res.users create
            ]

            task = _make_task(TaskType.USER_SETUP)
            result = _run(builder._setup_users(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED

        calls = mock_rpc._execute.call_args_list
        # Verify ir.model.data search was called
        assert calls[0][0][0] == "ir.model.data"
        assert calls[0][0][1] == "search"
        # Verify user was created with correct groups (using (4, gid) link format)
        create_call = calls[2]
        assert create_call[0][0] == "res.users"
        assert create_call[0][1] == "create"
        user_vals = create_call[0][2][0]
        assert user_vals["groups_id"] == [(4, 55)]
        assert user_vals["password"] == "changeme123!"
        # Login should be sanitized
        assert "test_corp" in user_vals["login"] or "testcorp" in user_vals["login"]
        assert ".local" in user_vals["login"]

    def test_handles_duplicate_login(self, mock_rpc):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", return_value=mock_rpc):
            mock_rpc._execute.side_effect = [
                [10],                      # ir.model.data search
                [{"res_id": 55}],          # ir.model.data read
                Exception("unique constraint: login already exists"),
            ]

            task = _make_task(TaskType.USER_SETUP)
            result = _run(builder._setup_users(task))

        # Should still succeed (graceful skip)
        assert result is True
        assert task.status == TaskStatus.COMPLETED

    def test_empty_user_roles(self, mock_rpc):
        spec = _make_spec(user_roles=[])
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        task = _make_task(TaskType.USER_SETUP)
        result = _run(builder._setup_users(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED
        mock_rpc._execute.assert_not_called()

    def test_connect_rpc_failure_still_completes(self):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", side_effect=ConnectionRefusedError("refused")):
            task = _make_task(TaskType.USER_SETUP)
            result = _run(builder._setup_users(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED


# ── _final_config ──


class TestFinalConfig:
    def test_writes_company(self, mock_rpc):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch.object(builder, "_connect_rpc", return_value=mock_rpc):
            mock_rpc._execute.side_effect = [
                [1],   # res.currency search → USD id
                True,  # res.currency write (activate)
                [5],   # res.country search → US id
                True,  # res.company write
                True,  # res.users write (timezone)
            ]

            task = _make_task(TaskType.FINAL_CONFIG)
            result = _run(builder._final_config(task))

        assert result is True
        assert task.status == TaskStatus.COMPLETED

        calls = mock_rpc._execute.call_args_list
        # Currency search (with active_test: False)
        assert calls[0][0][0] == "res.currency"
        assert calls[0][0][1] == "search"
        # Currency activation
        assert calls[1][0][0] == "res.currency"
        assert calls[1][0][1] == "write"
        # Country lookup
        assert calls[2][0][0] == "res.country"
        # Company write
        assert calls[3][0][0] == "res.company"
        assert calls[3][0][1] == "write"
        company_vals = calls[3][0][2][1]
        assert company_vals["name"] == "Test Corp"
        assert company_vals["currency_id"] == 1
        assert company_vals["country_id"] == 5
        # Timezone write
        assert calls[4][0][0] == "res.users"
        assert calls[4][0][2][1] == {"tz": "America/New_York"}


# ── stop() ──


class TestStop:
    def test_stop_sets_event_and_status(self):
        spec = _make_spec()
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        with patch("subprocess.run"):
            builder.stop()

        assert builder._stop_event.is_set()
        assert builder.state.status == TaskStatus.FAILED
        assert builder.state.completed_at is not None

    def test_build_loop_respects_stop_event(self):
        spec = _make_spec(modules=[], user_roles=[])
        builder = OdooBuilder(spec, work_dir="/tmp/test-odoo-build")

        # Set stop before build starts
        builder._stop_event.set()

        result = _run(builder.build())

        assert result.status == TaskStatus.FAILED
