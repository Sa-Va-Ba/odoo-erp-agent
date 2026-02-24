#!/usr/bin/env python3
"""
Quick launcher that pre-seeds a completed interview PRD,
then starts the web server so you can test the deploy workflow directly.

Usage:
    python3 test_deploy_workflow.py

Then open http://localhost:5001 — the page loads straight into the
summary+deploy view (no interview needed).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.schemas.implementation_spec import create_spec_from_interview
import web_interview

# ── Fake interview summary (as if the interview just finished) ──
demo_summary = {
    "client_name": "Acme Manufacturing",
    "industry": "Manufacturing",
    "questions_asked": 12,
    "domains_covered": ["sales", "inventory", "manufacturing", "accounting"],
    "recommended_modules": [
        "sale_management",
        "stock",
        "mrp",
        "account",
        "purchase",
        "contacts",
    ],
    "scoping_responses": [
        {"q": "Company name?", "a": "Acme Manufacturing"},
        {"q": "Industry?", "a": "We are a mid-size manufacturing company in Belgium"},
        {"q": "Employees?", "a": "About 45 employees across production and office"},
    ],
    "domain_responses": {
        "sales": [
            {"q": "How do you manage sales?", "a": "We do B2B quotations and invoicing"},
        ],
        "inventory": [
            {"q": "Warehouse workflow?", "a": "We have one warehouse with barcode scanning"},
        ],
        "manufacturing": [
            {"q": "Production process?", "a": "We use bills of materials and work orders"},
        ],
    },
}

# Generate the PRD spec from the fake summary
spec = create_spec_from_interview(demo_summary)
prd_result = {
    "markdown": spec.to_markdown(),
    "json": spec.to_dict(),
    "company_name": spec.company.name,
    "module_count": len(spec.modules),
    "estimated_minutes": spec.get_total_estimated_time(),
}

# Seed the demo-result endpoint so the UI auto-loads it
web_interview.last_demo_result = {"summary": demo_summary, "prd": prd_result}

print("""
╔═══════════════════════════════════════════════════════════╗
║         DEPLOY WORKFLOW TEST                              ║
╠═══════════════════════════════════════════════════════════╣
║  Pre-loaded: Acme Manufacturing (6 modules)               ║
║  Open: http://localhost:5001                              ║
║                                                           ║
║  → Select "Local Docker" or "Railway Cloud"               ║
║  → Click "Deploy to Odoo"                                 ║
║                                                           ║
║  For Railway: set RAILWAY_API_TOKEN env var first          ║
╚═══════════════════════════════════════════════════════════╝
""")

web_interview.app.run(host="0.0.0.0", port=5001, debug=False)
