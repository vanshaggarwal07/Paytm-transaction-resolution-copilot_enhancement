# Paytm Transaction Resolution Copilot

## What This Is

The Paytm Transaction Resolution Copilot is a multi-portal GenAI platform that helps customers, support agents, and merchants resolve payment disputes with grounded, auditable recommendations. Unlike a simple chatbot that freely invents answers, this system separates **deterministic decision-making** (transaction lookup, issue classification, escalation) from **generative explanation** (Gemini-powered responses constrained by transaction facts, SOP guidance, and historical cases). Each persona gets a dedicated Streamlit portal, all routed through a shared FastAPI resolution engine orchestrated by a LangGraph workflow.

## Architecture

The copilot enforces a three-tier grounding hierarchy:

1. **Transaction Facts (Priority 1)** — Structured CSV fields (`TXN_STATUS`, `MERCHANT_CREDITED`, `SETTLEMENT_STATUS`, etc.) are the authoritative source of truth. The rule engine reads these deterministically; the LLM never overrides them.
2. **SOP Guidance (Priority 2)** — Standard Operating Procedures in `data/sops/*.md` provide procedural next steps. Structured metadata (escalation thresholds, required fields, teams) is parsed separately from prose so escalation rules remain deterministic.
3. **Historical Cases (Priority 3)** — Previously resolved cases from `data/resolved_cases.csv` offer supporting context via semantic retrieval, but they are never treated as ground truth.

**Why escalation is deterministic:** Escalation thresholds (e.g., settlement delay > 48 hours) are encoded in SOP metadata and evaluated by `escalation_rules.py` against transaction age and status. The LLM explains *why* escalation is needed but cannot decide *whether* to escalate — that prevents hallucinated urgency from triggering incorrect handoffs.

```
Customer / Agent / Merchant
            │
            ▼
   Landing Page (Port 8500)
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
Customer  Agent   Merchant
 Portal   Portal   Portal
 :8502    :8501    :8503
   │        │        │
   └────────┼────────┘
            ▼
  FastAPI Resolution Engine (Port 8000)
            │
            ▼
      LangGraph Workflow
            │
   ┌────────┼────────────────────────────────────┐
   ▼        ▼        ▼        ▼        ▼          ▼
lookup → identify_issue → reconcile → router ──→ clarify
                              │                    (END)
                              ▼
                          retrieve (hybrid RAG)
                              │
                              ▼
                          generate (Gemini)
                              │
                              ▼
                          escalate (rule engine)
                              │
                              ▼
                          verify (groundedness check)
                              │
                              ▼
                            END
```

## Personas

**Customer** (`customer_portal.py`, port 8502) — Authenticated customers view their transaction history, submit complaints, and receive AI-generated resolution updates tied to the `/resolve` endpoint.

**Support Agent** (`app.py`, port 8501) — Agents enter transaction identifiers manually or via screenshot extraction, resolve disputes through a two-phase clarify-then-resolve flow, review SOP-grounded responses, and submit feedback that feeds back into the case history.

**Merchant** (`merchant_portal.py`, port 8503) — Merchants monitor settlement health, flagged transactions, issue breakdowns, and operational alerts for their MID without access to customer PII beyond their own transaction scope.

## Key Design Decisions

- **Escalation lives in the rule engine, not the LLM.** Thresholds are parsed from SOP YAML frontmatter and evaluated against transaction age. The LLM narrates the escalation; it cannot trigger one spuriously.
- **Structured SOP metadata is separated from prose.** Escalation teams, thresholds, and required documentation fields are machine-readable so the pipeline can enforce policy without parsing free-text SOPs at runtime.
- **The LangGraph pipeline has a clarification branch.** When the rule engine and complaint-derived intents conflict, or confidence is too low, the graph routes to `clarify` instead of generating a premature resolution — preventing wrong-issue responses on ambiguous complaints.
- **Hybrid retrieval (semantic + intent + structural) beats semantic-only.** FAISS provides candidate SOPs; a hybrid scorer re-ranks using complaint intent signals and transaction field alignment, fixing cases where embedding similarity alone picks the wrong SOP.
- **Historical cases are supporting evidence, not ground truth.** Similar resolved cases are injected into the LLM prompt as reference material with explicit framing — they inform tone and precedent but cannot override transaction facts or SOP procedures.
- **Each persona gets their own Streamlit portal rather than one app with role switching.** Separate portals allow independent UX, authentication, and accent styling per audience while sharing a single resolution backend — simpler to demo and easier to permission in production.

## Evaluation Results

Run on the 100-complaint labeled evaluation set (`data/complaints.csv`):

```bash
python src/core/evaluate_retrieval.py
```

| Metric | Result |
|--------|--------|
| Semantic-only retrieval precision@1 | **79.0%** (79/100) |
| Intent extraction hit rate | **97.0%** (97/100) |
| Hybrid retrieval precision@1 | **89.0%** (89/100) |
| Delta (hybrid − semantic) | **+10.0 percentage points** |

Hybrid retrieval fixed 10 cases where semantic-only picked the wrong top-1 SOP, with zero regressions on this evaluation set.

## Setup

### Environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_key_here
```

Obtain a key from [Google AI Studio](https://aistudio.google.com). Never commit the actual key to source control.

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Generate synthetic data

Run in order (requires `PYTHONPATH=.` or run from project root with venv active):

```bash
export PYTHONPATH=.
python src/data_generation/generate_transactions.py
python src/data_generation/generate_complaints.py
python src/data_generation/generate_case_history.py
python src/data_generation/generate_customers.py
python src/data_generation/generate_merchants.py
```

Verify with:

```bash
python scripts/verify_data.py
```

SOP markdown files in `data/sops/` are committed and not generated.

## Running the Platform

**One command (all five services):**

```bash
chmod +x run_demo.sh   # first time only
./run_demo.sh
```

| Service | URL |
|---------|-----|
| Landing Page | http://localhost:8500 |
| Agent Portal | http://localhost:8501 |
| Customer Portal | http://localhost:8502 |
| Merchant Portal | http://localhost:8503 |
| API docs | http://localhost:8000/docs |

Press `Ctrl+C` to stop all services.

**Manual (five terminals):**

```bash
source .venv/bin/activate && export PYTHONPATH=.

# Terminal 1 — API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Landing
streamlit run src/ui/landing.py --server.port 8500 --server.headless true

# Terminal 3 — Agent
streamlit run src/ui/app.py --server.port 8501 --server.headless true

# Terminal 4 — Customer
streamlit run src/ui/customer_portal.py --server.port 8502 --server.headless true

# Terminal 5 — Merchant
streamlit run src/ui/merchant_portal.py --server.port 8503 --server.headless true
```

## Running Tests

```bash
source .venv/bin/activate
export PYTHONPATH=.
pytest tests/ -v
```

**Current passing count: 100 / 100**

## Tech Stack

Python 3.11, FastAPI, LangGraph, Gemini (`google-genai`), `sentence-transformers`, FAISS, Streamlit, pandas, pytest.
