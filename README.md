# Odoo ERP Implementation Agent

An AI-powered multi-agent system for automating Odoo ERP implementations through intelligent client interviews, specification generation, and coordinated implementation.

## Overview

This system uses a team of specialized AI agents to streamline Odoo implementations:

```
ORCHESTRATOR AGENT (Project Manager)
├── INTERVIEW AGENT (Requirements Gathering)      ← You are here
├── SPECIFICATION AGENT (Documentation)
├── TECHNICAL ARCHITECT AGENT (Technical Supervision)
│   ├── MODULE SELECTOR AGENT (Open-source Selection)
│   ├── CONFIGURATION AGENT (Odoo Setup)
│   ├── CODING AGENT (Development & Scripting)
│   └── DATA MIGRATION AGENT (ETL & Import)
└── QA/VALIDATION AGENT (Quality Control)
```

## Current Status: Interview Module (Phase 1)

The Interview Agent is the first module, responsible for conducting structured client discovery interviews to gather requirements for Odoo implementation.

### Features

- **10 Interview Domains**: Comprehensive coverage of all business areas
  1. Company Basics (size, structure, locations)
  2. Current Systems & Pain Points
  3. Finance & Accounting
  4. Sales & CRM
  5. Inventory & Operations
  6. HR & Payroll
  7. Project Management
  8. Integrations
  9. Users & Permissions
  10. Data Migration

- **Intelligent Questioning**: Follow-up questions when answers are vague
- **Odoo Context**: Built-in knowledge of Odoo capabilities per domain
- **Session Management**: Save/resume interviews, track progress
- **Structured Output**: Generates requirements JSON for downstream agents

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/odoo-erp-agent.git
cd odoo-erp-agent

# Install in development mode
pip install -e ".[dev]"

# Or with LLM support
pip install -e ".[dev,llm]"
```

## Usage

### Interactive Interview Mode

```bash
# Start a new interview
python -m src.cli --client "ACME Corporation" --industry "Manufacturing"

# Resume a previous session
python -m src.cli --resume interview-20260205143000

# List all interview domains
python -m src.cli --list-domains
```


### Module Selection Swarm

Generate a module plan and configuration tasks from an interview output JSON:

```bash
python -m src.swarm.cli --input outputs/requirements-interview-20260205183339.json
python -m src.swarm.cli --input outputs/requirements-interview-20260205183339.json --odoo-version 5.3
```

This produces:
- `module-plan-*.json`
- `config-tasks-*.json`
- `implementation-spec-*.md`
- `swarm-audit-*.json`

Note: Swarm defaults to Odoo Community edition (free). Use `--edition enterprise` to include enterprise-only modules.
Enterprise modules can define explicit free alternatives in `src/knowledge/odoo_modules.json` via `community_alternatives`.
Version-aware registry selection is enabled: `--odoo-version 5.3` auto-uses `src/knowledge/odoo_modules_5_3.json`.

Run QA agents (architecture, codebase, setup validation):

```bash
python -m src.swarm.qa --module-plan outputs/module-plan-YYYYMMDDHHMMSS.json
```

Apply selected modules to a target instance:

```bash
python -m src.swarm.apply --module-plan outputs/module-plan-YYYYMMDDHHMMSS.json --dry-run
python -m src.swarm.apply --module-plan outputs/module-plan-YYYYMMDDHHMMSS.json --url http://localhost:8069 --database mydb --username admin --password admin
```

### Generate LLM Prompts

For use with Claude, GPT, or other LLMs:

```bash
python -m src.cli --client "ACME Corp" --industry "Manufacturing" --generate-prompts
```

### Programmatic Usage

```python
from src.agents import InterviewAgent
from src.prompts import create_domain_prompt

# Create an interview agent
agent = InterviewAgent(
    client_name="ACME Corporation",
    industry="Manufacturing"
)

# Start interview
print(agent.start_interview())

# Get next question
question = agent.get_next_question()
print(agent.format_question_prompt(question))

# Record response
agent.record_response(question, "We use QuickBooks for accounting...")

# Generate requirements JSON
requirements_file = agent.generate_requirements_json()
```

## Output Format

The Interview Agent outputs a `requirements.json` file with the following structure:

```json
{
  "project_id": "odoo-impl-20260205143000",
  "client_name": "ACME Corporation",
  "industry": "Manufacturing",
  "company_profile": {
    "name": "ACME Corporation",
    "employee_count": 150,
    "locations": ["Brussels", "Antwerp"],
    "currencies": ["EUR", "USD"]
  },
  "requirements_by_domain": {
    "accounting": [...],
    "sales": [...],
    "inventory": [...]
  },
  "integrations_needed": [...],
  "users_and_roles": [...],
  "data_migration_scope": {...}
}
```

## Architecture

```
odoo-erp-agent/
├── src/
│   ├── agents/
│   │   └── interview_agent.py    # Main Interview Agent
│   ├── schemas/
│   │   ├── shared_context.py     # Shared context between agents
│   │   └── interview_domains.py  # 10 interview domain definitions
│   ├── prompts/
│   │   └── interview_agent_prompt.py  # LLM prompt templates
│   └── cli.py                    # Command-line interface
├── tests/
├── outputs/                      # Generated files
└── pyproject.toml
```

## Roadmap

### Phase 1: Interview Module (Current)
- [x] Interview Agent with 10 domains
- [x] CLI interface
- [x] Session save/resume
- [x] Requirements JSON output
- [ ] LLM integration (Claude API)

### Phase 2: Specification Module
- [ ] Specification Agent
- [ ] Requirements-to-spec conversion
- [ ] Module recommendation engine

### Phase 3: Technical Architecture
- [ ] Technical Architect Agent
- [ ] Module Selector with OCA database
- [ ] Configuration Agent

### Phase 4: Execution
- [ ] Coding Agent
- [ ] Data Migration Agent
- [ ] QA/Validation Agent

### Phase 5: Orchestration
- [ ] Orchestrator Agent
- [ ] Full workflow automation

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## License

MIT License - see LICENSE file for details.
