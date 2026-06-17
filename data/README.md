# Data directory

All dummy / synthetic data for the copilot lives here.

| File / folder | Description | Regenerate with |
|---------------|-------------|-----------------|
| `transactions.csv` | 150 synthetic transaction records (the app's lookup "database") | `python -m src.data_generation.generate_transactions` |
| `complaints.csv` | 100 labeled customer complaints (RAG evaluation only) | `python -m src.data_generation.generate_complaints` |
| `sops/*.md` | 10 Standard Operating Procedure markdown files (knowledge base) | Hand-authored; not generated |

Quick regenerate both CSVs:

```bash
./scripts/regenerate_data.sh
```

Verify everything is present:

```bash
python scripts/verify_data.py
```
