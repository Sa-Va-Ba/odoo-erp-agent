"""
CLI Interface for Odoo ERP Implementation Interview Agent

This provides a command-line interface for running interviews,
either interactively or with LLM assistance.
"""

import argparse
import sys
from pathlib import Path

from .agents.interview_agent import (
    InterviewAgent,
    InterviewState,
    create_interview_prompt
)
from .schemas.interview_domains import get_total_domains


def print_header():
    """Print CLI header."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ODOO ERP IMPLEMENTATION AGENT - Interview Module          ║
║                                                               ║
║     An AI-powered requirements gathering system               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def run_interactive_interview(agent: InterviewAgent):
    """Run an interactive interview session in the terminal."""
    print(agent.start_interview())
    print(agent.get_status_display())

    while agent.session.state == InterviewState.IN_PROGRESS:
        question = agent.get_next_question()

        if question is None:
            # Current domain complete
            print(f"\n✓ {agent.current_domain.title} section complete!")
            agent.complete_current_domain()

            if agent.session.state == InterviewState.COMPLETED:
                break

            print(f"\nMoving to: {agent.current_domain.title}")
            print(agent.get_status_display())
            continue

        # Display the question
        print(agent.format_question_prompt(question))

        # Get response
        response = input("\nYour response: ").strip()

        # Handle special commands
        if response.lower() == 'skip':
            agent.record_response(question, "[SKIPPED]")
            print("Question skipped.")
            continue

        if response.lower() == 'pause':
            filepath = agent.save_session()
            print(f"\nSession saved to: {filepath}")
            print("You can resume later with: --resume <session_id>")
            return

        if response.lower() == 'back':
            if agent.current_domain_progress.current_question_index > 0:
                agent.current_domain_progress.current_question_index -= 1
                agent.current_domain_progress.responses.pop()
                print("Going back to previous question...")
            else:
                print("Already at the first question of this domain.")
            continue

        if response.lower() == 'status':
            print(agent.get_status_display())
            continue

        if response.lower() == 'quit':
            save = input("Save progress before quitting? (y/n): ")
            if save.lower() == 'y':
                filepath = agent.save_session()
                print(f"Session saved to: {filepath}")
            return

        # Record the response
        agent.record_response(question, response)

        # Check for follow-up questions
        follow_ups = agent.should_ask_follow_up(question, response)
        if follow_ups:
            print("\nLet me ask a few follow-up questions...")
            for fu in follow_ups:
                fu_response = input(f"\n{fu}\nYour response: ").strip()
                if fu_response and fu_response.lower() not in ['skip', 'n/a']:
                    # Store follow-up response
                    agent.current_domain_progress.responses[-1].follow_up_responses[fu] = fu_response

    # Interview complete
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    INTERVIEW COMPLETE!                        ║
╚═══════════════════════════════════════════════════════════════╝

Thank you for completing the discovery interview!

""")
    print(agent.get_status_display())

    # Generate outputs
    session_file = agent.save_session()
    requirements_file = agent.generate_requirements_json()

    print(f"""
Generated Files:
  - Session data: {session_file}
  - Requirements JSON: {requirements_file}

The requirements.json file will be used by the Specification Agent
to generate your implementation specification document.
""")


def generate_llm_prompts(agent: InterviewAgent, output_dir: str):
    """Generate prompts for LLM-assisted interviews."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    prompts = []

    # Generate system prompt
    system_prompt = agent.SYSTEM_PROMPT

    # Generate prompts for each domain
    for domain_idx in range(get_total_domains()):
        agent.session.current_domain_index = domain_idx
        agent.session.domain_progress[agent.current_domain.domain.value].started = True

        domain = agent.current_domain
        domain_prompts = {
            "domain": domain.title,
            "domain_index": domain_idx + 1,
            "context": domain.odoo_context,
            "questions": []
        }

        for q_idx, question in enumerate(domain.questions):
            agent.current_domain_progress.current_question_index = q_idx
            prompt = create_interview_prompt(agent)
            domain_prompts["questions"].append({
                "question_id": question.id,
                "prompt": prompt
            })

        prompts.append(domain_prompts)

    # Save prompts
    import json
    prompts_file = output_path / f"interview_prompts_{agent.session.session_id}.json"
    with open(prompts_file, 'w') as f:
        json.dump({
            "system_prompt": system_prompt,
            "domain_prompts": prompts
        }, f, indent=2)

    print(f"Generated LLM prompts: {prompts_file}")
    return str(prompts_file)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Odoo ERP Implementation Interview Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a new interactive interview
  python -m src.cli --client "ACME Corp" --industry "Manufacturing"

  # Resume a previous session
  python -m src.cli --resume interview-20260205143000

  # Generate LLM prompts for Claude/GPT assisted interview
  python -m src.cli --client "ACME Corp" --industry "Manufacturing" --generate-prompts

  # Specify custom output directory
  python -m src.cli --client "ACME Corp" --industry "Manufacturing" --output ./my_outputs
        """
    )

    parser.add_argument(
        "--client", "-c",
        help="Client/company name"
    )

    parser.add_argument(
        "--industry", "-i",
        help="Client industry (e.g., Manufacturing, Retail, Services)"
    )

    parser.add_argument(
        "--resume", "-r",
        help="Resume a previous session by session ID"
    )

    parser.add_argument(
        "--output", "-o",
        default="./outputs",
        help="Output directory for generated files (default: ./outputs)"
    )

    parser.add_argument(
        "--generate-prompts", "-g",
        action="store_true",
        help="Generate prompts for LLM-assisted interview instead of interactive mode"
    )

    parser.add_argument(
        "--list-domains",
        action="store_true",
        help="List all interview domains and exit"
    )

    args = parser.parse_args()

    print_header()

    # List domains mode
    if args.list_domains:
        from .schemas.interview_domains import ALL_DOMAINS
        print("Interview Domains:\n")
        for i, domain in enumerate(ALL_DOMAINS, 1):
            print(f"  {i}. {domain.title}")
            print(f"     {domain.description}")
            print(f"     Questions: {len(domain.questions)}\n")
        return

    # Resume mode
    if args.resume:
        agent = InterviewAgent(
            client_name="",
            industry="",
            output_dir=args.output
        )
        if agent.load_session(args.resume):
            print(f"Resuming session: {args.resume}")
            run_interactive_interview(agent)
        else:
            print(f"Error: Session '{args.resume}' not found in {args.output}")
            sys.exit(1)
        return

    # New interview - require client and industry
    if not args.client or not args.industry:
        parser.print_help()
        print("\nError: --client and --industry are required for new interviews")
        sys.exit(1)

    # Create agent
    agent = InterviewAgent(
        client_name=args.client,
        industry=args.industry,
        output_dir=args.output
    )

    if args.generate_prompts:
        # Generate LLM prompts mode
        generate_llm_prompts(agent, args.output)
    else:
        # Interactive interview mode
        run_interactive_interview(agent)


if __name__ == "__main__":
    main()
