"""
Interview Agent for Odoo ERP Implementation

This agent conducts structured client discovery interviews to gather
requirements for Odoo implementation. It follows a domain-by-domain
approach with intelligent follow-up questions.

Usage:
    agent = InterviewAgent(client_name="ACME Corp", industry="Manufacturing")
    agent.run_interview()
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

from ..schemas.shared_context import (
    SharedContext,
    create_new_project,
    CompanyProfile,
    Requirement,
    Integration,
    UserRole,
    DataMigrationScope,
    ProjectPhase,
    AgentType
)
from ..schemas.interview_domains import (
    InterviewDomain,
    DomainDefinition,
    Question,
    ALL_DOMAINS,
    get_domain,
    get_domain_by_index,
    get_total_domains
)


class InterviewState(str, Enum):
    """Current state of the interview."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class QuestionResponse:
    """A response to a single question."""
    question_id: str
    question_text: str
    response: str
    follow_up_responses: dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    extracted_requirements: list[str] = field(default_factory=list)


@dataclass
class DomainProgress:
    """Progress tracking for a single domain."""
    domain: InterviewDomain
    started: bool = False
    completed: bool = False
    current_question_index: int = 0
    responses: list[QuestionResponse] = field(default_factory=list)
    notes: str = ""


@dataclass
class InterviewSession:
    """Complete interview session state."""
    session_id: str
    client_name: str
    industry: str
    state: InterviewState = InterviewState.NOT_STARTED
    current_domain_index: int = 0
    domain_progress: dict[str, DomainProgress] = field(default_factory=dict)
    started_at: str = ""
    last_updated: str = ""
    completed_at: str = ""

    def __post_init__(self):
        # Initialize progress for all domains
        if not self.domain_progress:
            for domain_def in ALL_DOMAINS:
                self.domain_progress[domain_def.domain.value] = DomainProgress(
                    domain=domain_def.domain
                )


class InterviewAgent:
    """
    Senior Odoo Business Analyst agent that conducts client discovery interviews.

    The agent:
    - Asks one focused question at a time
    - Uses follow-up questions for vague answers
    - Suggests Odoo capabilities to guide discussion
    - Confirms understanding before moving forward
    - Flags critical requirements for Technical Architect review
    """

    SYSTEM_PROMPT = """You are a Senior Odoo Business Analyst conducting client discovery
for a first-time Odoo implementation. Your goal is to extract complete requirements
for Odoo configuration.

INTERVIEW STYLE:
- Ask ONE focused question at a time
- Use follow-up questions for vague answers
- Suggest Odoo capabilities to guide discussion
- Confirm understanding before moving forward
- Flag critical requirements for Technical Architect review

Always be professional, patient, and thorough. Explain Odoo terminology when needed."""

    def __init__(
        self,
        client_name: str,
        industry: str,
        output_dir: str = "./outputs"
    ):
        self.client_name = client_name
        self.industry = industry
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize session
        self.session = InterviewSession(
            session_id=f"interview-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            client_name=client_name,
            industry=industry
        )

        # Initialize shared context
        self.context = create_new_project(client_name, industry)
        self.context.interview_output.company_profile.name = client_name
        self.context.interview_output.company_profile.industry = industry

    @property
    def current_domain(self) -> DomainDefinition:
        """Get the current domain being interviewed."""
        return get_domain_by_index(self.session.current_domain_index)

    @property
    def current_domain_progress(self) -> DomainProgress:
        """Get progress for current domain."""
        return self.session.domain_progress[self.current_domain.domain.value]

    @property
    def progress_percentage(self) -> int:
        """Calculate overall interview progress."""
        total_domains = get_total_domains()
        completed = sum(
            1 for p in self.session.domain_progress.values()
            if p.completed
        )
        return int((completed / total_domains) * 100)

    def get_interview_context(self) -> str:
        """Build context string for LLM prompt."""
        domain = self.current_domain
        progress = self.current_domain_progress

        # Gather responses so far for this domain
        responses_text = ""
        if progress.responses:
            responses_text = "\n".join([
                f"Q: {r.question_text}\nA: {r.response}"
                for r in progress.responses
            ])

        return f"""
ROLE: Senior Odoo Business Analyst
CLIENT: {self.client_name} - {self.industry} company
OBJECTIVE: Complete requirements gathering for Odoo implementation

INTERVIEW_STAGE: {domain.title} ({self.session.current_domain_index + 1}/{get_total_domains()})

DOMAIN CONTEXT:
{domain.description}

ODOO CAPABILITIES IN THIS AREA:
{domain.odoo_context}

GATHERED SO FAR IN THIS DOMAIN:
{responses_text if responses_text else "No responses yet"}

INTERVIEW STYLE:
- Ask ONE focused question at a time
- Probe for specifics when answers are vague
- Suggest Odoo capabilities when gaps identified
- Confirm understanding before moving forward
"""

    def get_next_question(self) -> Optional[Question]:
        """Get the next question to ask in the current domain."""
        domain = self.current_domain
        progress = self.current_domain_progress

        if progress.current_question_index >= len(domain.questions):
            return None

        return domain.questions[progress.current_question_index]

    def format_question_prompt(self, question: Question) -> str:
        """Format a question for display with context."""
        prompt = f"\n{'='*60}\n"
        prompt += f"Domain: {self.current_domain.title} "
        prompt += f"(Question {self.current_domain_progress.current_question_index + 1}/"
        prompt += f"{len(self.current_domain.questions)})\n"
        prompt += f"{'='*60}\n\n"

        if question.context:
            prompt += f"[Context: {question.context}]\n\n"

        prompt += f"{question.text}\n"

        return prompt

    def record_response(self, question: Question, response: str) -> QuestionResponse:
        """Record a response to a question."""
        qr = QuestionResponse(
            question_id=question.id,
            question_text=question.text,
            response=response,
            timestamp=datetime.now().isoformat(),
            extracted_requirements=question.extracts
        )

        self.current_domain_progress.responses.append(qr)
        self.current_domain_progress.current_question_index += 1

        # Update last_updated timestamp
        self.session.last_updated = datetime.now().isoformat()

        return qr

    def should_ask_follow_up(self, question: Question, response: str) -> list[str]:
        """Determine if follow-up questions should be asked."""
        # Simple heuristic: if response is short or vague, ask follow-ups
        vague_indicators = [
            "maybe", "i think", "not sure", "depends",
            "sometimes", "it varies", "kind of"
        ]

        response_lower = response.lower()
        is_short = len(response.split()) < 10
        is_vague = any(v in response_lower for v in vague_indicators)

        if (is_short or is_vague) and question.follow_ups:
            return question.follow_ups

        return []

    def complete_current_domain(self):
        """Mark current domain as complete and move to next."""
        self.current_domain_progress.completed = True

        if self.session.current_domain_index < get_total_domains() - 1:
            self.session.current_domain_index += 1
            # Mark next domain as started
            next_domain = self.current_domain
            self.session.domain_progress[next_domain.domain.value].started = True
        else:
            # Interview complete
            self.session.state = InterviewState.COMPLETED
            self.session.completed_at = datetime.now().isoformat()

    def extract_requirements_from_responses(self) -> None:
        """Extract structured requirements from all responses."""
        # This would typically use an LLM to extract structured data
        # For now, we'll provide a framework for manual/LLM extraction

        for domain_key, progress in self.session.domain_progress.items():
            domain = InterviewDomain(domain_key)

            for response in progress.responses:
                # Create a requirement object from the response
                if response.response.strip():
                    req = Requirement(
                        id=response.question_id,
                        domain=domain_key,
                        description=response.response,
                        notes=f"Extracted from: {response.question_text}"
                    )

                    # Add to appropriate domain in interview output
                    if domain_key in self.context.interview_output.requirements_by_domain:
                        self.context.interview_output.requirements_by_domain[domain_key].append(req)

    def start_interview(self) -> str:
        """Start the interview session."""
        self.session.state = InterviewState.IN_PROGRESS
        self.session.started_at = datetime.now().isoformat()

        # Mark first domain as started
        first_domain = ALL_DOMAINS[0]
        self.session.domain_progress[first_domain.domain.value].started = True

        welcome = f"""
╔══════════════════════════════════════════════════════════════╗
║           ODOO IMPLEMENTATION DISCOVERY INTERVIEW            ║
╠══════════════════════════════════════════════════════════════╣
║  Client: {self.client_name:<50} ║
║  Industry: {self.industry:<48} ║
║  Session: {self.session.session_id:<49} ║
╚══════════════════════════════════════════════════════════════╝

Welcome! I'm your Odoo Business Analyst. I'll be guiding you through
a comprehensive discovery interview to understand your business needs
and how Odoo can best serve your organization.

We'll cover {get_total_domains()} key areas:
"""
        for i, domain in enumerate(ALL_DOMAINS, 1):
            welcome += f"  {i}. {domain.title}\n"

        welcome += f"""
Let's begin with understanding your company basics.
Type 'skip' to skip a question, 'back' to go back, or 'pause' to save progress.
"""
        return welcome

    def get_status_display(self) -> str:
        """Get a status display of interview progress."""
        status = f"\n{'─'*60}\n"
        status += f"Progress: {self.progress_percentage}% complete\n"
        status += f"{'─'*60}\n"

        for i, domain in enumerate(ALL_DOMAINS):
            progress = self.session.domain_progress[domain.domain.value]
            if progress.completed:
                icon = "✓"
            elif progress.started:
                icon = "→"
            else:
                icon = "○"
            status += f"  {icon} {domain.title}\n"

        status += f"{'─'*60}\n"
        return status

    def save_session(self) -> str:
        """Save the current session to a JSON file."""
        filepath = self.output_dir / f"{self.session.session_id}.json"

        # Convert session to dict for JSON serialization
        session_data = {
            "session": asdict(self.session),
            "context": self.context.to_dict()
        }

        with open(filepath, 'w') as f:
            json.dump(session_data, f, indent=2, default=str)

        return str(filepath)

    def load_session(self, session_id: str) -> bool:
        """Load a previous session from JSON file."""
        filepath = self.output_dir / f"{session_id}.json"

        if not filepath.exists():
            return False

        with open(filepath, 'r') as f:
            data = json.load(f)

        # Reconstruct session - simplified, would need full deserialization
        self.session.session_id = data["session"]["session_id"]
        self.session.state = InterviewState(data["session"]["state"])
        self.session.current_domain_index = data["session"]["current_domain_index"]

        return True

    def generate_requirements_json(self) -> str:
        """Generate the requirements.json output for the Specification Agent."""
        self.extract_requirements_from_responses()

        output = {
            "project_id": self.context.project_id,
            "client_name": self.client_name,
            "industry": self.industry,
            "interview_completed": self.session.completed_at,
            "company_profile": asdict(self.context.interview_output.company_profile),
            "requirements_by_domain": {
                domain: [asdict(r) for r in reqs]
                for domain, reqs in self.context.interview_output.requirements_by_domain.items()
            },
            "integrations_needed": [
                asdict(i) for i in self.context.interview_output.integrations_needed
            ],
            "users_and_roles": [
                asdict(u) for u in self.context.interview_output.users_and_roles
            ],
            "data_migration_scope": asdict(self.context.interview_output.data_migration_scope),
            "current_systems": self.context.interview_output.current_systems,
            "pain_points": self.context.interview_output.pain_points,
            "success_criteria": self.context.interview_output.success_criteria,
            "raw_responses": {
                domain: [asdict(r) for r in progress.responses]
                for domain, progress in self.session.domain_progress.items()
            }
        }

        filepath = self.output_dir / f"requirements-{self.session.session_id}.json"
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        return str(filepath)


def create_interview_prompt(agent: InterviewAgent) -> str:
    """
    Create a complete prompt for an LLM to conduct the interview.

    This prompt can be used with Claude or other LLMs to run
    the interview in a conversational manner.
    """
    context = agent.get_interview_context()
    question = agent.get_next_question()

    if not question:
        return f"""
{context}

All questions for this domain have been covered.

Please provide a brief summary of what you've learned about the client's
{agent.current_domain.title} requirements, then confirm with the client
if there's anything else they'd like to add before moving to the next domain.
"""

    return f"""
{context}

NEXT QUESTION TO ASK:
{question.text}

{f"Context for why we ask this: {question.context}" if question.context else ""}

{f"Potential follow-ups if answer is vague: {', '.join(question.follow_ups)}" if question.follow_ups else ""}

Ask this question naturally, adapting the wording if needed based on
the conversation flow. If the client's answer is vague or incomplete,
use the follow-up questions to probe deeper.
"""
