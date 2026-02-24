"""
Response Analyzer for interview responses.

Analyzes user responses to determine quality, extract information,
and identify areas that need follow-up questions.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class ResponseQuality(str, Enum):
    """Quality classification of a response."""
    COMPLETE = "complete"           # Full, detailed answer with specifics
    PARTIAL = "partial"             # Answer provided but missing details
    VAGUE = "vague"                 # Unclear, non-committal, or uncertain
    OFF_TOPIC = "off_topic"         # Didn't answer the question
    NEGATIVE = "negative"           # Clear "no" or "not applicable"
    SKIP_SIGNAL = "skip_signal"     # User wants to skip


@dataclass
class ExtractedInfo:
    """Information extracted from a response."""
    key: str                        # What was extracted (e.g., "employee_count")
    value: Any                      # The extracted value
    confidence: float = 1.0         # How confident we are (0-1)
    source_text: str = ""           # Original text this was extracted from


@dataclass
class ResponseAnalysis:
    """Complete analysis of a response."""
    quality: ResponseQuality
    word_count: int
    extracted_info: List[ExtractedInfo] = field(default_factory=list)
    detected_keywords: List[str] = field(default_factory=list)
    detected_systems: List[str] = field(default_factory=list)
    detected_pain_points: List[str] = field(default_factory=list)
    needs_follow_up: bool = False
    follow_up_reasons: List[str] = field(default_factory=list)
    suggested_follow_ups: List[str] = field(default_factory=list)
    skip_future_questions: List[str] = field(default_factory=list)  # Question IDs to skip


class ResponseAnalyzer:
    """
    Analyzes interview responses for quality and information extraction.

    Can work in two modes:
    1. Rule-based (fast, no LLM needed)
    2. LLM-assisted (more accurate, requires LLM)
    """

    # Indicators of vague/uncertain responses
    VAGUE_INDICATORS = [
        r"\bmaybe\b", r"\bi think\b", r"\bnot sure\b", r"\bdepends\b",
        r"\bsometimes\b", r"\bit varies\b", r"\bkind of\b", r"\bsort of\b",
        r"\bprobably\b", r"\bmight\b", r"\bcould be\b", r"\bnot really\b",
        r"\bi guess\b", r"\bi don'?t know\b", r"\bhard to say\b"
    ]

    # Indicators of negative/not applicable responses
    NEGATIVE_INDICATORS = [
        r"\bno\b", r"\bnot applicable\b", r"\bn/?a\b", r"\bwe don'?t\b",
        r"\bwe do not\b", r"\bnone\b", r"\bnever\b", r"\bnothing\b",
        r"\bdon'?t have\b", r"\bdon'?t use\b", r"\bdon'?t need\b"
    ]

    # Skip signals
    SKIP_SIGNALS = [
        r"^skip$", r"^next$", r"^pass$", r"^n/?a$", r"^-$",
        r"^\[skipped.*\]$", r"^\[error\]$"
    ]

    # Common software systems (for detection)
    KNOWN_SYSTEMS = {
        # Accounting
        "quickbooks": "accounting", "xero": "accounting", "sage": "accounting",
        "freshbooks": "accounting", "wave": "accounting", "zoho books": "accounting",

        # CRM
        "salesforce": "crm", "hubspot": "crm", "pipedrive": "crm",
        "zoho crm": "crm", "dynamics": "crm", "monday": "crm",

        # ERP
        "sap": "erp", "oracle": "erp", "netsuite": "erp", "odoo": "erp",
        "microsoft dynamics": "erp", "infor": "erp",

        # E-commerce
        "shopify": "ecommerce", "woocommerce": "ecommerce", "magento": "ecommerce",
        "bigcommerce": "ecommerce", "prestashop": "ecommerce",

        # Inventory
        "fishbowl": "inventory", "cin7": "inventory", "tradegecko": "inventory",
        "dear inventory": "inventory", "unleashed": "inventory",

        # HR
        "bamboohr": "hr", "gusto": "hr", "adp": "hr", "workday": "hr",
        "zenefits": "hr", "rippling": "hr",

        # Project Management
        "asana": "project", "jira": "project", "trello": "project",
        "basecamp": "project", "clickup": "project",

        # General
        "excel": "spreadsheet", "google sheets": "spreadsheet",
        "airtable": "spreadsheet", "notion": "general"
    }

    # Pain point indicators
    PAIN_POINT_PATTERNS = [
        r"(?:it'?s?\s+)?(?:a\s+)?(?:real\s+)?(?:pain|nightmare|mess|disaster|problem)",
        r"(?:we\s+)?(?:struggle|struggling)\s+(?:with|to)",
        r"(?:takes?\s+)?(?:too\s+)?(?:much|long)\s+time",
        r"(?:always|constantly)\s+(?:have\s+to|need\s+to|breaking|failing)",
        r"(?:can'?t|cannot|unable\s+to)\s+(?:track|see|find|manage)",
        r"(?:don'?t\s+have)\s+(?:visibility|insight|control)",
        r"(?:manual|manually)\s+(?:process|enter|input|track)",
        r"(?:error|mistake|issue|bug)s?\s+(?:all\s+the\s+time|frequently|often)",
        r"(?:no|lack\s+of)\s+(?:integration|automation|visibility)",
        r"(?:duplicate|redundant)\s+(?:data|entry|work)"
    ]

    def __init__(self, use_llm: bool = False, llm_manager=None):
        """
        Initialize the response analyzer.

        Args:
            use_llm: Whether to use LLM for enhanced analysis
            llm_manager: LLM manager instance (required if use_llm=True)
        """
        self.use_llm = use_llm
        self.llm_manager = llm_manager

    def analyze(
        self,
        response: str,
        question_text: str,
        domain: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ResponseAnalysis:
        """
        Analyze a response to determine quality and extract information.

        Args:
            response: The user's response text
            question_text: The question that was asked
            domain: The current interview domain
            context: Additional context (previous responses, etc.)

        Returns:
            ResponseAnalysis with quality assessment and extracted info
        """
        response_lower = response.lower().strip()
        word_count = len(response.split())

        # Check for skip signal
        if self._is_skip_signal(response_lower):
            return ResponseAnalysis(
                quality=ResponseQuality.SKIP_SIGNAL,
                word_count=word_count
            )

        # Detect quality
        quality = self._assess_quality(response_lower, word_count, question_text)

        # Extract systems mentioned
        detected_systems = self._detect_systems(response_lower)

        # Detect pain points
        detected_pain_points = self._detect_pain_points(response)

        # Extract keywords
        detected_keywords = self._extract_keywords(response_lower, domain)

        # Determine if follow-up is needed
        needs_follow_up, follow_up_reasons = self._needs_follow_up(
            quality, response_lower, word_count, domain
        )

        # Generate suggested follow-ups
        suggested_follow_ups = self._generate_follow_ups(
            quality, response_lower, domain, detected_systems, context
        )

        # Determine if we can skip future questions
        skip_questions = self._identify_skippable_questions(
            response_lower, domain, detected_keywords
        )

        # If LLM is enabled, enhance analysis
        if self.use_llm and self.llm_manager:
            return self._enhance_with_llm(
                ResponseAnalysis(
                    quality=quality,
                    word_count=word_count,
                    detected_keywords=detected_keywords,
                    detected_systems=detected_systems,
                    detected_pain_points=detected_pain_points,
                    needs_follow_up=needs_follow_up,
                    follow_up_reasons=follow_up_reasons,
                    suggested_follow_ups=suggested_follow_ups,
                    skip_future_questions=skip_questions
                ),
                response,
                question_text,
                domain
            )

        return ResponseAnalysis(
            quality=quality,
            word_count=word_count,
            detected_keywords=detected_keywords,
            detected_systems=detected_systems,
            detected_pain_points=detected_pain_points,
            needs_follow_up=needs_follow_up,
            follow_up_reasons=follow_up_reasons,
            suggested_follow_ups=suggested_follow_ups,
            skip_future_questions=skip_questions
        )

    def _is_skip_signal(self, response: str) -> bool:
        """Check if response indicates user wants to skip."""
        for pattern in self.SKIP_SIGNALS:
            if re.match(pattern, response, re.IGNORECASE):
                return True
        return False

    def _assess_quality(self, response: str, word_count: int, question: str) -> ResponseQuality:
        """Assess the quality of a response."""
        # Check for negative indicators first
        for pattern in self.NEGATIVE_INDICATORS:
            if re.search(pattern, response, re.IGNORECASE):
                # Only if it's a short response (likely a direct "no")
                if word_count < 20:
                    return ResponseQuality.NEGATIVE

        # Check for vague indicators
        vague_count = sum(
            1 for pattern in self.VAGUE_INDICATORS
            if re.search(pattern, response, re.IGNORECASE)
        )
        if vague_count >= 2 or (vague_count >= 1 and word_count < 15):
            return ResponseQuality.VAGUE

        # Check word count thresholds
        if word_count < 5:
            return ResponseQuality.PARTIAL
        elif word_count < 15:
            # Short but might be complete if specific
            if any(char.isdigit() for char in response):
                return ResponseQuality.COMPLETE  # Contains numbers = specific
            return ResponseQuality.PARTIAL
        elif word_count >= 30:
            return ResponseQuality.COMPLETE
        else:
            # Medium length - check for specificity
            has_numbers = any(char.isdigit() for char in response)
            has_names = any(system in response for system in self.KNOWN_SYSTEMS)
            if has_numbers or has_names:
                return ResponseQuality.COMPLETE
            return ResponseQuality.PARTIAL

    def _detect_systems(self, response: str) -> List[str]:
        """Detect software systems mentioned in response."""
        detected = []
        for system, category in self.KNOWN_SYSTEMS.items():
            if system in response:
                detected.append(f"{system} ({category})")
        return detected

    def _detect_pain_points(self, response: str) -> List[str]:
        """Detect pain points mentioned in response."""
        pain_points = []
        for pattern in self.PAIN_POINT_PATTERNS:
            matches = re.findall(pattern, response, re.IGNORECASE)
            for match in matches:
                # Extract surrounding context
                idx = response.lower().find(match.lower())
                start = max(0, idx - 20)
                end = min(len(response), idx + len(match) + 30)
                context = response[start:end].strip()
                if context not in pain_points:
                    pain_points.append(context)
        return pain_points[:5]  # Limit to 5

    def _extract_keywords(self, response: str, domain: str) -> List[str]:
        """Extract domain-relevant keywords from response."""
        keywords = []

        # Domain-specific keyword patterns
        domain_patterns = {
            "finance_accounting": [
                r"\binvoic\w*\b", r"\bpayment\w*\b", r"\btax\w*\b", r"\bvat\b",
                r"\breconcil\w*\b", r"\bbudget\w*\b", r"\breport\w*\b"
            ],
            "sales_crm": [
                r"\blead\w*\b", r"\bopportunit\w*\b", r"\bpipeline\b",
                r"\bquot\w*\b", r"\bdiscount\w*\b", r"\bcommission\w*\b"
            ],
            "inventory_operations": [
                r"\bwarehouse\w*\b", r"\bstock\w*\b", r"\bserial\w*\b",
                r"\blot\w*\b", r"\bbarcod\w*\b", r"\bmanufactur\w*\b"
            ],
            "hr_payroll": [
                r"\bemploy\w*\b", r"\battendanc\w*\b", r"\bleave\w*\b",
                r"\bpayroll\w*\b", r"\brecruit\w*\b", r"\bexpens\w*\b"
            ],
            "integrations": [
                r"\bapi\b", r"\bintegrat\w*\b", r"\bsync\w*\b",
                r"\bconnect\w*\b", r"\bimport\w*\b", r"\bexport\w*\b"
            ]
        }

        patterns = domain_patterns.get(domain, [])
        for pattern in patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            keywords.extend(matches)

        return list(set(keywords))

    def _needs_follow_up(
        self,
        quality: ResponseQuality,
        response: str,
        word_count: int,
        domain: str
    ) -> tuple[bool, List[str]]:
        """Determine if follow-up questions are needed."""
        reasons = []

        if quality == ResponseQuality.VAGUE:
            reasons.append("Response is vague or uncertain")
        elif quality == ResponseQuality.PARTIAL:
            reasons.append("Response is missing details")
        elif quality == ResponseQuality.OFF_TOPIC:
            reasons.append("Response doesn't address the question")

        # Domain-specific triggers
        if domain == "finance_accounting":
            if "multi" in response and "currenc" in response:
                reasons.append("Multi-currency mentioned - need specifics")
            if any(x in response for x in ["tax", "vat", "gst"]):
                reasons.append("Tax mentioned - need compliance details")

        elif domain == "inventory_operations":
            if "serial" in response or "lot" in response:
                reasons.append("Tracking method mentioned - need product categories")
            if "manufactur" in response:
                reasons.append("Manufacturing mentioned - need BOM/routing details")

        elif domain == "sales_crm":
            if "discount" in response:
                reasons.append("Discounts mentioned - need approval workflow")
            if "commission" in response:
                reasons.append("Commission mentioned - need calculation method")

        return len(reasons) > 0, reasons

    def _generate_follow_ups(
        self,
        quality: ResponseQuality,
        response: str,
        domain: str,
        detected_systems: List[str],
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate follow-up questions based on analysis."""
        follow_ups = []

        # Generic follow-ups for quality issues
        if quality == ResponseQuality.VAGUE:
            follow_ups.append("Can you give me a specific example?")
        elif quality == ResponseQuality.PARTIAL:
            follow_ups.append("Could you tell me more about that?")

        # System-specific follow-ups
        for system_info in detected_systems:
            system = system_info.split(" (")[0]
            follow_ups.append(f"How long have you been using {system}?")
            follow_ups.append(f"What data would you need to migrate from {system}?")
            break  # Only one system follow-up

        # Domain-specific follow-ups
        if domain == "finance_accounting":
            if "multi" in response and "currenc" in response:
                follow_ups.append("Which currencies do you invoice in vs pay vendors in?")
            if "report" in response:
                follow_ups.append("Who needs access to these reports and how often?")

        elif domain == "inventory_operations":
            if "warehouse" in response and "multiple" not in response:
                follow_ups.append("How many warehouse locations do you operate?")
            if "barcode" in response or "scan" in response:
                follow_ups.append("What operations need barcode scanning - receiving, picking, or both?")

        elif domain == "sales_crm":
            if "discount" in response:
                follow_ups.append("Who can approve discounts and what are the approval limits?")

        return follow_ups[:3]  # Limit to 3 follow-ups

    def _identify_skippable_questions(
        self,
        response: str,
        domain: str,
        keywords: List[str]
    ) -> List[str]:
        """Identify questions that can be skipped based on response."""
        skip_questions = []

        # If they say they don't manufacture, skip manufacturing questions
        if "don't manufacture" in response or "do not manufacture" in response:
            skip_questions.extend(["io_04", "io_05"])  # Manufacturing questions

        # If they say they don't have employees, skip HR questions
        if "no employees" in response or "just me" in response:
            skip_questions.extend(["hr_02", "hr_03", "hr_04", "hr_05", "hr_06"])

        # If they say they don't sell online, skip e-commerce questions
        if "don't sell online" in response or "no e-commerce" in response:
            skip_questions.extend(["sc_06", "in_02"])

        return skip_questions

    def _enhance_with_llm(
        self,
        base_analysis: ResponseAnalysis,
        response: str,
        question: str,
        domain: str
    ) -> ResponseAnalysis:
        """Enhance analysis using LLM for better understanding."""
        if not self.llm_manager:
            return base_analysis

        prompt = f"""Analyze this interview response for an Odoo ERP implementation.

Question asked: {question}
User's response: {response}
Domain: {domain}

Current analysis:
- Quality: {base_analysis.quality.value}
- Detected systems: {base_analysis.detected_systems}
- Pain points: {base_analysis.detected_pain_points}

Please provide:
1. Is the current quality assessment correct? If not, what should it be?
2. What additional information was extracted that we might have missed?
3. What are the 2 most important follow-up questions to ask?

Keep your response brief and actionable."""

        try:
            llm_response = self.llm_manager.complete(
                prompt,
                system_prompt="You are an expert Odoo business analyst. Be concise.",
                max_tokens=500
            )

            # Parse LLM suggestions (simplified - could be more structured)
            content = llm_response.content

            # Extract suggested follow-ups if mentioned
            if "follow-up" in content.lower():
                # Simple extraction - in production, use structured output
                lines = content.split("\n")
                for line in lines:
                    if "?" in line and len(line) > 20:
                        base_analysis.suggested_follow_ups.append(line.strip())

        except Exception as e:
            # LLM failed, use base analysis
            print(f"LLM enhancement failed: {e}")

        return base_analysis
