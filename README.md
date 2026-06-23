# Paytm Transaction Resolution Copilot

A GenAI support copilot prototype that helps payment-support agents resolve disputes. It combines three layers:

1. **Rule engine** — reads synthetic transaction CSV data and deterministically identifies the issue type.
2. **RAG retriever** — embeds SOP markdown files with `sentence-transformers` and retrieves the best match via FAISS.
3. **LLM explainer** — uses Google Gemini to explain what happened and recommend next steps, grounded only in transaction facts and the retrieved SOP.

The LLM never decides transaction status or issue type — that is always the rule engine's job.

## Architecture

```
Agent UI (Streamlit)  →  POST /resolve  →  FastAPI
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
           transaction_lookup          issue_rules              rag_retriever
           (data/transactions.csv)      (deterministic)          (data/sops/*.md)
                                              │                         │
                                              └──────────┬──────────────┘
                                                         ▼
                                                  llm_generator
                                                  (Gemini via google-genai)
```

**Request flow:** lookup transaction by MID + Order ID + Customer ID → identify issue → retrieve SOP by issue name → generate grounded agent response → return JSON to the UI.

## Prerequisites

- Python 3.11 recommended (3.9+ works; project was tested on 3.9)
- A [Google AI Studio](https://aistudio.google.com) API key for Gemini

## Install

```bash
cd paytm-copilot
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Environment setup

Create or edit `.env` in the project root:

```env
GEMINI_API_KEY=your_key_here
```

Replace `your_key_here` with your real key from [Google AI Studio](https://aistudio.google.com). The `google-genai` client reads `GEMINI_API_KEY` from the environment automatically — never hardcode the key in source files.

If the key is missing, the API and UI still run, but `/resolve` returns the LLM fallback message instead of a full generated response.

## Generate synthetic data

Transaction and complaint CSVs are not committed to git. Generate them before running the demo:

```bash
source .venv/bin/activate
export PYTHONPATH=.

# Both CSVs in one command:
./scripts/regenerate_data.sh

# Or individually:
python -m src.data_generation.generate_transactions   # 150 rows
python -m src.data_generation.generate_complaints     # 100 rows

# Verify everything is present:
python scripts/verify_data.py
```

This writes:

- `data/transactions.csv` — synthetic transaction "database" (150 rows)
- `data/complaints.csv` — labeled complaint evaluation set (100 rows)

SOP markdown files are already in `data/sops/` (10 files, not generated).

> **Note:** Regenerated CSVs are written to `data/` after running the generate scripts above.

## Run the demo (one command)

```bash
chmod +x run_demo.sh   # first time only
./run_demo.sh
```

This activates the venv, starts FastAPI on **http://localhost:8000** in the background, then starts Streamlit on **http://localhost:8501**. Press `Ctrl+C` to stop both.

## Run API and UI separately

**Terminal 1 — API:**

```bash
source .venv/bin/activate
export PYTHONPATH=.
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — UI:**

```bash
source .venv/bin/activate
export PYTHONPATH=.
streamlit run src/ui/app.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501). Try a sample transaction:

| Field | Value | Expected issue |
|-------|-------|----------------|
| MID | `MID000002` | `Settlement Delay` |
| Order ID | `ORD000002` | |
| Customer ID | `CUST000002` | |

Or for **Amount Debited but Merchant Not Credited**, use `MID000010` / `ORD000010` / `CUST000010`.

> Transaction field values are randomized each time you run `./scripts/regenerate_data.sh`, but IDs stay sequential (`ORD000001`…`ORD000150`).

**Health check:**

```bash
curl http://localhost:8000/health
```

## Run tests

```bash
source .venv/bin/activate
export PYTHONPATH=.
pytest tests/ -v
```

## Evaluate RAG retrieval

```bash
python -m src.core.evaluate_retrieval
```

## Project layout

```
data/
  transactions.csv          # generated
  complaints.csv            # generated
  sops/*.md                 # SOP knowledge base
src/
  issue_taxonomy.py         # single source of truth for issue names
  core/                     # lookup, rules, RAG, LLM, eval
  api/main.py               # FastAPI /resolve endpoint
  ui/app.py                 # Streamlit agent UI
  data_generation/          # synthetic data scripts
tests/
```
