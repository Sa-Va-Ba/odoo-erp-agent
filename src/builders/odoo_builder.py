"""
Odoo Builder Agent

Orchestrates the complete Odoo setup:
1. Docker environment setup
2. Module installation
3. Configuration
4. Status tracking

This is the main coordinator that delegates to specialized sub-agents.
"""

import asyncio
import json
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Callable
import threading
import uuid


class TaskStatus(Enum):
    """Status of a build task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskType(Enum):
    """Types of build tasks."""
    DOCKER_SETUP = "docker_setup"
    DATABASE_INIT = "database_init"
    MODULE_INSTALL = "module_install"
    MODULE_CONFIG = "module_config"
    DATA_IMPORT = "data_import"
    USER_SETUP = "user_setup"
    FINAL_CONFIG = "final_config"


@dataclass
class BuildTask:
    """A single build task."""
    task_id: str
    task_type: TaskType
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    logs: list[str] = field(default_factory=list)

    # For module tasks
    module_name: Optional[str] = None

    def to_dict(self) -> dict:
        ct = self.get_current_task()
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "progress": self.progress,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "logs": self.logs[-10:],  # Last 10 log entries
            "module_name": self.module_name,
        }


@dataclass
class BuildState:
    """Overall build state."""
    build_id: str
    spec_id: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    tasks: list[BuildTask] = field(default_factory=list)

    # Odoo connection info
    odoo_url: Optional[str] = None
    odoo_port: int = 8069
    db_name: str = "odoo"
    admin_password: str = "admin"

    # Deploy target
    deploy_target: str = "docker"

    # Docker info
    container_id: Optional[str] = None
    db_container_id: Optional[str] = None

    def get_current_task(self) -> Optional[BuildTask]:
        """Get the currently running task."""
        for task in self.tasks:
            if task.status == TaskStatus.IN_PROGRESS:
                return task
        return None

    def get_overall_progress(self) -> int:
        """Get overall build progress (0-100)."""
        if not self.tasks:
            return 0
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        return int((completed / len(self.tasks)) * 100)

    def to_dict(self) -> dict:
        ct = self.get_current_task()
        return {
            "build_id": self.build_id,
            "spec_id": self.spec_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "overall_progress": self.get_overall_progress(),
            "current_task": ct.to_dict() if ct else None,
            "tasks": [t.to_dict() for t in self.tasks],
            "odoo_url": self.odoo_url,
            "odoo_port": self.odoo_port,
            "db_name": self.db_name,
            "deploy_target": self.deploy_target,
        }


class OdooBuilder:
    """
    Main Odoo builder that coordinates the entire setup process.

    Usage:
        builder = OdooBuilder(implementation_spec)
        builder.on_progress = my_callback  # Optional progress callback
        await builder.build()
    """

    def __init__(
        self,
        spec: "ImplementationSpec",
        work_dir: str = "./odoo-instance",
        odoo_version: str = "17.0",
    ):
        from ..schemas.implementation_spec import ImplementationSpec
        self.spec = spec
        self.work_dir = Path(work_dir)
        self.odoo_version = odoo_version

        self.state = BuildState(
            build_id=f"build-{uuid.uuid4().hex[:8]}",
            spec_id=spec.spec_id,
        )

        # Callback for progress updates
        self.on_progress: Optional[Callable[[BuildState], None]] = None

        # Stop event for graceful cancellation
        self._stop_event = threading.Event()

        # Cached RPC connection
        self._rpc = None

        # Create work directory
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, task: BuildTask, message: str):
        """Add log message to task."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        task.logs.append(f"[{timestamp}] {message}")
        print(f"[{task.name}] {message}")
        self._notify_progress()

    def _notify_progress(self):
        """Notify progress callback if set."""
        if self.on_progress:
            self.on_progress(self.state)

    def _create_tasks(self) -> list[BuildTask]:
        """Create all tasks for the build."""
        tasks = []

        # 1. Docker setup
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.DOCKER_SETUP,
            name="Docker Environment",
            description="Set up Docker containers for Odoo and PostgreSQL",
        ))

        # 2. Database initialization
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.DATABASE_INIT,
            name="Database Setup",
            description="Initialize Odoo database",
        ))

        # 3. Module installations (in dependency order)
        ordered_modules = self.spec.get_install_order()
        for module in ordered_modules:
            tasks.append(BuildTask(
                task_id=f"task-{uuid.uuid4().hex[:6]}",
                task_type=TaskType.MODULE_INSTALL,
                name=f"Install {module.display_name}",
                description=f"Installing {module.module_name} module",
                module_name=module.module_name,
            ))

        # 4. Module configurations
        for module in ordered_modules:
            if module.settings:
                tasks.append(BuildTask(
                    task_id=f"task-{uuid.uuid4().hex[:6]}",
                    task_type=TaskType.MODULE_CONFIG,
                    name=f"Configure {module.display_name}",
                    description=f"Applying settings for {module.module_name}",
                    module_name=module.module_name,
                ))

        # 5. User setup
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.USER_SETUP,
            name="User Roles",
            description="Creating user roles and permissions",
        ))

        # 6. Final configuration
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.FINAL_CONFIG,
            name="Final Setup",
            description="Company settings and final configuration",
        ))

        return tasks

    def _generate_docker_compose(self) -> str:
        """Generate docker-compose.yml content."""
        company_name_safe = self.spec.company.name.lower().replace(" ", "-").replace("_", "-")[:20]

        return f"""version: '3.8'
services:
  odoo:
    image: odoo:{self.odoo_version}
    container_name: odoo-{company_name_safe}
    depends_on:
      - db
    ports:
      - "{self.state.odoo_port}:8069"
    volumes:
      - odoo-data:/var/lib/odoo
      - ./addons:/mnt/extra-addons
      - ./config:/etc/odoo
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=odoo
    restart: unless-stopped

  db:
    image: postgres:15
    container_name: postgres-{company_name_safe}
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_USER=odoo
      - POSTGRES_PASSWORD=odoo
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - postgres-data:/var/lib/postgresql/data/pgdata
    restart: unless-stopped

volumes:
  odoo-data:
  postgres-data:
"""

    def _generate_odoo_config(self) -> str:
        """Generate odoo.conf content."""
        return f"""[options]
addons_path = /mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons
data_dir = /var/lib/odoo
admin_passwd = {self.state.admin_password}
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
db_name = {self.state.db_name}
list_db = True
"""

    async def _run_command(self, cmd: list[str], task: BuildTask, cwd: Optional[Path] = None) -> tuple[bool, str]:
        """Run a shell command and return success status and output."""
        try:
            self._log(task, f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=cwd or self.work_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            if result.returncode != 0:
                self._log(task, f"Error: {result.stderr}")
                return False, result.stderr
            return True, result.stdout
        except subprocess.TimeoutExpired:
            self._log(task, "Command timed out")
            return False, "Command timed out"
        except Exception as e:
            self._log(task, f"Exception: {str(e)}")
            return False, str(e)

    async def _setup_docker(self, task: BuildTask) -> bool:
        """Set up Docker environment."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 0
        self._notify_progress()

        # Create directories
        self._log(task, "Creating directory structure...")
        (self.work_dir / "addons").mkdir(exist_ok=True)
        (self.work_dir / "config").mkdir(exist_ok=True)
        task.progress = 20
        self._notify_progress()

        # Write docker-compose.yml
        self._log(task, "Generating docker-compose.yml...")
        compose_path = self.work_dir / "docker-compose.yml"
        compose_path.write_text(self._generate_docker_compose())
        task.progress = 40
        self._notify_progress()

        # Write odoo.conf
        self._log(task, "Generating odoo.conf...")
        config_path = self.work_dir / "config" / "odoo.conf"
        config_path.write_text(self._generate_odoo_config())
        task.progress = 60
        self._notify_progress()

        # Check if Docker is available
        self._log(task, "Checking Docker availability...")
        success, output = await self._run_command(["docker", "--version"], task)
        if not success:
            task.error_message = "Docker is not installed. Please install Docker Desktop from https://docker.com/products/docker-desktop"
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now().isoformat()
            self._log(task, "❌ Docker is required but not installed!")
            self._log(task, "Please install Docker Desktop: https://docker.com/products/docker-desktop")
            self._notify_progress()
            return False
        self._log(task, f"✓ Docker found: {output.strip()}")
        task.progress = 70
        self._notify_progress()

        # Pull images
        self._log(task, f"Pulling Odoo {self.odoo_version} image...")
        success, _ = await self._run_command(
            ["docker", "compose", "pull"],
            task,
            cwd=self.work_dir
        )
        task.progress = 90
        self._notify_progress()

        # Start containers
        self._log(task, "Starting containers...")
        success, output = await self._run_command(
            ["docker", "compose", "up", "-d"],
            task,
            cwd=self.work_dir
        )

        if success:
            self.state.odoo_url = f"http://localhost:{self.state.odoo_port}"
            task.progress = 100
            task.status = TaskStatus.COMPLETED
            self._log(task, f"Docker setup complete! Odoo will be at {self.state.odoo_url}")
        else:
            task.status = TaskStatus.FAILED
            task.error_message = output

        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return success

    async def _init_database(self, task: BuildTask) -> bool:
        """Initialize Odoo database."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        self._notify_progress()

        # Wait for Odoo to be ready
        self._log(task, "Waiting for Odoo to start...")
        max_retries = 30
        for i in range(max_retries):
            task.progress = int((i / max_retries) * 50)
            self._notify_progress()

            try:
                import urllib.request
                req = urllib.request.Request(f"http://localhost:{self.state.odoo_port}/web/database/selector")
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        self._log(task, "Odoo is ready!")
                        break
            except Exception:
                pass

            await asyncio.sleep(2)
        else:
            task.status = TaskStatus.FAILED
            task.error_message = "Odoo did not start in time"
            task.completed_at = datetime.now().isoformat()
            self._notify_progress()
            return False

        task.progress = 60
        self._notify_progress()

        # Create database via CLI
        self._log(task, f"Creating database '{self.state.db_name}'...")

        # Use docker exec to create database
        cmd = [
            "docker", "compose", "exec", "-T", "odoo",
            "odoo", "--database", self.state.db_name,
            "--init", "base",
            "--stop-after-init",
            "--without-demo=all"
        ]
        success, output = await self._run_command(cmd, task, cwd=self.work_dir)

        if success:
            task.progress = 100
            task.status = TaskStatus.COMPLETED
            self._log(task, "Database initialized successfully!")
        else:
            # Database might already exist, which is okay
            if "already exists" in output.lower():
                task.progress = 100
                task.status = TaskStatus.COMPLETED
                self._log(task, "Database already exists, continuing...")
            else:
                task.status = TaskStatus.FAILED
                task.error_message = output

        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return task.status == TaskStatus.COMPLETED

    async def _install_module(self, task: BuildTask) -> bool:
        """Install a single Odoo module."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        self._notify_progress()

        module_name = task.module_name
        self._log(task, f"Installing module: {module_name}")
        task.progress = 20
        self._notify_progress()

        # Install via docker exec
        cmd = [
            "docker", "compose", "exec", "-T", "odoo",
            "odoo", "--database", self.state.db_name,
            "--init", module_name,
            "--stop-after-init"
        ]

        task.progress = 50
        self._notify_progress()

        success, output = await self._run_command(cmd, task, cwd=self.work_dir)

        if success or "already installed" in output.lower():
            task.progress = 100
            task.status = TaskStatus.COMPLETED
            self._log(task, f"Module {module_name} installed successfully!")
        else:
            task.status = TaskStatus.FAILED
            task.error_message = output
            self._log(task, f"Failed to install {module_name}")

        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return task.status == TaskStatus.COMPLETED

    @staticmethod
    def _sanitize_login(name: str) -> str:
        """Sanitize a name for use as a login identifier."""
        nfkd = unicodedata.normalize("NFKD", name)
        ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
        sanitized = re.sub(r"[^a-z0-9]", "_", ascii_name.lower())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return sanitized or "user"

    def _connect_rpc(self, max_retries=10, retry_delay=3):
        """Create an authenticated XML-RPC connection with retry and caching."""
        if self._rpc is not None:
            return self._rpc

        from ..swarm.apply import OdooRPC, RPCConfig

        config = RPCConfig(
            url=f"http://localhost:{self.state.odoo_port}",
            database=self.state.db_name,
            username="admin",
            password=self.state.admin_password,
            odoo_version=self.odoo_version,
        )
        rpc = OdooRPC(config)

        for attempt in range(max_retries):
            try:
                rpc.login()
                self._rpc = rpc
                return rpc
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(retry_delay)

        raise RuntimeError("Could not connect to Odoo via RPC")

    async def _configure_module(self, task: BuildTask) -> bool:
        """Configure a module's settings via XML-RPC."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 10
        self._notify_progress()

        self._log(task, f"Configuring {task.module_name}...")

        # Find matching module config from spec
        module_cfg = None
        for m in self.spec.modules:
            if m.module_name == task.module_name:
                module_cfg = m
                break

        if not module_cfg or not module_cfg.settings:
            self._log(task, "No settings to apply, skipping")
            task.progress = 100
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            self._notify_progress()
            return True

        task.progress = 30
        self._notify_progress()

        try:
            rpc = self._connect_rpc()
            task.progress = 50
            self._notify_progress()

            self._log(task, f"Applying settings: {list(module_cfg.settings.keys())}")
            config_id = rpc._execute("res.config.settings", "create", [module_cfg.settings])
            task.progress = 70
            self._notify_progress()

            rpc._execute("res.config.settings", "set_values", [[config_id]])
            task.progress = 100
            self._log(task, "Settings applied successfully")
        except Exception as e:
            self._log(task, f"Warning: settings apply failed ({e}), continuing anyway")
            task.progress = 100

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return True

    async def _setup_users(self, task: BuildTask) -> bool:
        """Set up user roles via XML-RPC."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 10
        self._notify_progress()

        self._log(task, "Setting up user roles...")

        if not self.spec.user_roles:
            self._log(task, "No user roles defined, skipping")
            task.progress = 100
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now().isoformat()
            self._notify_progress()
            return True

        try:
            rpc = self._connect_rpc()
            task.progress = 20
            self._notify_progress()

            company_slug = self._sanitize_login(self.spec.company.name)[:20]
            total_roles = len(self.spec.user_roles)

            for i, role in enumerate(self.spec.user_roles):
                role_progress = 20 + int((i / total_roles) * 70)
                task.progress = role_progress
                self._notify_progress()

                # Resolve XML IDs to group database IDs
                group_ids = []
                for xml_id in role.groups:
                    parts = xml_id.split(".")
                    if len(parts) != 2:
                        self._log(task, f"  Skipping invalid XML ID: {xml_id}")
                        continue
                    module_part, name_part = parts
                    try:
                        data_ids = rpc._execute(
                            "ir.model.data", "search",
                            [[("module", "=", module_part), ("name", "=", name_part)]],
                        )
                        if data_ids:
                            data_records = rpc._execute(
                                "ir.model.data", "read", [data_ids], fields=["res_id"],
                            )
                            if data_records:
                                rec = data_records[0] if isinstance(data_records, list) else data_records
                                group_ids.append(rec["res_id"])
                    except Exception as e:
                        self._log(task, f"  Warning: could not resolve {xml_id}: {e}")

                self._log(task, f"  {role.name}: creating {role.count} user(s) with {len(group_ids)} groups")

                for n in range(role.count):
                    login_name = self._sanitize_login(role.name)
                    suffix = f"_{n+1}" if role.count > 1 else ""
                    login = f"{login_name}{suffix}@{company_slug}.local"
                    try:
                        user_vals = {
                            "name": f"{role.name}{suffix}",
                            "login": login,
                            "password": "changeme123!",
                        }
                        if group_ids:
                            user_vals["groups_id"] = [(4, gid) for gid in group_ids]
                        rpc._execute("res.users", "create", [user_vals])
                        self._log(task, f"    Created user: {login}")
                    except Exception as e:
                        if "already exists" in str(e).lower() or "unique" in str(e).lower():
                            self._log(task, f"    User {login} already exists, skipping")
                        else:
                            self._log(task, f"    Warning: failed to create {login}: {e}")

        except Exception as e:
            self._log(task, f"Warning: user setup encountered errors ({e})")

        task.progress = 100
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._log(task, "User roles configured")
        self._notify_progress()
        return True

    async def _final_config(self, task: BuildTask) -> bool:
        """Apply final company configuration via XML-RPC."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 10
        self._notify_progress()

        self._log(task, f"Setting company name to: {self.spec.company.name}")
        self._log(task, f"Industry: {self.spec.company.industry}")

        try:
            rpc = self._connect_rpc()
            task.progress = 30
            self._notify_progress()

            company_vals = {"name": self.spec.company.name}

            # Look up currency (include inactive — most are inactive by default)
            if self.spec.company.currency:
                self._log(task, f"Setting currency: {self.spec.company.currency}")
                currency_ids = rpc._execute(
                    "res.currency", "search",
                    [[("name", "=", self.spec.company.currency)]],
                    context={"active_test": False},
                )
                if currency_ids:
                    rpc._execute("res.currency", "write", [[currency_ids[0]], {"active": True}])
                    company_vals["currency_id"] = currency_ids[0]
            task.progress = 50
            self._notify_progress()

            # Look up country
            if self.spec.company.country:
                self._log(task, f"Setting country: {self.spec.company.country}")
                country_ids = rpc._execute(
                    "res.country", "search",
                    [[("code", "=", self.spec.company.country)]],
                )
                if country_ids:
                    company_vals["country_id"] = country_ids[0]
            task.progress = 70
            self._notify_progress()

            # Write company record (id=1 is the default company)
            rpc._execute("res.company", "write", [[1], company_vals])
            self._log(task, "Company settings applied")

            # Set admin user timezone
            if self.spec.company.timezone:
                self._log(task, f"Setting admin timezone: {self.spec.company.timezone}")
                rpc._execute("res.users", "write", [[rpc.uid], {"tz": self.spec.company.timezone}])

            task.progress = 100
            self._log(task, "Final configuration complete!")

        except Exception as e:
            self._log(task, f"Warning: final config encountered errors ({e})")
            task.progress = 100

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return True

    async def build(self) -> BuildState:
        """
        Execute the complete build process.

        Returns the final build state.
        """
        self.state.status = TaskStatus.IN_PROGRESS
        self.state.started_at = datetime.now().isoformat()
        self.state.tasks = self._create_tasks()
        self._notify_progress()

        # Execute each task in order
        for task in self.state.tasks:
            if self._stop_event.is_set():
                self.state.status = TaskStatus.FAILED
                break

            success = False

            if task.task_type == TaskType.DOCKER_SETUP:
                success = await self._setup_docker(task)
            elif task.task_type == TaskType.DATABASE_INIT:
                success = await self._init_database(task)
            elif task.task_type == TaskType.MODULE_INSTALL:
                success = await self._install_module(task)
            elif task.task_type == TaskType.MODULE_CONFIG:
                success = await self._configure_module(task)
            elif task.task_type == TaskType.USER_SETUP:
                success = await self._setup_users(task)
            elif task.task_type == TaskType.FINAL_CONFIG:
                success = await self._final_config(task)

            if not success and task.task_type in [TaskType.DOCKER_SETUP, TaskType.DATABASE_INIT]:
                # Critical tasks - stop on failure
                self.state.status = TaskStatus.FAILED
                break

        # Set final state
        if self.state.status != TaskStatus.FAILED:
            self.state.status = TaskStatus.COMPLETED

        self.state.completed_at = datetime.now().isoformat()
        self._notify_progress()

        return self.state

    def get_state(self) -> BuildState:
        """Get current build state."""
        return self.state

    def stop(self):
        """Stop the build and clean up."""
        self._stop_event.set()
        self.state.status = TaskStatus.FAILED
        self.state.completed_at = datetime.now().isoformat()
        self._rpc = None
        # Stop Docker containers
        subprocess.run(
            ["docker", "compose", "down"],
            cwd=self.work_dir,
            capture_output=True
        )


# Convenience function to run build
async def run_build(spec: "ImplementationSpec", work_dir: str = "./odoo-instance") -> BuildState:
    """Run a complete build from specification."""
    builder = OdooBuilder(spec, work_dir)
    return await builder.build()
