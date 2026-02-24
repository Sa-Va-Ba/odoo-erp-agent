"""
Smart Interview Agent - Enhanced Interview Agent with LLM and Branching Logic

This is an enhanced version of the Interview Agent that:
- Uses LLM (Groq/Ollama) for natural conversation
- Applies intelligent branching based on responses
- Adapts questions based on context
- Extracts structured requirements automatically
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from .interview_agent import (
    InterviewAgent,
    InterviewState,
    QuestionResponse,
    DomainProgress,
    InterviewSession
)
from ..schemas.shared_context import (
    SharedContext,
    create_new_project,
    Requirement,
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
from ..llm.base import Message
from ..llm.manager import LLMManager, get_llm_manager
from ..branching.analyzer import ResponseAnalyzer, ResponseQuality, ResponseAnalysis, ExtractedInfo
from ..branching.engine import BranchingEngine, NextAction, ActionType
from ..branching.triggers import load_domain_triggers


@dataclass
class EnhancedQuestionResponse(QuestionResponse):
    """Extended response with analysis data."""
    analysis: Optional[ResponseAnalysis] = None
    llm_enhanced: bool = False
    triggered_rules: List[str] = field(default_factory=list)


class SmartInterviewAgent(InterviewAgent):
    """
    Enhanced Interview Agent with LLM integration and intelligent branching.

    Features:
    - LLM-powered natural conversation (Groq or Ollama)
    - Response quality analysis
    - Domain-specific trigger rules
    - Adaptive question flow
    - Automatic requirement extraction
    """

    def __init__(
        self,
        client_name: str,
        industry: str,
        output_dir: str = "./outputs",
        use_llm: bool = True,
        llm_manager: Optional[LLMManager] = None
    ):
        """
        Initialize the Smart Interview Agent.

        Args:
            client_name: Name of the client company
            industry: Client's industry
            output_dir: Directory for output files
            use_llm: Whether to use LLM for enhanced conversation
            llm_manager: Optional pre-configured LLM manager
        """
        super().__init__(client_name, industry, output_dir)

        # LLM setup
        self.use_llm = use_llm
        self.llm_manager = llm_manager

        if use_llm and not llm_manager:
            try:
                self.llm_manager = get_llm_manager()
                print(f"LLM Status: {self.llm_manager.get_status()}")
            except Exception as e:
                print(f"Warning: LLM initialization failed: {e}")
                print("Falling back to non-LLM mode")
                self.use_llm = False

        # Branching engine setup
        self.analyzer = ResponseAnalyzer(
            use_llm=use_llm and self.llm_manager is not None,
            llm_manager=self.llm_manager
        )
        self.branching_engine = BranchingEngine(
            analyzer=self.analyzer,
            llm_manager=self.llm_manager
        )

        # Conversation history for LLM
        self.conversation_history: List[Message] = []

        # Current pending action (if any)
        self._pending_action: Optional[NextAction] = None

    def _init_conversation(self):
        """Initialize conversation history with system prompt."""
        system_message = f"""You are a Senior Odoo Business Analyst conducting a discovery interview
for {self.client_name}, a {self.industry} company.

Your goal is to understand their business requirements for an Odoo ERP implementation.

Interview Guidelines:
- Ask ONE focused question at a time
- When answers are vague, probe for specific examples
- Suggest relevant Odoo capabilities when appropriate
- Confirm your understanding before moving on
- Be professional, patient, and thorough

Current Progress: Domain {self.session.current_domain_index + 1}/{get_total_domains()} - {self.current_domain.title}

Odoo can help with: {self.current_domain.odoo_context}"""

        self.conversation_history = [
            Message(role="system", content=system_message)
        ]

    def get_llm_enhanced_question(self, base_question: Question) -> str:
        """
        Use LLM to generate a more natural, context-aware question.

        Args:
            base_question: The base question to enhance

        Returns:
            Enhanced question text
        """
        if not self.use_llm or not self.llm_manager:
            return base_question.text

        # Build context from previous responses
        context_parts = []
        for resp in self.current_domain_progress.responses[-3:]:  # Last 3 responses
            context_parts.append(f"Q: {resp.question_text}\nA: {resp.response}")

        context = "\n".join(context_parts) if context_parts else "No previous responses yet."

        prompt = f"""Based on our conversation so far:

{context}

The next topic to cover is: {base_question.text}

Context for this question: {base_question.context or 'General information gathering'}

Please rephrase this question naturally, considering the conversation flow.
Keep it concise (1-2 sentences). Don't repeat information already gathered.
Just output the question, nothing else."""

        try:
            response = self.llm_manager.complete(prompt, max_tokens=200)
            enhanced = response.content.strip()

            # Validate it's actually a question
            if "?" in enhanced and len(enhanced) < 300:
                return enhanced
            return base_question.text

        except Exception as e:
            print(f"LLM enhancement failed: {e}")
            return base_question.text

    def process_response_with_branching(
        self,
        response: str,
        question: Question
    ) -> Tuple[EnhancedQuestionResponse, NextAction]:
        """
        Process a response with full branching logic.

        Args:
            response: User's response text
            question: The question that was asked

        Returns:
            Tuple of (EnhancedQuestionResponse, NextAction)
        """
        # Map domain enum to trigger key
        domain_key = self._get_trigger_domain_key()

        # Set domain in branching engine
        self.branching_engine.set_domain(domain_key)

        # Process through branching engine
        analysis, next_action = self.branching_engine.process_response(
            response=response,
            question_text=question.text,
            question_id=question.id,
            domain=domain_key
        )

        # If we have a strong enough response, mark required info as gathered
        if analysis.quality in [ResponseQuality.COMPLETE, ResponseQuality.NEGATIVE]:
            existing_keys = {info.key for info in analysis.extracted_info}
            for key in question.extracts:
                self.branching_engine.state.mark_info_gathered(domain_key, key)
                if key in existing_keys:
                    continue
                analysis.extracted_info.append(
                    ExtractedInfo(
                        key=key,
                        value=response.strip(),
                        confidence=0.6 if analysis.quality == ResponseQuality.NEGATIVE else 0.85,
                        source_text=response.strip()
                    )
                )
                existing_keys.add(key)

        # Create enhanced response record
        enhanced_response = EnhancedQuestionResponse(
            question_id=question.id,
            question_text=question.text,
            response=response,
            timestamp=datetime.now().isoformat(),
            extracted_requirements=question.extracts,
            analysis=analysis,
            llm_enhanced=self.use_llm
        )

        # Record the response
        self.current_domain_progress.responses.append(enhanced_response)
        self.session.last_updated = datetime.now().isoformat()

        # Handle skip questions
        if next_action.skip_question_ids:
            for q_id in next_action.skip_question_ids:
                # Mark questions to skip in domain progress
                pass  # Handled by branching engine state

        return enhanced_response, next_action

    def _get_trigger_domain_key(self) -> str:
        """Map current domain to trigger domain key."""
        domain_mapping = {
            InterviewDomain.COMPANY_BASICS: "company_basics",
            InterviewDomain.CURRENT_SYSTEMS: "current_systems",
            InterviewDomain.FINANCE_ACCOUNTING: "finance_accounting",
            InterviewDomain.SALES_CRM: "sales_crm",
            InterviewDomain.INVENTORY_OPERATIONS: "inventory_operations",
            InterviewDomain.HR_PAYROLL: "hr_payroll",
            InterviewDomain.PROJECT_MANAGEMENT: "project_management",
            InterviewDomain.INTEGRATIONS: "integrations",
            InterviewDomain.USERS_PERMISSIONS: "users_permissions",
            InterviewDomain.DATA_MIGRATION: "data_migration",
        }
        return domain_mapping.get(self.current_domain.domain, "company_basics")

    def get_next_question_smart(self) -> Tuple[Optional[str], Optional[Question]]:
        """
        Get the next question using smart branching logic.

        Returns:
            Tuple of (question_text, base_question) or (None, None) if domain complete
        """
        # Check for pending follow-up action
        if self._pending_action and self._pending_action.action_type in [
            ActionType.ASK_FOLLOW_UP,
            ActionType.PROBE_DEEPER
        ]:
            action = self._pending_action
            self._pending_action = None
            return (action.question_text, None)

        # Get base question
        domain = self.current_domain
        progress = self.current_domain_progress

        # Find next non-skipped question
        while progress.current_question_index < len(domain.questions):
            question = domain.questions[progress.current_question_index]

            # Check if should skip
            if self.branching_engine.should_skip_question(question.id):
                progress.current_question_index += 1
                continue

            # Found a question to ask
            if self.use_llm:
                enhanced_text = self.get_llm_enhanced_question(question)
                return (enhanced_text, question)
            else:
                return (question.text, question)

        # No more questions in this domain
        return (None, None)

    def handle_response(self, response: str, question: Question) -> NextAction:
        """
        Handle a user response and determine next action.

        Args:
            response: User's response
            question: The question that was asked

        Returns:
            NextAction indicating what to do next
        """
        # Process with branching
        enhanced_response, next_action = self.process_response_with_branching(
            response, question
        )

        # Prefer domain-specific follow-ups from the question itself when response is weak
        if enhanced_response.analysis and question.follow_ups:
            next_action = self._maybe_use_question_followups(
                question=question,
                analysis=enhanced_response.analysis,
                next_action=next_action
            )

        # Only advance when we are not in a follow-up flow
        if next_action.action_type not in [ActionType.ASK_FOLLOW_UP, ActionType.PROBE_DEEPER]:
            self.current_domain_progress.current_question_index += 1

        return next_action

    def generate_domain_summary(self) -> str:
        """Generate a summary of the current domain using LLM."""
        if not self.use_llm or not self.llm_manager:
            return self._generate_simple_summary()

        responses_text = "\n".join([
            f"Q: {r.question_text}\nA: {r.response}"
            for r in self.current_domain_progress.responses
        ])

        prompt = f"""Summarize the key requirements gathered for {self.current_domain.title}:

{responses_text}

Provide a concise summary (3-5 bullet points) of:
1. Main requirements identified
2. Any pain points mentioned
3. Relevant Odoo modules that would help

Be concise and factual."""

        try:
            response = self.llm_manager.complete(prompt, max_tokens=500)
            return response.content
        except Exception:
            return self._generate_simple_summary()

    def _generate_simple_summary(self) -> str:
        """Generate a simple non-LLM summary."""
        summary = f"\n📋 {self.current_domain.title} - Summary\n"
        summary += "─" * 40 + "\n"

        for resp in self.current_domain_progress.responses:
            if resp.response and resp.response != "[SKIPPED]":
                # Truncate long responses
                response_preview = resp.response[:100]
                if len(resp.response) > 100:
                    response_preview += "..."
                summary += f"• {response_preview}\n"

        # Add branching engine insights
        engine_summary = self.branching_engine.get_domain_summary(
            self._get_trigger_domain_key()
        )

        if engine_summary.get("architect_flags"):
            summary += "\n⚠️ Flags for Technical Architect:\n"
            for flag in engine_summary["architect_flags"]:
                summary += f"  - {flag['flag']}\n"

        return summary

    def _maybe_use_question_followups(
        self,
        question: Question,
        analysis: ResponseAnalysis,
        next_action: NextAction
    ) -> NextAction:
        """Prefer explicit follow-ups defined on the question when answers are weak."""
        if analysis.quality not in [ResponseQuality.VAGUE, ResponseQuality.PARTIAL]:
            return next_action

        # Avoid overriding trigger-based follow-ups
        if next_action.reason.lower().startswith("triggered") or "flagged" in next_action.reason.lower():
            return next_action

        follow_ups = [fu for fu in question.follow_ups if fu and fu.strip()]
        if not follow_ups:
            return next_action

        # Use first follow-up immediately, queue the rest
        next_action.question_text = follow_ups[0]
        for extra in follow_ups[1:]:
            self.branching_engine.state.add_follow_up(extra, priority=6, reason="Question follow-up")

        return next_action

    def record_follow_up_response(self, follow_up_question: str, follow_up_response: str):
        """Record a follow-up response and advance to the next base question."""
        if self.current_domain_progress.responses:
            last_response = self.current_domain_progress.responses[-1]
            last_response.follow_up_responses[follow_up_question] = follow_up_response

            # Mark required info gathered based on the original question extracts
            domain_key = self._get_trigger_domain_key()
            combined_text = f"{last_response.response}\nFollow-up: {follow_up_response}".strip()

            if last_response.analysis and last_response.extracted_requirements:
                existing_keys = {info.key for info in last_response.analysis.extracted_info}
                for key in last_response.extracted_requirements:
                    self.branching_engine.state.mark_info_gathered(domain_key, key)
                    if key not in existing_keys:
                        last_response.analysis.extracted_info.append(
                            ExtractedInfo(
                                key=key,
                                value=combined_text,
                                confidence=0.8 if follow_up_response else 0.6,
                                source_text=combined_text
                            )
                        )

            self.session.last_updated = datetime.now().isoformat()

        # Advance after follow-up so we don't get stuck
        self.current_domain_progress.current_question_index += 1
        self._pending_action = None

    def extract_requirements_smart(self) -> dict:
        """Extract structured requirements using LLM-enhanced analysis."""
        requirements = {
            "by_domain": {},
            "pain_points": self.branching_engine.state.pain_points,
            "systems_mentioned": self.branching_engine.state.mentioned_systems,
            "architect_flags": self.branching_engine.state.architect_flags,
            "skipped_questions": list(self.branching_engine.state.skip_questions)
        }

        for domain_key, progress in self.session.domain_progress.items():
            domain_reqs = []

            for resp in progress.responses:
                if isinstance(resp, EnhancedQuestionResponse) and resp.analysis:
                    # Use analyzed data
                    for info in resp.analysis.extracted_info:
                        domain_reqs.append({
                            "key": info.key,
                            "value": info.value,
                            "confidence": info.confidence,
                            "source": resp.question_text
                        })

                    # Add detected pain points
                    for pain_point in resp.analysis.detected_pain_points:
                        if pain_point not in requirements["pain_points"]:
                            requirements["pain_points"].append(pain_point)

                elif resp.response and resp.response != "[SKIPPED]":
                    # Fallback for non-enhanced responses
                    domain_reqs.append({
                        "key": resp.question_id,
                        "value": resp.response,
                        "confidence": 0.8,
                        "source": resp.question_text
                    })

            requirements["by_domain"][domain_key] = domain_reqs

        return requirements

    def generate_requirements_json(self) -> str:
        """Generate enhanced requirements.json with smart extraction."""
        smart_requirements = self.extract_requirements_smart()

        output = {
            "project_id": self.context.project_id,
            "client_name": self.client_name,
            "industry": self.industry,
            "interview_completed": self.session.completed_at,
            "llm_enhanced": self.use_llm,
            "company_profile": asdict(self.context.interview_output.company_profile),

            # Smart extracted requirements
            "requirements": smart_requirements["by_domain"],
            "pain_points": smart_requirements["pain_points"],
            "systems_mentioned": smart_requirements["systems_mentioned"],
            "technical_architect_flags": smart_requirements["architect_flags"],

            # Interview summary from branching engine
            "interview_summary": self.branching_engine.get_interview_summary(),

            # Raw responses for reference
            "raw_responses": {
                domain: [
                    {
                        "question_id": r.question_id,
                        "question": r.question_text,
                        "response": r.response,
                        "timestamp": r.timestamp,
                        "quality": r.analysis.quality.value if isinstance(r, EnhancedQuestionResponse) and r.analysis else "unknown"
                    }
                    for r in progress.responses
                ]
                for domain, progress in self.session.domain_progress.items()
            }
        }

        filepath = self.output_dir / f"requirements-{self.session.session_id}.json"
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        return str(filepath)

    def start_interview(self) -> str:
        """Start the interview session with LLM initialization."""
        # Initialize conversation for LLM
        if self.use_llm:
            self._init_conversation()

        # Reset branching engine state
        self.branching_engine.reset_state()

        # Call parent start
        welcome = super().start_interview()

        # Add LLM status to welcome
        if self.use_llm and self.llm_manager:
            status = self.llm_manager.get_status()
            provider = status.get("current_provider", "none")
            welcome += f"\n🤖 AI Assistant: Active (using {provider})\n"
        else:
            welcome += "\n🤖 AI Assistant: Offline (rule-based mode)\n"

        return welcome


def create_smart_agent(
    client_name: str,
    industry: str,
    use_llm: bool = True
) -> SmartInterviewAgent:
    """
    Factory function to create a Smart Interview Agent.

    Args:
        client_name: Client company name
        industry: Client's industry
        use_llm: Whether to enable LLM features

    Returns:
        Configured SmartInterviewAgent
    """
    return SmartInterviewAgent(
        client_name=client_name,
        industry=industry,
        use_llm=use_llm
    )
