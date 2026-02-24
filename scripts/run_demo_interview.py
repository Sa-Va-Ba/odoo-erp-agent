"""
Automated demo interview for a consumer goods / DTC pet food company
(modeled after Just Russel — personalized pet food, subscription-based,
e-commerce + some B2B wholesale).

Runs the full interview via the Flask API, generates the PRD, and
leaves the server running so you can view the result in the browser.

Usage:
    python3 scripts/run_demo_interview.py

Then open http://localhost:5001 — the PRD will already be generated.
"""

import requests
import json
import time
import sys

BASE = "http://localhost:5001"

# ── Answers keyed by question ID prefix ──
# Scoping answers
SCOPING_ANSWERS = {
    "scope_01": (
        "We sell personalized pet food — fresh, made-to-order kibble and wet food "
        "tailored to each dog's breed, age, weight, and dietary needs. Our main channel "
        "is a subscription e-commerce model: customers fill in a profile for their dog, "
        "we generate a custom recipe, and they get recurring deliveries every 2–6 weeks. "
        "We also have a small B2B wholesale channel selling to independent pet shops and "
        "veterinary clinics in Belgium and the Netherlands."
    ),
    "scope_02": (
        "Yes, absolutely. We have a central warehouse near Antwerp where we store raw "
        "ingredients (proteins, grains, supplements) and finished packaged products. "
        "We ship direct-to-consumer via bpost and DHL across Belgium, Netherlands, and "
        "France. We also do pallet shipments to our B2B wholesale customers. We need "
        "lot tracking for ingredients due to food safety regulations (FAVV/AFSCA compliance)."
    ),
    "scope_03": (
        "Yes, we manufacture our own pet food. We have a production facility connected to "
        "the warehouse. We process raw materials (chicken, rice, vegetables, supplements) "
        "through mixing, cooking, and packaging lines. We need bill of materials management, "
        "production planning, and batch/lot traceability for quality control."
    ),
    "scope_04": (
        "We use formal purchase orders with our ingredient suppliers — around 25 active "
        "suppliers for proteins, grains, packaging materials, and supplements. Some suppliers "
        "have blanket contracts with agreed pricing tiers. We reorder based on min stock "
        "levels and production planning needs. Lead times vary from 2 days for local suppliers "
        "to 3 weeks for specialty imports."
    ),
    "scope_05": (
        "Not really. We don't do project-based or time & materials billing. Our business "
        "is product-based with subscriptions. We might track some internal projects like "
        "new recipe development but we don't need to bill anyone for that."
    ),
    "scope_06": (
        "We currently use a separate accounting package (Exact Online) but want to consolidate "
        "into Odoo. We deal with Belgian VAT (21%, 6% for pet food), intra-EU sales to NL and "
        "FR with reverse charge, and all invoicing is in EUR. We need structured chart of "
        "accounts following Belgian accounting standards (MAR/PCR). Monthly VAT returns and "
        "annual accounts filing."
    ),
    "scope_07": (
        "We have about 35 employees — 8 in the production facility, 5 in the warehouse, "
        "3 in customer support, 4 in marketing, 2 in finance, 3 in product development, "
        "and 10 in management/operations. We'd like to manage leave requests, track "
        "attendance for production staff (shifts), and handle expense claims. Payroll is "
        "done via our social secretariat (Securex) so we just need the HR admin side."
    ),
    "scope_08": (
        "Our main sales channel is our Shopify store where customers create dog profiles "
        "and subscribe. We'd like to keep Shopify as the storefront but sync orders, "
        "inventory, and customer data with Odoo. We also have a basic WordPress site for "
        "B2B inquiries but that's just a contact form."
    ),
    "scope_09": (
        "Key integrations: Shopify (orders, inventory sync), Stripe (payment processing), "
        "bpost and DHL APIs (shipping labels and tracking), Exact Online (accounting — to "
        "be replaced), Mailchimp (email marketing), Securex (payroll export). We also use "
        "Google Workspace for internal collaboration and have some Google Sheets with "
        "recipe formulations we'd eventually want in Odoo."
    ),
}

# Domain expert answers — generic responses that work for any domain question
DOMAIN_ANSWERS = {
    "sales": [
        (
            "Our sales process has two tracks. For D2C: customers visit our Shopify store, "
            "create a dog profile (breed, age, weight, allergies, activity level), we "
            "generate a personalized food plan with a recommended recipe, they choose a "
            "delivery frequency (2, 4, or 6 weeks), and they subscribe. Average order is "
            "about 45-65 EUR depending on dog size. For B2B: sales reps contact pet shops "
            "and vets, we send quotes with volume discounts, they place orders via email "
            "or phone, we invoice on 30-day payment terms."
        ),
        (
            "We use tiered pricing for both channels. D2C has a fixed price per kg based on "
            "the recipe complexity — standard recipes around 8 EUR/kg, premium (grain-free, "
            "single protein) around 12 EUR/kg. B2B wholesale gets 30-40% discount off retail "
            "depending on volume commitments. We offer a 10% discount on the first subscription "
            "order as acquisition incentive. No complex pricelist rules beyond that."
        ),
        (
            "Subscriptions are managed in Shopify currently. Customers can pause, skip a "
            "delivery, change frequency, or cancel online. We'd want Odoo to receive and "
            "process the recurring orders. Churn rate is about 8% monthly so retention is "
            "important. We send renewal reminders 3 days before each shipment."
        ),
        (
            "For B2B customers we track credit limits — most are net-30, a few larger accounts "
            "are net-60. We don't use sales teams per se, it's two people handling all wholesale. "
            "We do want basic pipeline tracking for new B2B prospects."
        ),
        (
            "Quotations are pretty simple — product, quantity, unit price, delivery date. We "
            "don't do complex multi-line configurations. The main thing we need is a clear "
            "distinction between D2C subscription orders (from Shopify) and B2B wholesale "
            "orders (manual or email-based)."
        ),
    ],
    "inventory": [
        (
            "We have one warehouse with three zones: raw materials storage (temperature-controlled "
            "for proteins), production staging area, and finished goods ready for shipping. "
            "We use FEFO (first expired first out) for ingredients and FIFO for finished goods."
        ),
        (
            "We need lot/batch tracking on both incoming ingredients and outgoing finished products. "
            "Each production batch gets a lot number tied to the ingredient lots used. This is "
            "critical for food safety — if there's a recall on a protein batch, we need to trace "
            "which finished products used it and which customers received them."
        ),
        (
            "Reordering is currently manual with spreadsheets. We check stock weekly and place "
            "orders when we're below minimum levels. We'd like automated reorder rules in Odoo — "
            "min/max stock rules per ingredient, with different lead times per supplier."
        ),
        (
            "We ship about 200-300 D2C parcels per day and 5-10 pallet shipments per week for "
            "wholesale. D2C goes via bpost (domestic) and DHL (international). We generate "
            "shipping labels via their APIs and need tracking numbers synced back to orders."
        ),
        (
            "We do cycle counts monthly for high-value ingredients (proteins, supplements) and "
            "full inventory count quarterly. Accuracy is usually around 97% which we'd like to "
            "improve. Barcode scanning would help — we already have the hardware."
        ),
    ],
    "manufacturing": [
        (
            "We have about 15 standard recipes (BOMs) and the ability to create custom variations. "
            "A typical BOM has 6-12 ingredients plus packaging materials. We produce in batches — "
            "usually 200-500kg per production run depending on demand forecasts."
        ),
        (
            "Production is planned weekly. We look at upcoming subscription deliveries plus B2B "
            "orders, aggregate demand by recipe, and schedule production runs. Most recipes take "
            "about 4 hours from start to packaged product. We run two shifts."
        ),
        (
            "Quality control is essential for pet food. We test each batch for moisture content, "
            "protein levels, and contaminants. A batch can be released, quarantined, or rejected. "
            "We need to record QC results and link them to the production lot."
        ),
        (
            "Main bottleneck is the mixing line — we can only run one recipe at a time, and "
            "changeover between recipes takes about 45 minutes for cleaning. So we try to batch "
            "similar recipes together. Planning optimization would be very helpful."
        ),
        (
            "We track production costs per batch — ingredient costs, labor (hours per shift), "
            "packaging, and overhead allocation. This feeds into our gross margin analysis per "
            "recipe and helps us price new recipes."
        ),
    ],
    "purchase": [
        (
            "We work with about 25 suppliers. Key categories: proteins (chicken, beef, fish — "
            "3 suppliers), grains and vegetables (5 suppliers), supplements and vitamins (4 "
            "specialized suppliers), packaging (3 suppliers). Some are local Belgian suppliers "
            "with 2-3 day delivery, others are European with 1-3 week lead times."
        ),
        (
            "For our main protein suppliers we have annual framework agreements with agreed "
            "pricing per kg at different volume tiers. We review these annually. For other "
            "ingredients it's more spot purchasing based on current pricing."
        ),
        (
            "Quality incoming inspection is mandatory. We check certificates of analysis for "
            "each ingredient delivery, verify quantities, check expiry dates, and take samples "
            "for our lab. Suppliers need to provide FAVV-compliant documentation."
        ),
        (
            "We'd like three-way matching — PO, receipt, invoice. Currently it's a mess with "
            "paper delivery notes and manual invoice matching. Some suppliers send invoices "
            "that don't match the PO quantities because of partial deliveries."
        ),
    ],
    "finance": [
        (
            "Belgian company (BV/SRL), standard Belgian chart of accounts following MAR plan. "
            "We file monthly VAT returns, prepare annual accounts for filing with the NBB. "
            "Our accountant handles the annual filing but we do the day-to-day bookkeeping."
        ),
        (
            "VAT setup: domestic sales at 6% (pet food is reduced rate in Belgium), some items "
            "at 21% (accessories, supplements sold separately). Intra-community supplies to NL "
            "and FR at 0% with reverse charge. We also have some import duties on specialty "
            "ingredients from outside the EU."
        ),
        (
            "Payment methods: D2C customers pay via Stripe (card) at subscription checkout. "
            "B2B customers are invoiced with bank transfer — we use a KBC business account. "
            "We reconcile bank statements weekly, would like daily with automated matching."
        ),
        (
            "Key financial reports: P&L by product line (D2C vs B2B), gross margin per recipe, "
            "cash flow forecasting (important due to ingredient pre-purchasing), aged receivables "
            "for B2B customers, and monthly management reporting pack."
        ),
    ],
    "hr": [
        (
            "35 employees across departments. Production staff (8) and warehouse staff (5) work "
            "in shifts — early shift 6am-2pm, late shift 2pm-10pm. Office staff work standard "
            "9-5. Some team leads split between production and office."
        ),
        (
            "Leave management: Belgian legal holidays plus 20 days annual leave per employee. "
            "We need to track ADV days (arbeidsduurvermindering), recuperation days for shift "
            "workers, and sick leave. Currently tracked in a shared spreadsheet."
        ),
        (
            "No internal payroll — Securex handles all payroll calculations, social contributions, "
            "and payslips. We just need to export worked hours, leave days, and expense claims "
            "to them monthly. A structured export file would save us a lot of time."
        ),
        (
            "Expense claims are mainly for the sales reps (travel, client meals) and management "
            "(conferences, travel). About 20-30 expense claims per month. Currently done via "
            "email with receipt photos — very manual approval process."
        ),
    ],
    "ecommerce": [
        (
            "Shopify is our primary storefront and we want to keep it — our frontend team has "
            "built custom features for the dog profile builder and subscription management. "
            "What we need is reliable two-way sync: orders from Shopify into Odoo for fulfillment, "
            "and inventory levels from Odoo back to Shopify to prevent overselling."
        ),
        (
            "Order volume is about 200-300 orders per day, mostly subscription renewals. Peak "
            "periods around holidays (Christmas gift subscriptions) can hit 500+/day. We need "
            "the sync to handle that volume without delays."
        ),
        (
            "Customer data sync is important — we want a single customer record in Odoo that "
            "links their Shopify profile, order history, subscription details, and any B2B "
            "relationship if they're also a wholesale customer."
        ),
    ],
}

# Fallback for any domain/question not explicitly covered
DEFAULT_ANSWER = (
    "That's handled fairly standardly for our industry. We follow common practices "
    "for a mid-size Belgian consumer goods company. We'd like Odoo's default "
    "configuration for this area, with the ability to customize later as we learn "
    "what works best for our team."
)


def main():
    print("\n  Starting automated demo interview...")
    print(f"  Server: {BASE}\n")

    # 1. Start session
    try:
        r = requests.post(f"{BASE}/api/start", json={
            "client_name": "PetFresh",
            "industry": "Food & Beverage",
        }, timeout=10)
        r.raise_for_status()
    except requests.ConnectionError:
        print("  Could not connect to server. Start it first:")
        print("    python3 web_interview.py\n")
        sys.exit(1)

    session = r.json()
    session_id = session["session_id"]
    print(f"  Session: {session_id}")
    print(f"  Company: {session['client_name']} ({session['industry']})\n")

    # 2. Loop through questions
    domain_q_index = {}  # track question index per domain
    question_count = 0
    summary = None

    while True:
        # Get next question
        r = requests.get(f"{BASE}/api/question", params={"session_id": session_id})
        data = r.json()

        if data.get("complete"):
            summary = data["summary"]
            print(f"\n  Interview complete! {question_count} questions answered.\n")
            break

        q_id = data.get("id", "")
        phase = data.get("phase", "")
        domain = data.get("domain")
        question_text = data.get("question", "")
        progress = data.get("progress", {})

        # Pick the right answer
        if phase == "scoping":
            # Match by scope ID prefix (handles followups like scope_01_followup_1)
            base_id = q_id.split("_followup")[0]
            answer = SCOPING_ANSWERS.get(base_id, DEFAULT_ANSWER)
            if "_followup" in q_id:
                answer = answer + " We're quite clear on this — happy to elaborate further if needed."
        elif phase == "domain_expert" and domain:
            idx = domain_q_index.get(domain, 0)
            answers = DOMAIN_ANSWERS.get(domain, [])
            if idx < len(answers):
                answer = answers[idx]
            else:
                answer = DEFAULT_ANSWER
            domain_q_index[domain] = idx + 1
        else:
            answer = DEFAULT_ANSWER

        # Show progress
        pct = progress.get("overall_percent", 0)
        phase_label = progress.get("phase", phase)
        bar = "=" * (pct // 5) + "-" * (20 - pct // 5)
        q_short = question_text[:70] + "..." if len(question_text) > 70 else question_text
        print(f"  [{bar}] {pct:3d}%  {phase_label}")
        print(f"    Q: {q_short}")
        print(f"    A: {answer[:80]}...\n")

        # Submit answer
        r = requests.post(f"{BASE}/api/respond", json={
            "session_id": session_id,
            "response": answer,
            "question": {
                "id": q_id,
                "text": question_text,
                "phase": phase,
                "domain": domain,
            }
        })
        question_count += 1

        # Small delay to not overwhelm the LLM-based signal detection
        time.sleep(0.3)

    if not summary:
        print("  Error: no summary returned. Ending manually...")
        r = requests.post(f"{BASE}/api/end", json={"session_id": session_id})
        summary = r.json().get("summary", {})

    # 3. Generate PRD
    print("  Generating implementation PRD...")
    r = requests.post(f"{BASE}/api/generate-prd", json={"summary": summary}, timeout=120)
    prd = r.json()

    if prd.get("error"):
        print(f"  PRD generation error: {prd['error']}")
        print("  (The summary is still saved — you can view it in the browser)\n")
    else:
        md_len = len(prd.get("markdown", ""))
        modules = prd.get("module_count", "?")
        est = prd.get("estimated_minutes", "?")
        print(f"  PRD generated: {md_len} chars, {modules} modules, ~{est} min setup")

        # Save PRD files locally
        company = summary.get("client_name", "company").replace(" ", "-")
        with open(f"outputs/prd-{company}.md", "w") as f:
            f.write(prd["markdown"])
        with open(f"outputs/prd-{company}.json", "w") as f:
            json.dump(prd["json"], f, indent=2)
        print(f"  Saved to outputs/prd-{company}.md and .json")

    print(f"""
  ┌─────────────────────────────────────────────┐
  │  Open http://localhost:5001 in your browser  │
  │  to see the interview result and PRD.        │
  │                                              │
  │  The session is still active — you can also  │
  │  click "Deploy to Odoo" to test the builder. │
  └─────────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
