# Swarm Architecture for Odoo Module Setup

## Purpose
Turn interview output JSON into a validated module plan, configuration tasks, and an implementation spec. The system moderates a swarm of specialized agents and consolidates results into a single, auditable decision.

## Components
- **Normalizer** (`src/swarm/normalizer.py`)
  - Loads interview output JSON
  - Extracts signals and evidence for downstream agents
- **Module Registry** (`src/knowledge/odoo_modules.json`, `src/knowledge/odoo_modules_5_3.json`, `src/swarm/registry.py`, `src/swarm/registry_resolver.py`)
  - Version-aware module catalogs (modern/default and dedicated 5.3)
  - Curated module metadata: dependencies, compatibility, and free alternatives
- **Agents** (`src/swarm/agents/*`)
  - Domain agents that map signals to modules
  - Risk agents that surface integration/migration flags
- **Moderator** (`src/swarm/moderator.py`)
  - Merges agent outputs
  - Handles conflicts
  - Flags enterprise-only modules when edition is unknown
- **Validator** (`src/swarm/validator.py`)
  - Ensures dependencies are included
  - Auto-adds base module
- **Orchestrator** (`src/swarm/orchestrator.py`)
  - Runs the full workflow
  - Writes outputs to `outputs/`
- **CLI** (`src/swarm/cli.py`)
  - Executes the swarm on a given interview JSON
- **Apply Runner** (`src/swarm/apply.py`)
  - Loads selected modules from module plan
  - Applies modules over XML-RPC (legacy and modern endpoints)
  - Writes execution report with install/missing/failure status
- **QA Agents** (`src/swarm/qa.py`)
  - `architecture_qa_agent`: validates required components and orchestration wiring
  - `codebase_qa_agent`: compiles swarm Python files for syntax/import integrity
  - `odoo_setup_qa_agent`: validates community compliance, dependencies, and version compatibility

## Output Artifacts
- `module-plan-*.json` — consolidated module selection and rationale
- `config-tasks-*.json` — configuration tasks per module
- `implementation-spec-*.md` — human-readable implementation spec
- `swarm-audit-*.json` — raw agent decisions for traceability

## Execution Flow
1. Ingest interview JSON
2. Normalize + signal extraction
3. Run domain agents in parallel (conceptually)
4. Moderate and resolve conflicts
5. Validate dependencies
6. Emit outputs
7. Run QA agents on produced module plan
8. Execute apply runner for dry-run or real module installation

## Extension Points
- Expand `odoo_modules.json` to include more modules
- Add new agents for industry-specific recommendations
- Add an RPC execution layer to install/configure modules in Odoo
