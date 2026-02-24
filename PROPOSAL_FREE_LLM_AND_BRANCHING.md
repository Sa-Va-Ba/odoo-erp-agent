# Proposal: Free LLM Integration & Advanced Branching Logic

## Part 1: Free LLM Options

### Recommended Primary: Groq (Cloud, Free Tier)

**Why Groq:**
- Completely free tier (no credit card required)
- 1,000 requests/day, 6,000 tokens/minute
- Ultra-fast inference (fastest in the market)
- OpenAI-compatible API (easy integration)
- Models: Llama 3.3 70B, DeepSeek R1, Mixtral 8x7B

**Setup:**
```bash
pip install groq
export GROQ_API_KEY=<your-key-from-console.groq.com>
```

### Recommended Fallback: Ollama (Local, 100% Free)

**Why Ollama:**
- Runs completely offline on your machine
- No API costs ever
- Privacy - data never leaves your device
- Works on Mac M1/M2/M3/M4 with 8GB+ RAM
- Models: Mistral 7B, Llama 3.2, Qwen 2.5

**Setup:**
```bash
# Install Ollama
brew install ollama  # or download from ollama.ai

# Pull a model
ollama pull mistral:7b

# Run locally
ollama serve
```

### Alternative Free Options

| Provider | Free Limits | Best For |
|----------|-------------|----------|
| Google AI Studio | 1.5M tokens/day | High volume |
| OpenRouter | 200 req/day | Model variety |
| Together AI | Free tier | Open source models |
| Cloudflare Workers AI | 10K neurons/day | Edge deployment |

### Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM Provider Manager                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Groq      │    │   Ollama    │    │  OpenRouter │     │
│  │  (Primary)  │    │ (Fallback)  │    │  (Backup)   │     │
│  │             │    │             │    │             │     │
│  │ Free: 1000  │    │ Free: ∞     │    │ Free: 200   │     │
│  │ req/day     │    │ (local)     │    │ req/day     │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│                   ┌────────▼────────┐                       │
│                   │  Unified API    │                       │
│                   │  (OpenAI-style) │                       │
│                   └─────────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 2: Advanced Follow-up Branching Logic

### Current State

The current implementation has simple follow-up logic:
- If response is short (<10 words) → ask follow-ups
- If response contains vague words ("maybe", "depends") → ask follow-ups

### Proposed Enhancement: Multi-Level Branching System

#### 2.1 Response Quality Analysis

```python
class ResponseQuality(Enum):
    COMPLETE = "complete"      # Full, detailed answer
    PARTIAL = "partial"        # Answer but missing details
    VAGUE = "vague"            # Unclear or non-committal
    OFF_TOPIC = "off_topic"    # Didn't answer the question
    NEEDS_CLARIFICATION = "needs_clarification"  # Technical terms need explanation
```

#### 2.2 Branching Decision Tree

```
User Response
     │
     ▼
┌─────────────────┐
│ Analyze Response │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 Short?    Vague?
 (<15w)    (keywords)
    │         │
    ▼         ▼
┌───┴───┐ ┌───┴───┐
│       │ │       │
▼       ▼ ▼       ▼
Yes     No Yes    No
│       │  │      │
▼       │  ▼      │
Probe   │  Clarify│
Deeper  │  Intent │
        │         │
        └────┬────┘
             │
             ▼
      ┌──────────────┐
      │ Check Domain │
      │ Completeness │
      └──────┬───────┘
             │
    ┌────────┼────────┐
    │        │        │
    ▼        ▼        ▼
 Missing  Has Key   Complete
 Critical Details   Domain
 Info
    │        │        │
    ▼        ▼        ▼
 Must-Ask  Optional  Next
 Follow-up Follow-up Question
```

#### 2.3 Domain-Specific Branching Rules

Each domain has specific triggers for follow-up questions:

**Finance & Accounting Domain:**
```yaml
triggers:
  - keyword: "QuickBooks|Xero|Sage"
    action: ask_migration_complexity
    follow_up: "How many years of data do you have in {system}?"

  - keyword: "multi-currency|multiple currencies"
    action: probe_currency_details
    follow_up: "Which currencies do you invoice in vs. pay vendors in?"

  - keyword: "tax|VAT|GST"
    action: probe_tax_complexity
    follow_up: "Do you have different tax rates for different products/regions?"

  - missing: "chart_of_accounts"
    action: must_ask
    follow_up: "Do you have a standardized Chart of Accounts structure?"
```

**Sales & CRM Domain:**
```yaml
triggers:
  - keyword: "Salesforce|HubSpot|Pipedrive"
    action: ask_migration_scope
    follow_up: "What data would you need to migrate from {system}?"

  - keyword: "discount|special pricing"
    action: probe_pricing_rules
    follow_up: "Who can approve discounts and what are the limits?"

  - keyword: "commission"
    action: probe_commission_structure
    follow_up: "How is commission calculated? Flat rate or tiered?"

  - missing: "sales_process_stages"
    action: must_ask
    follow_up: "What stages does a deal go through from lead to close?"
```

**Inventory & Operations Domain:**
```yaml
triggers:
  - keyword: "barcode|scanning"
    action: probe_barcode_needs
    follow_up: "What operations need barcode scanning? Receiving, picking, both?"

  - keyword: "manufacture|assembly|production"
    action: probe_manufacturing_depth
    follow_ups:
      - "Do you need Bill of Materials (BOM) management?"
      - "Do you track work center capacity?"
      - "Do you have routing/work order steps?"

  - keyword: "dropship|direct ship"
    action: probe_dropship_process
    follow_up: "How do you currently manage dropship orders with vendors?"

  - missing: "inventory_valuation_method"
    action: must_ask
    follow_up: "How do you value inventory? FIFO, average cost, or standard?"
```

#### 2.4 Conversation Flow Control

```python
class ConversationState:
    """Track conversation state for intelligent branching."""

    # Track what critical info we have/need per domain
    domain_requirements: Dict[str, DomainRequirements]

    # Pending follow-ups queue (prioritized)
    pending_follow_ups: PriorityQueue[FollowUpQuestion]

    # Context from previous answers (for reference)
    conversation_context: Dict[str, str]

    # Systems mentioned (for cross-referencing)
    mentioned_systems: List[str]

    # Pain points identified (for emphasis)
    pain_points: List[str]


class BranchingEngine:
    """Engine for determining next question/follow-up."""

    def analyze_response(self, question: Question, response: str) -> ResponseAnalysis:
        """Analyze response quality and extract information."""

    def get_next_action(self, state: ConversationState) -> NextAction:
        """Determine next action: follow-up, next question, or domain complete."""

    def should_probe_deeper(self, response: str, domain: str) -> List[str]:
        """Check domain-specific triggers for deeper probing."""

    def check_domain_completeness(self, domain: str, state: ConversationState) -> CompletionStatus:
        """Check if we have all critical information for a domain."""
```

#### 2.5 LLM-Assisted Analysis

For complex response analysis, use the LLM to:

```python
ANALYSIS_PROMPT = """
Analyze this interview response for an Odoo implementation discovery.

Question: {question}
Response: {response}
Domain: {domain}

Determine:
1. Response quality (complete/partial/vague/off_topic)
2. Key information extracted (list)
3. Missing critical information (list)
4. Suggested follow-up questions (list, max 2)
5. Any Odoo module implications mentioned

Return as JSON.
"""
```

#### 2.6 Adaptive Question Selection

Instead of strictly linear questions, adapt based on responses:

```python
class AdaptiveQuestionSelector:
    """Select next question based on conversation context."""

    def select_next(self, domain: DomainDefinition, state: ConversationState) -> Question:
        # Check for must-ask follow-ups first
        if state.has_critical_follow_ups():
            return state.pop_critical_follow_up()

        # Check for triggered follow-ups
        triggered = self.check_triggers(state.last_response, domain)
        if triggered:
            return triggered[0]  # Most relevant trigger

        # Check if we can skip questions based on context
        next_q = domain.get_next_question(state.current_index)
        if self.can_skip(next_q, state):
            state.current_index += 1
            return self.select_next(domain, state)

        return next_q

    def can_skip(self, question: Question, state: ConversationState) -> bool:
        """Check if question is already answered from context."""
        # E.g., if they said "we don't manufacture anything"
        # skip all manufacturing-related questions
        pass
```

#### 2.7 Example Conversation Flow

```
AGENT: How do you currently manage your inventory?

USER: We use Excel spreadsheets. It's a mess honestly.

[Analysis]
- Quality: PARTIAL (mentions current system but lacks detail)
- Extracted: current_system=Excel, pain_point=disorganized
- Missing: tracking_method, volume, locations
- Triggers: "spreadsheet" → probe automation needs

AGENT: I understand the challenges with spreadsheets. A few follow-ups:
       1. Do you track inventory by serial numbers, lot numbers, or just quantities?

USER: Just quantities for most items, but we have some serialized equipment.

[Analysis]
- Quality: COMPLETE
- Extracted: tracking=mixed (quantity + serial for some)
- Triggers: "serialized" → probe which products need serial tracking

AGENT: Got it - mixed tracking makes sense. Which product categories need
       serial number tracking? This will help us configure Odoo's tracking properly.

USER: Mainly our high-value machinery and electronic components.

[Analysis]
- Quality: COMPLETE
- Extracted: serial_categories=[machinery, electronics]
- Domain completeness: Still missing → warehouse_locations, reorder_process

AGENT: Perfect. Now, how many warehouse locations do you operate from?
       [Continues with adaptive flow...]
```

---

## Part 3: Implementation Plan

### Phase 1: LLM Integration (1-2 days)
1. Create `LLMProvider` base class with unified interface
2. Implement `GroqProvider` (primary)
3. Implement `OllamaProvider` (fallback)
4. Add provider auto-selection and failover logic
5. Add environment-based configuration

### Phase 2: Branching Logic (2-3 days)
1. Create `ResponseAnalyzer` class
2. Define domain-specific trigger rules (YAML/JSON config)
3. Implement `BranchingEngine` with decision tree
4. Create `AdaptiveQuestionSelector`
5. Add LLM-assisted response analysis
6. Update `InterviewAgent` to use new branching system

### Phase 3: Testing & Refinement (1 day)
1. Test with sample interviews
2. Tune trigger keywords and thresholds
3. Add logging for branching decisions
4. Document branching rules

---

## Questions for You

1. **LLM Provider Priority**:
   - Start with Groq (cloud) or Ollama (local) as primary?
   - Do you have a Mac with M-series chip for local inference?

2. **Branching Complexity**:
   - Full adaptive system (LLM-assisted analysis) or rule-based only?
   - How strict should domain completion be? (must have all critical info vs. best effort)

3. **Configuration Format**:
   - Hardcoded Python or external YAML/JSON for trigger rules?
   - This affects how easy it is to modify branching without code changes.

Let me know your preferences and I'll start implementation!
