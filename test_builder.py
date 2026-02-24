#!/usr/bin/env python3
"""
Test script to demonstrate the builder flow with simulated interview output.

Run:
    python3 test_builder.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.schemas.implementation_spec import (
    ImplementationSpec,
    CompanySetup,
    ModuleConfig,
    ConfigPriority,
    UserRole,
    create_spec_from_interview
)
from src.builders.odoo_builder import OdooBuilder, BuildState, TaskStatus


def create_sample_interview_output() -> dict:
    """
    Create a realistic interview output as if someone completed the interview.
    This simulates a small e-commerce company with inventory.
    """
    return {
        "client_name": "TechGadgets Pro",
        "industry": "E-commerce",
        "session_id": "test-session-001",
        "questions_asked": 15,
        "detected_signals": {
            "sales": 5,
            "inventory": 4,
            "ecommerce": 3,
            "finance": 2,
        },
        "domains_covered": ["sales", "inventory", "finance", "ecommerce"],
        "recommended_modules": [
            "sale_management",
            "crm",
            "stock",
            "account",
            "website_sale",
            "website"
        ],
        "scoping_responses": [
            {
                "q": "What's the main thing your company does?",
                "a": "We sell electronics and tech gadgets online through our website"
            },
            {
                "q": "How do customers typically buy from you?",
                "a": "Mostly through our online store, some B2B customers call directly"
            },
            {
                "q": "Do you keep physical inventory/stock?",
                "a": "Yes, we have a warehouse with about 500 different products"
            },
            {
                "q": "Do you manufacture or assemble products?",
                "a": "No, we buy finished goods from suppliers and resell them"
            },
            {
                "q": "How many employees will use the system?",
                "a": "About 10 people - sales team, warehouse staff, and management"
            },
            {
                "q": "What's your biggest headache right now?",
                "a": "Tracking inventory across multiple sales channels and keeping stock levels accurate"
            }
        ],
        "domain_responses": {
            "sales": [
                {
                    "q": "Walk me through your sales process",
                    "a": "Customer finds product online, adds to cart, checks out. For B2B we send quotes first."
                },
                {
                    "q": "How do you price your products?",
                    "a": "Standard prices for retail, discounted prices for wholesale buyers"
                }
            ],
            "inventory": [
                {
                    "q": "Describe your warehouse setup",
                    "a": "Single warehouse with zones for different product categories, about 2000 sq ft"
                },
                {
                    "q": "Do products need serial numbers or batch tracking?",
                    "a": "Yes for electronics we need serial numbers for warranty purposes"
                }
            ],
            "finance": [
                {
                    "q": "Which countries do you operate in?",
                    "a": "Just United States for now"
                },
                {
                    "q": "What are your payment terms?",
                    "a": "Online orders are paid upfront, B2B is Net 30"
                }
            ]
        }
    }


def print_spec(spec: ImplementationSpec):
    """Pretty print the implementation specification."""
    print("\n" + "="*60)
    print("📋 IMPLEMENTATION SPECIFICATION")
    print("="*60)

    print(f"\n🏢 Company: {spec.company.name}")
    print(f"   Industry: {spec.company.industry}")
    print(f"   Country: {spec.company.country}")
    print(f"   Currency: {spec.company.currency}")

    print(f"\n📦 Modules to Install ({len(spec.modules)}):")
    for mod in spec.get_install_order():
        priority_emoji = {
            ConfigPriority.CRITICAL: "🔴",
            ConfigPriority.HIGH: "🟠",
            ConfigPriority.MEDIUM: "🟡",
            ConfigPriority.LOW: "🟢"
        }.get(mod.priority, "⚪")
        deps = f" (deps: {', '.join(mod.depends_on)})" if mod.depends_on else ""
        print(f"   {priority_emoji} {mod.display_name} ({mod.module_name}){deps}")
        print(f"      Est. time: {mod.estimated_minutes} min | {mod.notes}")

    print(f"\n👥 User Roles ({len(spec.user_roles)}):")
    for role in spec.user_roles:
        print(f"   - {role.name}: {role.count} user(s)")

    if spec.pain_points:
        print(f"\n⚠️ Pain Points to Address:")
        for pain in spec.pain_points:
            print(f"   - {pain}")

    print(f"\n⏱️ Total Estimated Setup Time: {spec.get_total_estimated_time()} minutes")
    print("="*60)


def print_build_state(state: BuildState):
    """Pretty print build state."""
    status_emoji = {
        TaskStatus.PENDING: "⏳",
        TaskStatus.IN_PROGRESS: "🔄",
        TaskStatus.COMPLETED: "✅",
        TaskStatus.FAILED: "❌",
        TaskStatus.SKIPPED: "⏭️"
    }

    print(f"\n{'─'*60}")
    print(f"Build Progress: {state.get_overall_progress()}% | Status: {state.status.value}")
    print(f"{'─'*60}")

    for task in state.tasks:
        emoji = status_emoji.get(task.status, "❓")
        status_str = task.status.value.upper()

        if task.status == TaskStatus.IN_PROGRESS:
            print(f"  {emoji} [{status_str:12}] {task.name} ({task.progress}%)")
        else:
            print(f"  {emoji} [{status_str:12}] {task.name}")

        # Show recent logs for in-progress or failed tasks
        if task.status in [TaskStatus.IN_PROGRESS, TaskStatus.FAILED] and task.logs:
            for log in task.logs[-3:]:
                print(f"      └─ {log}")


async def run_test():
    """Run the complete test flow."""

    print("\n" + "🧪 "*20)
    print("ODOO BUILDER TEST - Simulated Interview Output")
    print("🧪 "*20)

    # Step 1: Create sample interview output
    print("\n📝 Step 1: Creating sample interview output...")
    interview_output = create_sample_interview_output()
    print(f"   Client: {interview_output['client_name']}")
    print(f"   Industry: {interview_output['industry']}")
    print(f"   Domains: {', '.join(interview_output['domains_covered'])}")
    print(f"   Signals detected: {interview_output['detected_signals']}")

    # Step 2: Convert to Implementation Spec
    print("\n🔄 Step 2: Converting to Implementation Specification...")
    spec = create_spec_from_interview(interview_output)
    print_spec(spec)

    # Save spec to file for reference
    spec_path = Path("./outputs/test-spec.json")
    spec_path.parent.mkdir(exist_ok=True)
    spec_path.write_text(spec.to_json(indent=2))
    print(f"\n💾 Specification saved to: {spec_path}")

    # Step 3: Create Builder and show tasks
    print("\n🔧 Step 3: Initializing Builder...")
    builder = OdooBuilder(
        spec=spec,
        work_dir="./odoo-instances/test-instance",
        odoo_version="17.0"
    )

    # Create tasks to show what would be executed
    builder.state.tasks = builder._create_tasks()

    print(f"\n📋 Build Plan ({len(builder.state.tasks)} tasks):")
    for i, task in enumerate(builder.state.tasks, 1):
        print(f"   {i}. {task.name}")
        print(f"      Type: {task.task_type.value}")
        print(f"      Description: {task.description}")
        if task.module_name:
            print(f"      Module: {task.module_name}")

    # Step 4: Ask if user wants to run the build
    print("\n" + "="*60)
    print("🚀 READY TO BUILD")
    print("="*60)
    print(f"\nThis will:")
    print(f"  1. Create Docker containers (Odoo 17 + PostgreSQL)")
    print(f"  2. Initialize database: {builder.state.db_name}")
    print(f"  3. Install {len(spec.modules)} modules")
    print(f"  4. Configure company and users")
    print(f"\nOdoo will be available at: http://localhost:{builder.state.odoo_port}")
    print(f"Login: admin / {builder.state.admin_password}")

    # Check if Docker is available
    import subprocess
    docker_check = subprocess.run(["which", "docker"], capture_output=True)
    if docker_check.returncode != 0:
        print("\n⚠️  WARNING: Docker is not installed!")
        print("   Install Docker Desktop from: https://docker.com/products/docker-desktop")
        print("\n   Skipping actual build. Showing what would happen...")

        # Simulate build progress for demo
        print("\n📊 Simulated Build Progress:")
        for task in builder.state.tasks:
            task.status = TaskStatus.COMPLETED
            print_build_state(builder.state)
            await asyncio.sleep(0.3)

        print("\n✅ (Simulated) Build Complete!")
        return

    # Docker is available - ask to proceed
    print("\n" + "-"*60)
    response = input("Do you want to start the actual build? (y/n): ").strip().lower()

    if response != 'y':
        print("\n⏹️ Build cancelled. You can run it later from the web UI.")
        return

    # Step 5: Run the actual build with progress updates
    print("\n🔨 Starting build...")

    def on_progress(state: BuildState):
        print_build_state(state)

    builder.on_progress = on_progress

    final_state = await builder.build()

    # Step 6: Show final results
    print("\n" + "="*60)
    if final_state.status == TaskStatus.COMPLETED:
        print("🎉 BUILD COMPLETE!")
        print("="*60)
        print(f"\n🌐 Odoo is running at: {final_state.odoo_url}")
        print(f"📁 Database: {final_state.db_name}")
        print(f"🔑 Login: admin / {builder.state.admin_password}")
        print(f"\nOpen in browser: {final_state.odoo_url}")
    else:
        print("❌ BUILD FAILED")
        print("="*60)
        failed_tasks = [t for t in final_state.tasks if t.status == TaskStatus.FAILED]
        for task in failed_tasks:
            print(f"\n   Failed task: {task.name}")
            print(f"   Error: {task.error_message}")
            if task.logs:
                print(f"   Last logs:")
                for log in task.logs[-5:]:
                    print(f"      {log}")


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              ODOO BUILDER TEST SCRIPT                          ║
║                                                                 ║
║  This demonstrates the complete flow:                          ║
║  1. Simulated interview output                                  ║
║  2. Conversion to Implementation Spec                           ║
║  3. Builder task creation                                       ║
║  4. (Optional) Actual Docker build                              ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    asyncio.run(run_test())
