"""Simulate the final UI demo flow via API calls and print each screen state."""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw

API_BASE = "http://localhost:8000"
CONFLICT_COMPLAINT = (
    "The card issuer raised a chargeback dispute on a previously successful "
    "transaction. The merchant reports a reversal debit from their settlement "
    "account and the customer claims an unauthorised transaction."
)
AGENT_ANSWERS = (
    "The customer confirmed the transaction was authorised — this is a "
    "settlement delay issue, not a dispute."
)


def _banner(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def _render_ui_state(label: str, payload: dict, *, complaint_provided: bool = True) -> None:
    """Print a text representation of render_resolution() panels."""
    _banner(label)

    if payload.get("status") == "clarification_needed":
        print("UI PHASE: clarification")
        print("Header: The assistant needs more information")
        for index, question in enumerate(payload.get("clarifying_questions") or [], start=1):
            print(f"  Q{index}. {question}")
        print("Actions: [Submit answers] [Start over]")
        return

    primary_issue = payload.get("primary_issue") or payload.get("issue", "Unknown")
    print(f"PRIMARY ISSUE: {primary_issue}")

    escalation_required = payload.get("escalation_required")
    if escalation_required is True:
        print("BADGE: [Escalation Required]")
    elif escalation_required is False:
        print("BADGE: [No Escalation Required]")
    else:
        print("BADGE: [Escalation Unknown]")

    if complaint_provided:
        if payload.get("conflict"):
            print("INTENT PANEL: [Signal conflict detected]")
        elif payload.get("unresolved_intents"):
            print("INTENT PANEL: [Primary confirmed] + secondary signals")
        else:
            print("INTENT PANEL: [All signals aligned]")
        if payload.get("reconciliation_note"):
            print(f"  Note: {payload['reconciliation_note']}")

    verified = payload.get("groundedness_verified")
    if verified is True:
        print("GROUNDEDNESS: [Verified]")
    elif verified is False:
        print("GROUNDEDNESS: [Flagged — review unsupported claims]")
        for claim in payload.get("unsupported_claims") or []:
            print(f"  - {claim}")
    else:
        print("GROUNDEDNESS: [Could not verify]")

    response_text = payload.get("response", "")
    print("\nAGENT RESPONSE (excerpt):")
    print(textwrap.shorten(response_text.replace("\n", " "), width=240, placeholder="..."))

    print(f"\nSOP source: {payload.get('sop_source', 'unknown')}")
    scores = payload.get("retrieval_scores") or {}
    print(
        "RETRIEVAL EXPANDER: "
        f"semantic={scores.get('semantic', 0):.3f}, "
        f"intent={scores.get('intent', 0):.3f}, "
        f"structural={scores.get('structural', 0):.3f}"
    )

    print("\nCASE NOTE (excerpt):")
    print(textwrap.shorten(payload.get("case_note", ""), width=240, placeholder="..."))

    customer_reply = payload.get("customer_reply", "")
    print("\nCUSTOMER-FACING REPLY DRAFT:")
    print(customer_reply or "(empty)")

    similar_cases = payload.get("similar_cases") or []
    if similar_cases:
        print("\nSIMILAR RESOLVED CASES:")
        for case in similar_cases:
            score = round(float(case.get("similarity_score", 0.0)) * 100)
            print(
                f"  ▸ {case.get('ISSUE')} — {case.get('OUTCOME')} "
                f"(Match: {score}%) [{case.get('CASE_ID')}]"
            )
    else:
        print("\nSIMILAR RESOLVED CASES: (section hidden — no matches)")

    resolution_id = payload.get("resolution_id")
    print("\nFEEDBACK SECTION:")
    if resolution_id:
        print(f"  resolution_id: {resolution_id}")
        print("  Buttons: [👍 Helpful] [👎 Not Helpful]")
        print("  Input: Add a comment (optional)")
        print("  Action: [Submit feedback]")
    else:
        print("  Feedback unavailable for this session")


def _build_demo_png() -> bytes:
    image = Image.new("RGB", (800, 400), color="white")
    draw = ImageDraw.Draw(image)
    text = (
        "MID: MID000042  ORDER_ID: ORD000042  CUST_ID: CUST000042\n"
        "Amount: ₹1,499  Mode: UPI  Status: Success"
    )
    draw.text((20, 180), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    health = requests.get(f"{API_BASE}/health", timeout=30).json()
    print("API health:", json.dumps(health))

    _banner("SCREEN 1 — Manual input submitted (conflict complaint)")
    print("Mode: Manual Input")
    print("MID000002 / ORD000002 / CUST000002")
    print(f"Complaint: {CONFLICT_COMPLAINT}")

    step1 = requests.post(
        f"{API_BASE}/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": CONFLICT_COMPLAINT,
        },
        timeout=120,
    )
    step1.raise_for_status()
    clarify_payload = step1.json()
    _render_ui_state("SCREEN 2 — Clarification needed", clarify_payload)

    _banner("SCREEN 3 — Agent submits clarification answers")
    print(f"Agent answers: {AGENT_ANSWERS}")

    step2 = requests.post(
        f"{API_BASE}/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": CONFLICT_COMPLAINT,
            "agent_answers": AGENT_ANSWERS,
        },
        timeout=120,
    )
    step2.raise_for_status()
    resolution_payload = step2.json()
    _render_ui_state("SCREEN 4 — Full resolution panels", resolution_payload)

    resolution_id = resolution_payload["resolution_id"]
    _banner("SCREEN 5 — Agent clicks 👍 Helpful and submits feedback")
    feedback = requests.post(
        f"{API_BASE}/feedback",
        json={
            "resolution_id": resolution_id,
            "rating": "helpful",
            "comment": "Clear guidance for the settlement delay case.",
        },
        timeout=30,
    )
    feedback.raise_for_status()
    print("Feedback response:", json.dumps(feedback.json(), indent=2))
    print('UI replaces feedback section with: "Thank you — your feedback helps improve the copilot."')

    demo_png_path = Path("data/demo_test_dashboard.png")
    demo_png_path.parent.mkdir(parents=True, exist_ok=True)
    demo_png_path.write_bytes(_build_demo_png())

    _banner("SCREEN 6 — Upload Screenshot mode")
    print("Mode: Upload Screenshot")
    print(f"Uploaded: {demo_png_path}")

    extract = requests.post(
        f"{API_BASE}/extract-image",
        files={"file": ("dashboard.png", demo_png_path.read_bytes(), "image/png")},
        timeout=120,
    )
    extract.raise_for_status()
    extraction = extract.json()
    print("Extracted pre_populated:", extraction.get("pre_populated"))
    if extraction.get("extraction_warning"):
        print("Warning:", extraction["extraction_warning"])

    _banner("SCREEN 7 — Agent corrects identifiers and resolves")
    print("Corrected to: MID000002 / ORD000002 / CUST000002")
    print("Complaint: Settlement still pending on merchant dashboard.")

    step3 = requests.post(
        f"{API_BASE}/resolve",
        json={
            "mid": "MID000002",
            "order_id": "ORD000002",
            "cust_id": "CUST000002",
            "complaint": "Settlement still pending on merchant dashboard.",
        },
        timeout=120,
    )
    step3.raise_for_status()
    upload_resolution = step3.json()
    _render_ui_state("SCREEN 8 — Upload mode full resolution panels", upload_resolution)


if __name__ == "__main__":
    main()
