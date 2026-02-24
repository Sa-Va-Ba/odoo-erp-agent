"""
Branching Engine - Core decision-making logic for interview flow.

This engine determines what to do next based on:
- Response analysis results
- Domain-specific triggers
- Conversation state
- Required information tracking
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from collections import deque

from .analyzer import ResponseAnalyzer, ResponseQuality, ResponseAnalysis
from .triggers import (
    TriggerRule,
    TriggerAction,
    DomainTriggers,
    load_domain_triggers,
    ALL_DOMAIN_TRIGGERS
)


class ActionType(str, Enum):
    """Type of action the engine recommends."""
    NEXT_QUESTION = "next_question"          # Move to next question
    ASK_FOLLOW_UP = "ask_follow_up"          # Ask a follow-up question
    PROBE_DEEPER = "probe_deeper"            # Ask for more detail
    CONFIRM_UNDERSTANDING = "confirm"         # Confirm what we understood
    COMPLETE_DOMAIN = "complete_domain"       # Domain is complete, move on
    SKIP_QUESTION = "skip_question"          # Skip current/future question
    FLAG_FOR_REVIEW = "flag_for_review"      # Flag and continue


@dataclass
class NextAction:
    """Recommended next action from the branching engine."""
    action_type: ActionType
    question_text: str = ""                  # Question to ask (if applicable)
    question_id: str = ""                    # Question ID
    reason: str = ""                         # Why this action
    priority: int = 5                        # Priority (1=highest)
    flags: List[str] = field(default_factory=list)  # Flags for architect
    skip_question_ids: List[str] = field(default_factory=list)  # Questions to skip
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationState:
    """Current state of the interview conversation."""
    # Current position
    current_domain: str = ""
    current_question_index: int = 0

    # Gathered information
    gathered_info: Dict[str, Any] = field(default_factory=dict)

    # Mentioned systems (for cross-referencing)
    mentioned_systems: List[str] = field(default_factory=list)

    # Pain points identified
    pain_points: List[str] = field(default_factory=list)

    # Questions to skip
    skip_questions: set = field(default_factory=set)

    # Flags for Technical Architect
    architect_flags: List[Dict[str, str]] = field(default_factory=list)

    # Pending follow-up queue (priority queue)
    pending_follow_ups: deque = field(default_factory=deque)

    # Domain completion tracking
    domain_completion: Dict[str, Dict[str, bool]] = field(default_factory=dict)

    def add_follow_up(self, question: str, priority: int = 5, reason: str = ""):
        """Add a follow-up question to the queue."""
        self.pending_follow_ups.append({
            "question": question,
            "priority": priority,
            "reason": reason
        })
        # Sort by priority
        self.pending_follow_ups = deque(
            sorted(self.pending_follow_ups, key=lambda x: x["priority"])
        )

    def pop_follow_up(self) -> Optional[Dict]:
        """Get the highest priority follow-up."""
        if self.pending_follow_ups:
            return self.pending_follow_ups.popleft()
        return None

    def has_follow_ups(self) -> bool:
        """Check if there are pending follow-ups."""
        return len(self.pending_follow_ups) > 0

    def add_flag(self, flag: str, domain: str, context: str = ""):
        """Add a flag for Technical Architect review."""
        self.architect_flags.append({
            "flag": flag,
            "domain": domain,
            "context": context
        })

    def mark_info_gathered(self, domain: str, info_key: str):
        """Mark that specific information has been gathered for a domain."""
        if domain not in self.domain_completion:
            self.domain_completion[domain] = {}
        self.domain_completion[domain][info_key] = True

    def is_info_gathered(self, domain: str, info_key: str) -> bool:
        """Check if specific information has been gathered."""
        return self.domain_completion.get(domain, {}).get(info_key, False)


class BranchingEngine:
    """
    Main branching engine that determines interview flow.

    The engine:
    1. Analyzes responses for quality and content
    2. Checks domain-specific triggers
    3. Tracks required information
    4. Decides what to ask next
    """

    def __init__(
        self,
        analyzer: Optional[ResponseAnalyzer] = None,
        llm_manager=None
    ):
        """
        Initialize the branching engine.

        Args:
            analyzer: Response analyzer instance
            llm_manager: LLM manager for enhanced analysis
        """
        self.analyzer = analyzer or ResponseAnalyzer()
        self.llm_manager = llm_manager
        self.state = ConversationState()

    def reset_state(self):
        """Reset conversation state for a new interview."""
        self.state = ConversationState()

    def set_domain(self, domain: str):
        """Set the current domain being interviewed."""
        self.state.current_domain = domain
        self.state.current_question_index = 0

    def process_response(
        self,
        response: str,
        question_text: str,
        question_id: str,
        domain: str
    ) -> Tuple[ResponseAnalysis, NextAction]:
        """
        Process a user response and determine next action.

        Args:
            response: User's response text
            question_text: The question that was asked
            question_id: ID of the question
            domain: Current interview domain

        Returns:
            Tuple of (ResponseAnalysis, NextAction)
        """
        # Analyze the response
        analysis = self.analyzer.analyze(
            response=response,
            question_text=question_text,
            domain=domain,
            context={
                "gathered_info": self.state.gathered_info,
                "mentioned_systems": self.state.mentioned_systems
            }
        )

        # Update state with extracted information
        self._update_state_from_analysis(analysis, domain)

        # Check for triggered rules
        triggered_actions = self._check_triggers(response, domain, analysis)

        # Determine next action
        next_action = self._determine_next_action(
            analysis=analysis,
            triggered_actions=triggered_actions,
            question_id=question_id,
            domain=domain
        )

        return analysis, next_action

    def _update_state_from_analysis(self, analysis: ResponseAnalysis, domain: str):
        """Update conversation state from analysis results."""
        # Add detected systems
        for system in analysis.detected_systems:
            if system not in self.state.mentioned_systems:
                self.state.mentioned_systems.append(system)

        # Add pain points
        for pain_point in analysis.detected_pain_points:
            if pain_point not in self.state.pain_points:
                self.state.pain_points.append(pain_point)

        # Mark extracted info as gathered
        for info in analysis.extracted_info:
            self.state.mark_info_gathered(domain, info.key)

        # Update skip list
        for q_id in analysis.skip_future_questions:
            self.state.skip_questions.add(q_id)

    def _check_triggers(
        self,
        response: str,
        domain: str,
        analysis: ResponseAnalysis
    ) -> List[Tuple[TriggerRule, str]]:
        """
        Check all triggers for the current domain.

        Returns:
            List of (triggered_rule, matched_text) tuples
        """
        triggered = []
        response_lower = response.lower()

        # Load domain triggers
        domain_triggers = load_domain_triggers(domain)
        if not domain_triggers:
            return triggered

        for trigger in domain_triggers.triggers:
            if trigger.trigger_type == "keyword":
                # Check keyword pattern
                match = re.search(trigger.trigger_value, response_lower, re.IGNORECASE)
                if match:
                    triggered.append((trigger, match.group()))

            elif trigger.trigger_type == "missing":
                # Check if required info is missing
                if not self.state.is_info_gathered(domain, trigger.trigger_value):
                    triggered.append((trigger, trigger.trigger_value))

            elif trigger.trigger_type == "pattern":
                # Custom pattern matching
                match = re.search(trigger.trigger_value, response, re.IGNORECASE)
                if match:
                    triggered.append((trigger, match.group()))

        # Sort by priority
        triggered.sort(key=lambda x: x[0].priority)

        return triggered

    def _determine_next_action(
        self,
        analysis: ResponseAnalysis,
        triggered_actions: List[Tuple[TriggerRule, str]],
        question_id: str,
        domain: str
    ) -> NextAction:
        """Determine the next action based on analysis and triggers."""

        # Priority 1: Check for pending follow-ups from previous responses
        if self.state.has_follow_ups():
            follow_up = self.state.pop_follow_up()
            return NextAction(
                action_type=ActionType.ASK_FOLLOW_UP,
                question_text=follow_up["question"],
                reason=follow_up.get("reason", "Pending follow-up"),
                priority=follow_up.get("priority", 5)
            )

        # Priority 2: Handle skip signal
        if analysis.quality == ResponseQuality.SKIP_SIGNAL:
            return NextAction(
                action_type=ActionType.NEXT_QUESTION,
                reason="User requested to skip"
            )

        # Priority 3: Process high-priority triggers
        for trigger, matched_text in triggered_actions:
            if trigger.priority <= 2:  # High priority triggers

                if trigger.action == TriggerAction.ASK_FOLLOW_UP:
                    return NextAction(
                        action_type=ActionType.ASK_FOLLOW_UP,
                        question_text=trigger.follow_up_question,
                        reason=f"Triggered by: '{matched_text}'",
                        priority=trigger.priority
                    )

                elif trigger.action == TriggerAction.FLAG_FOR_REVIEW:
                    self.state.add_flag(
                        flag=trigger.description or trigger.follow_up_question,
                        domain=domain,
                        context=matched_text
                    )
                    if trigger.follow_up_question:
                        return NextAction(
                            action_type=ActionType.ASK_FOLLOW_UP,
                            question_text=trigger.follow_up_question,
                            reason=f"Flagged for review: {trigger.description}",
                            priority=trigger.priority,
                            flags=[trigger.description]
                        )

                elif trigger.action == TriggerAction.SKIP_QUESTIONS:
                    for q_id in trigger.target_questions:
                        self.state.skip_questions.add(q_id)
                    return NextAction(
                        action_type=ActionType.NEXT_QUESTION,
                        reason=f"Skipping questions: {trigger.target_questions}",
                        skip_question_ids=trigger.target_questions
                    )

        # Priority 4: Handle response quality issues
        if analysis.quality == ResponseQuality.VAGUE:
            if analysis.suggested_follow_ups:
                return NextAction(
                    action_type=ActionType.PROBE_DEEPER,
                    question_text=analysis.suggested_follow_ups[0],
                    reason="Response was vague, probing for clarity"
                )
            return NextAction(
                action_type=ActionType.PROBE_DEEPER,
                question_text="Could you be more specific? A concrete example would help.",
                reason="Response was vague"
            )

        if analysis.quality == ResponseQuality.PARTIAL:
            if analysis.suggested_follow_ups:
                # Queue additional follow-ups
                for fu in analysis.suggested_follow_ups[1:]:
                    self.state.add_follow_up(fu, priority=6, reason="Partial response")

                return NextAction(
                    action_type=ActionType.ASK_FOLLOW_UP,
                    question_text=analysis.suggested_follow_ups[0],
                    reason="Response was incomplete"
                )

        # Priority 5: Process lower-priority triggers
        for trigger, matched_text in triggered_actions:
            if trigger.priority > 2:

                if trigger.action == TriggerAction.ASK_FOLLOW_UP:
                    # Queue it instead of interrupting
                    self.state.add_follow_up(
                        trigger.follow_up_question,
                        priority=trigger.priority,
                        reason=f"Triggered by: '{matched_text}'"
                    )

                elif trigger.action == TriggerAction.PROBE_DEEPER:
                    self.state.add_follow_up(
                        trigger.follow_up_question,
                        priority=trigger.priority,
                        reason=f"Probe deeper: '{matched_text}'"
                    )

        # Priority 6: Check if we have pending follow-ups now
        if self.state.has_follow_ups():
            follow_up = self.state.pop_follow_up()
            return NextAction(
                action_type=ActionType.ASK_FOLLOW_UP,
                question_text=follow_up["question"],
                reason=follow_up.get("reason", "Triggered follow-up"),
                priority=follow_up.get("priority", 5)
            )

        # Default: Move to next question
        return NextAction(
            action_type=ActionType.NEXT_QUESTION,
            reason="Response complete, moving to next question"
        )

    def should_skip_question(self, question_id: str) -> bool:
        """Check if a question should be skipped."""
        return question_id in self.state.skip_questions

    def check_domain_completion(self, domain: str) -> Tuple[bool, List[str]]:
        """
        Check if all required information for a domain is gathered.

        Returns:
            Tuple of (is_complete, missing_info_list)
        """
        domain_triggers = load_domain_triggers(domain)
        if not domain_triggers:
            return True, []

        missing = []
        for required in domain_triggers.required_info:
            if not self.state.is_info_gathered(domain, required):
                missing.append(required)

        return len(missing) == 0, missing

    def get_domain_summary(self, domain: str) -> Dict[str, Any]:
        """Get a summary of what was gathered for a domain."""
        return {
            "domain": domain,
            "gathered_info": self.state.domain_completion.get(domain, {}),
            "mentioned_systems": list(self.state.mentioned_systems),
            "pain_points": self.state.pain_points,
            "architect_flags": [f for f in self.state.architect_flags
                                if f["domain"] == domain],
            "skipped_questions": [q for q in self.state.skip_questions
                                  if q.startswith(domain[:2])]
        }

    def get_interview_summary(self) -> Dict[str, Any]:
        """Get a complete summary of the interview."""
        return {
            "systems_mentioned": self.state.mentioned_systems,
            "pain_points": self.state.pain_points,
            "architect_flags": self.state.architect_flags,
            "completion_by_domain": self.state.domain_completion,
            "questions_skipped": list(self.state.skip_questions)
        }
