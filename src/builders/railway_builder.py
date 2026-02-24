from __future__ import annotations

"""
Railway Cloud Builder for Odoo

Deploys Odoo 17 + PostgreSQL 15 on Railway's PaaS via their GraphQL API,
then configures the instance using XML-RPC (same as the local Docker builder).
"""

import asyncio
import json
import os
import re
import secrets
import unicodedata
import urllib.request
import urllib.error
import uuid
import threading
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable

from .odoo_builder import BuildState, BuildTask, TaskType, TaskStatus


class RailwayAPIError(Exception):
    """Error from the Railway GraphQL API."""


class RailwayClient:
    """Thin wrapper around Railway's GraphQL API using only stdlib."""

    # Prefer api.railway.app (less likely to be blocked by Cloudflare browser rules),
    # then fall back to backboard.railway.com for compatibility.
    DEFAULT_API_URLS = (
        "https://api.railway.app/graphql/v2",
        "https://backboard.railway.com/graphql/v2",
    )

    def __init__(self, token: str, api_urls: Optional[list[str] | tuple[str, ...]] = None):
        self.token = token.strip()
        if not self.token:
            raise ValueError("Railway API token cannot be empty")
        self.api_urls = self._resolve_api_urls(api_urls)

    @classmethod
    def _resolve_api_urls(cls, api_urls: Optional[list[str] | tuple[str, ...]]) -> list[str]:
        if api_urls:
            resolved = [u.strip() for u in api_urls if u and u.strip()]
            if resolved:
                return resolved

        env_urls = os.environ.get("RAILWAY_API_URL", "")
        if env_urls:
            resolved = [u.strip() for u in env_urls.split(",") if u.strip()]
            if resolved:
                return resolved

        return list(cls.DEFAULT_API_URLS)

    @staticmethod
    def _is_cloudflare_1010(status_code: int, error_body: str) -> bool:
        return status_code == 403 and "error code: 1010" in error_body.lower()

    @staticmethod
    def _compact_error_body(error_body: str, limit: int = 400) -> str:
        compact = re.sub(r"\s+", " ", error_body).strip()
        if len(compact) > limit:
            return compact[:limit] + "..."
        return compact

    @classmethod
    def _format_http_error(cls, api_url: str, status_code: int, error_body: str) -> str:
        compact_body = cls._compact_error_body(error_body)
        if cls._is_cloudflare_1010(status_code, compact_body):
            return (
                f"Railway API HTTP 403 (Cloudflare 1010) via {api_url}: "
                "request blocked by Railway edge firewall. "
                "Try setting RAILWAY_API_URL=https://api.railway.app/graphql/v2 "
                "or retry from a different network/IP."
            )
        return f"Railway API HTTP {status_code} via {api_url}: {compact_body}"

    def _request(self, query: str, variables: dict | None = None) -> dict:
        """Send a GraphQL request to Railway."""
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "OdooBuilder/1.0",
        }

        last_error: Optional[RailwayAPIError] = None

        for i, api_url in enumerate(self.api_urls):
            req = urllib.request.Request(api_url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode(errors="replace") if exc.fp else str(exc)
                last_error = RailwayAPIError(self._format_http_error(api_url, exc.code, error_body))

                # Some networks get blocked on specific edge hosts (Cloudflare 1010).
                # Retry on the next configured endpoint before failing.
                if self._is_cloudflare_1010(exc.code, error_body) and i < len(self.api_urls) - 1:
                    continue
                raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = RailwayAPIError(f"Railway API connection error via {api_url}: {exc}")
                if i < len(self.api_urls) - 1:
                    continue
                raise last_error from exc

            if "errors" in body:
                raise RailwayAPIError(f"Railway API error via {api_url}: {body['errors']}")
            return body.get("data", {})

        if last_error:
            raise last_error
        raise RailwayAPIError("Railway API request failed before execution")

    def create_project(self, name: str) -> tuple[str, str]:
        """Create a Railway project. Returns (project_id, environment_id)."""
        query = """
        mutation($name: String!) {
            projectCreate(input: { name: $name }) {
                id
                environments { edges { node { id } } }
            }
        }
        """
        data = self._request(query, {"name": name})
        project = data["projectCreate"]
        project_id = project["id"]
        env_id = project["environments"]["edges"][0]["node"]["id"]
        return project_id, env_id

    def create_service(self, project_id: str, name: str) -> str:
        """Create a service in a project. Returns service_id."""
        query = """
        mutation($projectId: String!, $name: String!) {
            serviceCreate(input: { projectId: $projectId, name: $name }) {
                id
            }
        }
        """
        data = self._request(query, {"projectId": project_id, "name": name})
        return data["serviceCreate"]["id"]

    def set_service_source(self, service_id: str, image: str) -> None:
        """Set a Docker image as the service source."""
        query = """
        mutation($serviceId: String!, $image: String!) {
            serviceInstanceUpdate(serviceId: $serviceId, input: { source: { image: $image } })
        }
        """
        self._request(query, {"serviceId": service_id, "image": image})

    def set_service_start_command(self, service_id: str, start_command: str) -> None:
        """Set a custom start command on a service."""
        query = """
        mutation($serviceId: String!, $startCommand: String!) {
            serviceInstanceUpdate(serviceId: $serviceId, input: { startCommand: $startCommand })
        }
        """
        self._request(query, {"serviceId": service_id, "startCommand": start_command})

    def set_service_variables(
        self, project_id: str, env_id: str, service_id: str, variables: dict[str, str]
    ) -> None:
        """Set environment variables on a service."""
        query = """
        mutation($input: VariableCollectionUpsertInput!) {
            variableCollectionUpsert(input: $input)
        }
        """
        self._request(query, {
            "input": {
                "projectId": project_id,
                "environmentId": env_id,
                "serviceId": service_id,
                "variables": variables,
            }
        })

    def create_service_domain(self, service_id: str, env_id: str) -> str:
        """Create a public Railway domain for a service. Returns the domain string."""
        query = """
        mutation($serviceId: String!, $environmentId: String!) {
            serviceDomainCreate(input: {
                serviceId: $serviceId,
                environmentId: $environmentId
            }) {
                domain
            }
        }
        """
        data = self._request(query, {
            "serviceId": service_id,
            "environmentId": env_id,
        })
        return data["serviceDomainCreate"]["domain"]

    def get_deployment_status(self, project_id: str) -> str:
        """Get latest deployment status for a project. Returns status string."""
        query = """
        query($projectId: String!) {
            deployments(
                input: { projectId: $projectId }
                first: 1
            ) {
                edges { node { status } }
            }
        }
        """
        data = self._request(query, {"projectId": project_id})
        edges = data.get("deployments", {}).get("edges", [])
        if edges:
            return edges[0]["node"]["status"]
        return "UNKNOWN"

    def delete_project(self, project_id: str) -> None:
        """Delete a Railway project and all its services."""
        query = """
        mutation($id: String!) {
            projectDelete(id: $id)
        }
        """
        self._request(query, {"id": project_id})


class RailwayOdooBuilder:
    """
    Deploys Odoo to Railway cloud.

    Exposes the same interface as OdooBuilder (.state, .build(), .stop(), ._stop_event)
    so the web_interview.py endpoints work unchanged.
    """

    def __init__(self, spec: "ImplementationSpec", railway_token: str):
        from ..schemas.implementation_spec import ImplementationSpec

        self.spec = spec
        self.railway = RailwayClient(railway_token)

        self.state = BuildState(
            build_id=f"build-{uuid.uuid4().hex[:8]}",
            spec_id=spec.spec_id,
            deploy_target="railway",
        )
        self.state.admin_password = secrets.token_urlsafe(12)

        self.on_progress: Optional[Callable[[BuildState], None]] = None
        self._stop_event = threading.Event()
        self._stopping = False
        self._rpc = None

        # Railway resource IDs (for cleanup)
        self._project_id: Optional[str] = None
        self._env_id: Optional[str] = None
        self._odoo_service_id: Optional[str] = None
        self._domain: Optional[str] = None

    def _log(self, task: BuildTask, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        task.logs.append(f"[{timestamp}] {message}")
        print(f"[{task.name}] {message}")
        self._notify_progress()

    def _notify_progress(self):
        if self.on_progress:
            self.on_progress(self.state)

    def _create_tasks(self) -> list[BuildTask]:
        tasks = []

        # 1. Railway setup (replaces Docker setup)
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.DOCKER_SETUP,
            name="Railway Setup",
            description="Create Railway project with Odoo and PostgreSQL services",
        ))

        # 2. Database init (wait for Odoo to boot)
        tasks.append(BuildTask(
            task_id=f"task-{uuid.uuid4().hex[:6]}",
            task_type=TaskType.DATABASE_INIT,
            name="Database Setup",
            description="Wait for Odoo to initialize database on Railway",
        ))

        # 3. Module installations via XML-RPC
        ordered_modules = self.spec.get_install_order()
        for module in ordered_modules:
            tasks.append(BuildTask(
                task_id=f"task-{uuid.uuid4().hex[:6]}",
                task_type=TaskType.MODULE_INSTALL,
                name=f"Install {module.display_name}",
                description=f"Installing {module.module_name} module via XML-RPC",
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

    async def _setup_railway(self, task: BuildTask) -> bool:
        """Create Railway project with Postgres + Odoo services."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 0
        self._notify_progress()

        db_password = secrets.token_urlsafe(16)
        company_name_safe = self.spec.company.name.lower().replace(" ", "-").replace("_", "-")[:20]
        project_name = f"odoo-{company_name_safe}"

        try:
            # Create project
            self._log(task, f"Creating Railway project: {project_name}")
            self._project_id, self._env_id = self.railway.create_project(project_name)
            task.progress = 15
            self._notify_progress()

            # Create Postgres service
            self._log(task, "Creating PostgreSQL 15 service...")
            pg_service_id = self.railway.create_service(self._project_id, "Postgres")
            self.railway.set_service_source(pg_service_id, "postgres:15")
            self.railway.set_service_variables(
                self._project_id, self._env_id, pg_service_id,
                {
                    "POSTGRES_USER": "odoo",
                    "POSTGRES_PASSWORD": db_password,
                    "POSTGRES_DB": "postgres",
                    "PGDATA": "/var/lib/postgresql/data/pgdata",
                },
            )
            task.progress = 40
            self._notify_progress()

            # Create Odoo service
            self._log(task, "Creating Odoo 17 service...")
            self._odoo_service_id = self.railway.create_service(self._project_id, "Odoo")
            self.railway.set_service_source(self._odoo_service_id, "odoo:17.0")
            self.railway.set_service_variables(
                self._project_id, self._env_id, self._odoo_service_id,
                {
                    # Postgres connection (Railway internal networking)
                    "HOST": "${{Postgres.RAILWAY_PRIVATE_DOMAIN}}",
                    "USER": "odoo",
                    "PASSWORD": db_password,
                },
            )
            # Start command: auto-init DB on first boot
            self._log(task, "Setting Odoo start command (--init base)...")
            self.railway.set_service_start_command(
                self._odoo_service_id,
                "odoo --database odoo --init base --db_host $HOST --db_port 5432 "
                f"--db_user odoo --db_password {db_password} --without-demo=all",
            )
            task.progress = 65
            self._notify_progress()

            # Create public domain
            self._log(task, "Creating public domain...")
            self._domain = self.railway.create_service_domain(
                self._odoo_service_id, self._env_id
            )
            domain = self._domain.strip()
            self.state.odoo_url = domain if domain.startswith("http") else f"https://{domain}"
            task.progress = 80
            self._notify_progress()

            self._log(task, f"Railway project created! URL: {self.state.odoo_url}")
            task.progress = 100
            task.status = TaskStatus.COMPLETED

        except Exception as e:
            if isinstance(e, RailwayAPIError):
                self._log(task, f"Railway API error: {e}")
            else:
                self._log(task, f"Railway setup error: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)[:200]
            # Clean up partial project
            if self._project_id:
                self._log(task, "Cleaning up partial Railway project...")
                try:
                    self.railway.delete_project(self._project_id)
                except Exception:
                    pass
            raise
        finally:
            task.completed_at = datetime.now().isoformat()
            self._notify_progress()
        return task.status == TaskStatus.COMPLETED

    async def _init_database(self, task: BuildTask) -> bool:
        """Wait for Odoo to boot and auto-init the database on Railway."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        self._notify_progress()

        url = self.state.odoo_url
        self._log(task, f"Waiting for Odoo at {url} (this can take several minutes)...")
        self._log(task, "Railway is booting Postgres, then Odoo will init the database...")

        # 10 minutes: Postgres boot + Odoo DB init with --init base can be slow
        max_retries = 120
        retry_interval = 5
        check_urls = [f"{url}/web/login", f"{url}/web/database/selector", f"{url}/web"]

        for i in range(max_retries):
            if self._stop_event.is_set():
                task.status = TaskStatus.FAILED
                task.error_message = "Build stopped"
                task.completed_at = datetime.now().isoformat()
                self._notify_progress()
                return False

            task.progress = int((i / max_retries) * 90)
            self._notify_progress()

            for check_url in check_urls:
                try:
                    req = urllib.request.Request(check_url, headers={"User-Agent": "OdooBuilder/1.0"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status == 200:
                            self._log(task, f"Odoo is ready! ({check_url} responded)")
                            task.progress = 100
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = datetime.now().isoformat()
                            self._notify_progress()
                            return True
                except Exception:
                    pass

            if i % 6 == 0 and i > 0:
                elapsed = i * retry_interval
                self._log(task, f"Still waiting... ({elapsed}s elapsed)")

            await asyncio.sleep(retry_interval)

        task.status = TaskStatus.FAILED
        task.error_message = "Odoo did not start in time (10 minutes)"
        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return False

    async def _install_module(self, task: BuildTask) -> bool:
        """Install a module via XML-RPC (no docker exec needed)."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        self._notify_progress()

        module_name = task.module_name
        self._log(task, f"Installing module: {module_name}")
        task.progress = 10
        self._notify_progress()

        try:
            rpc = await self._connect_rpc()
            task.progress = 30
            self._notify_progress()

            # Update module list so Odoo knows what's available
            self._log(task, "Updating module list...")
            rpc.update_module_list()
            task.progress = 50
            self._notify_progress()

            # Find the module
            module_id = rpc.find_module_id(module_name)
            if module_id is None:
                self._log(task, f"Module {module_name} not found, skipping")
                task.progress = 100
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                self._notify_progress()
                return True

            # Check if already installed
            state = rpc.get_module_state(module_id)
            if state == "installed":
                self._log(task, f"Module {module_name} already installed")
                task.progress = 100
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                self._notify_progress()
                return True

            # Install it
            self._log(task, f"Installing {module_name}...")
            rpc.install_module(module_id)
            task.progress = 90
            self._notify_progress()

            self._log(task, f"Module {module_name} installed successfully!")
            task.progress = 100
            task.status = TaskStatus.COMPLETED

        except (ConnectionError, xmlrpc.client.ProtocolError):
            self._rpc = None
            raise
        except Exception as e:
            self._log(task, f"Failed to install {module_name}: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)

        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return task.status == TaskStatus.COMPLETED

    @staticmethod
    def _sanitize_login(name: str) -> str:
        nfkd = unicodedata.normalize("NFKD", name)
        ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
        sanitized = re.sub(r"[^a-z0-9]", "_", ascii_name.lower())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        return sanitized or "user"

    async def _connect_rpc(self, max_retries=10, retry_delay=3):
        """Create an authenticated XML-RPC connection to the Railway Odoo instance."""
        if self._stopping:
            raise RuntimeError("Build stopped, resources cleaned up")
        if self._rpc is not None:
            return self._rpc

        from ..swarm.apply import OdooRPC, RPCConfig

        config = RPCConfig(
            url=self.state.odoo_url,
            database=self.state.db_name,
            username="admin",
            password=self.state.admin_password,
        )
        rpc = OdooRPC(config)

        for attempt in range(max_retries):
            if self._stopping:
                raise RuntimeError("Build stopped, resources cleaned up")
            try:
                rpc.login()
                self._rpc = rpc
                return rpc
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(retry_delay)

        raise RuntimeError("Could not connect to Odoo via RPC")

    async def _configure_module(self, task: BuildTask) -> bool:
        """Configure a module's settings via XML-RPC (identical to OdooBuilder)."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 10
        self._notify_progress()

        self._log(task, f"Configuring {task.module_name}...")

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
            rpc = await self._connect_rpc()
            task.progress = 50
            self._notify_progress()

            self._log(task, f"Applying settings: {list(module_cfg.settings.keys())}")
            config_id = rpc._execute("res.config.settings", "create", [module_cfg.settings])
            task.progress = 70
            self._notify_progress()

            rpc._execute("res.config.settings", "set_values", [[config_id]])
            task.progress = 100
            self._log(task, "Settings applied successfully")
        except (ConnectionError, xmlrpc.client.ProtocolError):
            self._rpc = None
            raise
        except Exception as e:
            self._log(task, f"Warning: settings apply failed ({e}), continuing anyway")
            task.progress = 100

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return True

    async def _setup_users(self, task: BuildTask) -> bool:
        """Set up user roles via XML-RPC (identical to OdooBuilder)."""
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
            rpc = await self._connect_rpc()
            task.progress = 20
            self._notify_progress()

            company_slug = self._sanitize_login(self.spec.company.name)[:20]
            total_roles = len(self.spec.user_roles)

            for i, role in enumerate(self.spec.user_roles):
                role_progress = 20 + int((i / total_roles) * 70)
                task.progress = role_progress
                self._notify_progress()

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
                        user_pw = secrets.token_urlsafe(10)
                        user_vals = {
                            "name": f"{role.name}{suffix}",
                            "login": login,
                            "password": user_pw,
                        }
                        if group_ids:
                            user_vals["groups_id"] = [(4, gid) for gid in group_ids]
                        rpc._execute("res.users", "create", [user_vals])
                        self._log(task, f"    Created user: {login} (password: {user_pw})")
                    except Exception as e:
                        if "already exists" in str(e).lower() or "unique" in str(e).lower():
                            self._log(task, f"    User {login} already exists, skipping")
                        else:
                            self._log(task, f"    Warning: failed to create {login}: {e}")

        except (ConnectionError, xmlrpc.client.ProtocolError):
            self._rpc = None
            raise
        except Exception as e:
            self._log(task, f"Warning: user setup encountered errors ({e})")

        task.progress = 100
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._log(task, "User roles configured")
        self._notify_progress()
        return True

    async def _final_config(self, task: BuildTask) -> bool:
        """Apply final company configuration via XML-RPC (identical to OdooBuilder)."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now().isoformat()
        task.progress = 10
        self._notify_progress()

        self._log(task, f"Setting company name to: {self.spec.company.name}")
        self._log(task, f"Industry: {self.spec.company.industry}")

        try:
            rpc = await self._connect_rpc()
            task.progress = 30
            self._notify_progress()

            company_vals = {"name": self.spec.company.name}

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

            rpc._execute("res.company", "write", [[1], company_vals])
            self._log(task, "Company settings applied")

            if self.spec.company.timezone:
                self._log(task, f"Setting admin timezone: {self.spec.company.timezone}")
                rpc._execute("res.users", "write", [[rpc.uid], {"tz": self.spec.company.timezone}])

            task.progress = 100
            self._log(task, "Final configuration complete!")

        except (ConnectionError, xmlrpc.client.ProtocolError):
            self._rpc = None
            raise
        except Exception as e:
            self._log(task, f"Warning: final config encountered errors ({e})")
            task.progress = 100

        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._notify_progress()
        return True

    async def build(self) -> BuildState:
        """Execute the complete Railway build process."""
        self.state.status = TaskStatus.IN_PROGRESS
        self.state.started_at = datetime.now().isoformat()
        self.state.tasks = self._create_tasks()
        self._notify_progress()

        for task in self.state.tasks:
            if self._stop_event.is_set():
                self.state.status = TaskStatus.FAILED
                break

            success = False

            if task.task_type == TaskType.DOCKER_SETUP:
                success = await self._setup_railway(task)
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
                self.state.status = TaskStatus.FAILED
                break

        if self.state.status == TaskStatus.FAILED and self._project_id:
            try:
                if self.state.tasks:
                    self._log(self.state.tasks[-1], "Cleaning up failed Railway project...")
                else:
                    print("Cleaning up failed Railway project...")
                self.railway.delete_project(self._project_id)
            except Exception:
                pass  # Best-effort cleanup

        if self.state.status != TaskStatus.FAILED:
            self.state.status = TaskStatus.COMPLETED

        self.state.completed_at = datetime.now().isoformat()
        self._notify_progress()

        return self.state

    def get_state(self) -> BuildState:
        return self.state

    def stop(self):
        """Stop the build and delete the Railway project."""
        self._stopping = True
        self._stop_event.set()
        self.state.status = TaskStatus.FAILED
        self.state.completed_at = datetime.now().isoformat()
        self._rpc = None

        if self._project_id:
            try:
                self.railway.delete_project(self._project_id)
                print(f"Railway project {self._project_id} deleted")
            except Exception as e:
                print(f"Warning: could not delete Railway project: {e}")
