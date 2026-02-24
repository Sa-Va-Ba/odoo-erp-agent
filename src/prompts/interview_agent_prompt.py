"""
Interview Agent Prompt Template

This prompt template is used to configure Claude or other LLMs
to act as the Interview Agent for Odoo implementation discovery.
"""

INTERVIEW_AGENT_SYSTEM_PROMPT = """
ROLE: Senior Odoo Business Analyst
EXPERIENCE: 15+ years of ERP implementations
OBJECTIVE: Complete requirements gathering for Odoo implementation

You are conducting a structured discovery interview for a first-time Odoo implementation.
Your goal is to extract complete, detailed requirements that will enable:
1. Accurate module selection from OCA (Odoo Community Association) and community modules
2. Proper configuration specifications
3. Custom development requirements identification
4. Data migration planning

INTERVIEW FRAMEWORK:
You will cover 10 domains in order:
1. Company basics (size, structure, locations)
2. Current systems and pain points
3. Core business processes by department:
   - Finance/Accounting
   - Sales/CRM
   - Inventory/Manufacturing
   - HR
   - Projects
4. Integration requirements
5. Reporting needs
6. User roles and permissions
7. Data migration scope

INTERVIEW STYLE:
- Ask ONE focused question at a time
- Probe for specifics when answers are vague
- Suggest Odoo capabilities when gaps identified
- Confirm understanding before moving forward
- Flag critical requirements for Technical Architect review

IMPORTANT GUIDELINES:
1. Never make assumptions - always clarify
2. Translate business needs into Odoo terminology when helpful
3. Identify potential customization needs early
4. Note any requirements that might conflict or need special attention
5. Be thorough but respectful of the client's time

OUTPUT FORMAT:
After each domain, summarize:
- Key requirements identified
- Potential Odoo modules/features that address needs
- Any flags or concerns for the Technical Architect
- Open questions that need follow-up
"""


def create_domain_prompt(
    domain_name: str,
    domain_number: int,
    total_domains: int,
    domain_context: str,
    odoo_capabilities: str,
    gathered_so_far: str,
    current_question: str,
    follow_up_hints: list[str] = None
) -> str:
    """
    Create a prompt for interviewing about a specific domain.

    Args:
        domain_name: Name of the current domain (e.g., "Finance & Accounting")
        domain_number: Current domain number (1-10)
        total_domains: Total number of domains (10)
        domain_context: Description of what this domain covers
        odoo_capabilities: What Odoo can do in this area
        gathered_so_far: Summary of information gathered so far
        current_question: The question to ask
        follow_up_hints: Potential follow-up questions if answer is vague

    Returns:
        Complete prompt string for the LLM
    """
    prompt = f"""
INTERVIEW_STAGE: {domain_name} ({domain_number}/{total_domains})

DOMAIN CONTEXT:
{domain_context}

ODOO CAPABILITIES IN THIS AREA:
{odoo_capabilities}

GATHERED SO FAR:
{gathered_so_far if gathered_so_far else "Starting this domain - no information gathered yet."}

---

CURRENT QUESTION TO ASK:
{current_question}
"""

    if follow_up_hints:
        prompt += f"""
FOLLOW-UP HINTS (use if answer is vague or incomplete):
{chr(10).join(f'- {hint}' for hint in follow_up_hints)}
"""

    prompt += """
---

Instructions:
1. Ask the question naturally, adapting wording to conversation flow
2. If the answer is vague, probe deeper with follow-up questions
3. Suggest relevant Odoo features when appropriate
4. Confirm your understanding before moving on
5. Note any requirements that need Technical Architect review
"""

    return prompt


def create_domain_summary_prompt(
    domain_name: str,
    all_responses: list[dict],
    odoo_capabilities: str
) -> str:
    """
    Create a prompt for summarizing a completed domain.

    Args:
        domain_name: Name of the completed domain
        all_responses: List of Q&A pairs from the domain
        odoo_capabilities: What Odoo can do in this area

    Returns:
        Prompt for generating domain summary
    """
    responses_text = "\n".join([
        f"Q: {r['question']}\nA: {r['answer']}\n"
        for r in all_responses
    ])

    return f"""
You have completed the {domain_name} section of the interview.

RESPONSES GATHERED:
{responses_text}

ODOO CAPABILITIES REFERENCE:
{odoo_capabilities}

Please provide a structured summary:

## {domain_name} - Requirements Summary

### Key Requirements Identified
[List main requirements in bullet points]

### Recommended Odoo Modules/Features
[Map requirements to specific Odoo modules/features]

### Customization Needs
[Any requirements that may need custom development]

### Technical Architect Flags
[Any concerns or complex requirements needing architect review]

### Open Questions
[Any items that need further clarification]

### Data Migration Notes
[Any data-related requirements for this domain]
"""


def create_interview_completion_prompt(
    client_name: str,
    industry: str,
    domain_summaries: list[str]
) -> str:
    """
    Create a prompt for generating the final requirements document.

    Args:
        client_name: Name of the client company
        industry: Client's industry
        domain_summaries: List of summaries from all domains

    Returns:
        Prompt for generating final requirements JSON
    """
    summaries_text = "\n\n---\n\n".join(domain_summaries)

    return f"""
The discovery interview for {client_name} ({industry}) is complete.

ALL DOMAIN SUMMARIES:
{summaries_text}

Please generate a comprehensive requirements document in the following JSON structure:

```json
{{
  "client_profile": {{
    "name": "{client_name}",
    "industry": "{industry}",
    "company_size": "",
    "locations": [],
    "currencies": [],
    "fiscal_year_end": ""
  }},
  "executive_summary": {{
    "business_objectives": [],
    "key_pain_points": [],
    "success_criteria": [],
    "timeline_expectations": ""
  }},
  "requirements_by_domain": {{
    "accounting": [],
    "sales_crm": [],
    "inventory": [],
    "manufacturing": [],
    "hr": [],
    "project": [],
    "integrations": [],
    "reporting": []
  }},
  "module_recommendations": {{
    "core_modules": [],
    "oca_modules": [],
    "potential_custom_modules": []
  }},
  "integration_requirements": [],
  "user_roles": [],
  "data_migration_scope": {{
    "systems": [],
    "data_types": [],
    "historical_years": 0,
    "cleanup_needed": false
  }},
  "technical_architect_flags": [],
  "open_questions": [],
  "phase_recommendations": {{
    "phase_1": [],
    "phase_2": [],
    "future": []
  }}
}}
```

Ensure all requirements are:
1. Specific and measurable where possible
2. Mapped to Odoo capabilities
3. Prioritized (critical, important, nice-to-have)
4. Tagged for customization if needed
"""


# Example usage with Claude API (pseudo-code)
CLAUDE_API_EXAMPLE = """
# Example of using these prompts with Claude API

import anthropic

client = anthropic.Client()

# Start interview
messages = [
    {"role": "system", "content": INTERVIEW_AGENT_SYSTEM_PROMPT}
]

# For each domain/question
domain_prompt = create_domain_prompt(
    domain_name="Finance & Accounting",
    domain_number=3,
    total_domains=10,
    domain_context="Chart of accounts, invoicing, payments, reporting",
    odoo_capabilities="Full double-entry bookkeeping, multi-currency...",
    gathered_so_far="Client is a manufacturing company with 50 employees...",
    current_question="Can you walk me through your current accounting workflow?",
    follow_up_hints=["What accounting software do you use?", "Who handles AP/AR?"]
)

messages.append({"role": "user", "content": domain_prompt})

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=messages,
    max_tokens=2000
)

# Continue conversation...
"""
