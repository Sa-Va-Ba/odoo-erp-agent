#!/usr/bin/env python3
"""
CLI for the Adaptive Interview Agent.

Usage:
    python -m src.adaptive_cli --client "Company Name" --industry "Tech"

Environment Variables:
    GROQ_API_KEY: For Groq free tier (recommended, 1000 req/day)

If no API key is set, falls back to Ollama (local, requires `ollama serve`)

The adaptive agent dynamically generates questions based on:
1. Initial discovery responses
2. Detected business signals
3. Odoo module configuration requirements
4. LLM analysis of information gaps
"""

import argparse
import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.adaptive_interview_agent import (
    AdaptiveInterviewAgent,
    get_interview_llm_manager,
)


def main():
    parser = argparse.ArgumentParser(
        description="Adaptive Odoo Implementation Interview",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (uses Groq if GROQ_API_KEY set, else Ollama)
    python -m src.adaptive_cli --client "Acme Corp" --industry "Manufacturing"

    # With custom config file for questions
    python -m src.adaptive_cli --client "Test Co" --industry "Services" \\
        --config ./custom_questions.json

LLM Providers (free/open-source only):
    - Groq: Set GROQ_API_KEY (free at console.groq.com, 1000 req/day)
    - Ollama: Run locally with `ollama serve` (unlimited, no API key needed)
        """
    )

    parser.add_argument(
        "--client", "-c",
        required=True,
        help="Client company name"
    )
    parser.add_argument(
        "--industry", "-i",
        required=True,
        help="Client industry (Manufacturing, Retail, Services, etc.)"
    )
    parser.add_argument(
        "--config",
        help="Path to custom module config requirements JSON file"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./outputs",
        help="Output directory for interview results"
    )

    args = parser.parse_args()

    # Check for API keys
    has_groq = bool(os.getenv("GROQ_API_KEY"))

    print(f"\n{'='*60}")
    print("Adaptive Odoo Implementation Interview")
    print(f"{'='*60}")
    print(f"Client: {args.client}")
    print(f"Industry: {args.industry}")

    if has_groq:
        print("LLM Provider: Groq (Llama 3.3 70B, free tier)")
    else:
        print("LLM Provider: Ollama (local)")
        print("  Tip: Set GROQ_API_KEY for better quality (free at console.groq.com)")

    print(f"Output: {args.output_dir}")
    print(f"{'='*60}\n")

    # Initialize agent
    agent = AdaptiveInterviewAgent(
        client_name=args.client,
        industry=args.industry,
        output_dir=args.output_dir,
        config_knowledge_path=args.config,
    )

    # Show available providers
    if agent.llm_manager:
        status = agent.llm_manager.get_status()
        print(f"Active LLM: {status.get('current_provider', 'None')}")
        for provider, info in status.get("providers", {}).items():
            print(f"  - {provider}: {info.get('status')} ({info.get('model')})")
        print()

    # Run interview
    print("Starting adaptive interview...")
    print("Commands: 'done' to finish, 'skip' to skip, 'status' to see progress\n")

    question_count = 0
    while True:
        question = agent.get_next_question()

        if not question:
            print("\n✅ Interview complete - all relevant questions covered.")
            break

        question_count += 1
        print(f"\n{'─'*50}")
        print(f"[{question.module_source}] Question {question_count}")
        print(f"{'─'*50}")
        print(f"\n{question.text}\n")

        if question.context:
            print(f"(Context: {question.context})")

        try:
            response = input("\n> ").strip()
        except KeyboardInterrupt:
            print("\n\nInterview interrupted.")
            break
        except EOFError:
            print("\n\nEnd of input.")
            break

        if response.lower() == 'done':
            print("Finishing interview early...")
            break

        if response.lower() == 'skip':
            print("Question skipped.")
            continue

        if response.lower() == 'status':
            summary = agent.get_interview_summary()
            print(f"\n--- Status ---")
            print(f"Questions asked: {summary['questions_asked']}")
            print(f"Modules detected: {', '.join(summary['recommended_modules']) or 'None yet'}")
            print(f"Signals: {summary['detected_signals']}")
            continue

        # Process the response
        result = agent.process_response(response, question)

        # Show feedback
        if result.get("signals_detected"):
            signals = ", ".join(result["signals_detected"].keys())
            print(f"  🔍 Signals detected: {signals}")

        if result.get("modules_identified"):
            print(f"  📦 Modules: {', '.join(result['modules_identified'][:5])}")

        if result.get("followup_generated"):
            print("  💡 Follow-up question queued")

        print(f"  📋 Questions remaining: {result.get('questions_in_queue', 0)}")

    # Save results
    filepath = agent.save_interview()
    summary = agent.get_interview_summary()

    print(f"\n{'='*60}")
    print("Interview Summary")
    print(f"{'='*60}")
    print(f"Questions asked: {summary['questions_asked']}")
    print(f"Recommended modules: {', '.join(summary['recommended_modules']) or 'None detected'}")

    if summary.get('detected_signals'):
        print(f"\nDetected signals:")
        for signal, count in summary['detected_signals'].items():
            if count > 0:
                print(f"  - {signal}: {count}")

    print(f"\nResults saved to: {filepath}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
