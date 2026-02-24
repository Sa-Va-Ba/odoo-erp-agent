#!/usr/bin/env python3
"""
Interactive Text Interview for Odoo Setup

Run directly in your terminal (NOT through Claude):
    cd /Users/samvanbael/Documents/odoo-erp-agent
    python3 run_interactive_interview.py

This is an INTERACTIVE interview - you type your answers!
"""

import warnings
warnings.filterwarnings('ignore')

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.adaptive_interview_agent import AdaptiveInterviewAgent


def main():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║         ODOO IMPLEMENTATION INTERVIEW                          ║
║         Interactive Text-Based Discovery                       ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    # Get client info
    print("First, tell me about the client:\n")
    client_name = input("Client/Company name: ").strip() or "Test Company"
    industry = input("Industry (e.g., E-commerce, Manufacturing, Services): ").strip() or "General"

    print(f"\n{'='*60}")
    print(f"Starting interview for: {client_name} ({industry})")
    print(f"{'='*60}")
    print("\nCommands during interview:")
    print("  'skip'   - Skip current question")
    print("  'status' - See progress and detected modules")
    print("  'done'   - End interview early")
    print(f"{'='*60}\n")

    # Initialize agent
    agent = AdaptiveInterviewAgent(
        client_name=client_name,
        industry=industry,
        output_dir="./outputs"
    )

    # Show LLM status
    if agent.llm_manager:
        status = agent.llm_manager.get_status()
        provider = status.get('current_provider', 'None')
        print(f"✓ LLM: {provider}")

    print("\nLet's begin!\n")

    question_count = 0

    while True:
        # Get next question
        question = agent.get_next_question()

        if not question:
            print("\n✅ All relevant questions have been asked!")
            break

        question_count += 1

        # Display question
        print(f"\n{'─'*60}")
        print(f"[{question.module_source}] Question {question_count}")
        print(f"{'─'*60}")
        print(f"\n{question.text}\n")

        # Get user input
        try:
            response = input("Your answer: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n⏹️ Interview interrupted")
            break

        # Handle commands
        if response.lower() == 'done':
            print("\nEnding interview early...")
            break

        if response.lower() == 'skip':
            print("  ⏭️ Skipped")
            continue

        if response.lower() == 'status':
            summary = agent.get_interview_summary()
            print(f"\n{'─'*40}")
            print(f"Questions asked: {summary['questions_asked']}")
            print(f"Modules detected: {', '.join(summary['recommended_modules']) or 'None yet'}")
            print(f"Signals: {dict((k,v) for k,v in summary['detected_signals'].items() if v > 0)}")
            print(f"{'─'*40}")
            # Re-show the question
            print(f"\n{question.text}\n")
            response = input("Your answer: ").strip()
            if response.lower() in ['done', 'skip', 'status']:
                continue

        if not response:
            print("  (empty response, skipping)")
            continue

        # Process the response
        result = agent.process_response(response, question)

        # Show feedback
        if result.get("signals_detected"):
            signals = list(result["signals_detected"].keys())
            print(f"  🔍 Detected: {', '.join(signals)}")

        if result.get("modules_identified"):
            modules = result["modules_identified"][:5]
            print(f"  📦 Modules: {', '.join(modules)}")

        remaining = result.get("questions_in_queue", 0)
        if remaining > 0:
            print(f"  📋 {remaining} questions remaining")

    # Save results
    print(f"\n{'='*60}")
    print("SAVING RESULTS...")
    print(f"{'='*60}")

    filepath = agent.save_interview()
    summary = agent.get_interview_summary()

    print(f"\n📊 INTERVIEW SUMMARY")
    print(f"{'─'*40}")
    print(f"Client: {client_name}")
    print(f"Industry: {industry}")
    print(f"Questions asked: {summary['questions_asked']}")
    print(f"\nRecommended Odoo modules:")
    for module in summary['recommended_modules']:
        print(f"  • {module}")

    if summary.get('detected_signals'):
        print(f"\nDetected business signals:")
        for signal, count in sorted(summary['detected_signals'].items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"  • {signal}: {count}")

    print(f"\n📄 Results saved to: {filepath}")
    print(f"{'='*60}")
    print("\nNext step: Run the module selection swarm:")
    print(f"  python3 -m src.swarm.cli --input {filepath}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
