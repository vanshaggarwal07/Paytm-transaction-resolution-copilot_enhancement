"""Persistent CSV logging for resolutions and agent feedback."""

from __future__ import annotations

import csv
import fcntl
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.core.graph_state import CopilotState
from src.core.transaction_lookup import lookup_transaction

logger = logging.getLogger(__name__)

_LOG_LOCK = threading.Lock()

RESOLUTION_LOG_PATH = Path("data/resolution_log.csv")
FEEDBACK_LOG_PATH = Path("data/feedback_log.csv")
RESOLVED_CASES_PATH = Path("data/resolved_cases.csv")

RESOLUTION_LOG_HEADERS: tuple[str, ...] = (
    "RESOLUTION_ID",
    "TIMESTAMP",
    "MID",
    "ORDER_ID",
    "CUST_ID",
    "ISSUE",
    "COMPLAINT_TEXT",
    "AGENT_ANSWERS",
    "SOP_SOURCE",
    "ESCALATION_REQUIRED",
    "ESCALATION_TEAM",
    "GROUNDEDNESS_VERIFIED",
    "RESPONSE_TEXT",
    "CASE_NOTE",
)

FEEDBACK_LOG_HEADERS: tuple[str, ...] = (
    "FEEDBACK_ID",
    "RESOLUTION_ID",
    "TIMESTAMP",
    "RATING",
    "COMMENT",
)

RESOLVED_CASE_HEADERS: tuple[str, ...] = (
    "CASE_ID",
    "ISSUE",
    "COMPLAINT",
    "RESOLUTION_SUMMARY",
    "OUTCOME",
    "AGE_HOURS",
    "PAYMENT_MODE",
    "TXN_AMOUNT",
    "RESOLUTION_TIMESTAMP",
    "RATING",
)


def _append_csv_row(path: Path, headers: tuple[str, ...], row: dict[str, Any]) -> None:
    """Append one CSV row with module and file locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.is_file() and path.stat().st_size > 0

    with _LOG_LOCK:
        with path.open("a", newline="", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass

            writer = csv.DictWriter(handle, fieldnames=list(headers))
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass


def log_resolution(state: CopilotState) -> str:
    """Persist a successful resolution and return its RESOLUTION_ID."""
    resolution_id = str(uuid.uuid4())
    reconciliation = state.get("reconciliation") or {}
    sop = state.get("sop") or {}
    escalation = state.get("escalation") or {}
    groundedness = state.get("groundedness") or {}

    issue = reconciliation.get("primary_issue") or state.get("rule_based_issue") or ""
    sop_source = Path(sop["file_path"]).name if sop.get("file_path") else ""
    escalation_team = escalation.get("escalation_team")
    groundedness_verified = groundedness.get("verified")

    row = {
        "RESOLUTION_ID": resolution_id,
        "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
        "MID": state["mid"],
        "ORDER_ID": state["order_id"],
        "CUST_ID": state["cust_id"],
        "ISSUE": issue,
        "COMPLAINT_TEXT": state.get("complaint_text") or "",
        "AGENT_ANSWERS": state.get("agent_answers") or "",
        "SOP_SOURCE": sop_source,
        "ESCALATION_REQUIRED": str(bool(escalation.get("escalation_required"))),
        "ESCALATION_TEAM": escalation_team if escalation_team is not None else "",
        "GROUNDEDNESS_VERIFIED": (
            "" if groundedness_verified is None else str(groundedness_verified)
        ),
        "RESPONSE_TEXT": state.get("response_text") or "",
        "CASE_NOTE": state.get("case_note") or "",
    }
    _append_csv_row(RESOLUTION_LOG_PATH, RESOLUTION_LOG_HEADERS, row)
    logger.info("Logged resolution %s for ORDER_ID=%s", resolution_id, state["order_id"])
    return resolution_id


def get_resolution_by_id(resolution_id: str) -> Optional[dict[str, str]]:
    """Return a resolution log row by RESOLUTION_ID, or None when missing."""
    if not RESOLUTION_LOG_PATH.is_file():
        return None

    with _LOG_LOCK:
        with RESOLUTION_LOG_PATH.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("RESOLUTION_ID") == resolution_id:
                    return row
    return None


def log_feedback(resolution_id: str, rating: str, comment: str = "") -> str:
    """Append agent feedback for a prior resolution and return FEEDBACK_ID."""
    feedback_id = str(uuid.uuid4())
    row = {
        "FEEDBACK_ID": feedback_id,
        "RESOLUTION_ID": resolution_id,
        "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
        "RATING": rating,
        "COMMENT": comment,
    }
    _append_csv_row(FEEDBACK_LOG_PATH, FEEDBACK_LOG_HEADERS, row)
    logger.info("Logged feedback %s for resolution %s", feedback_id, resolution_id)
    return feedback_id


def _parse_bool(value: str) -> bool:
    """Parse a boolean string from CSV."""
    return str(value).strip().lower() in {"true", "1", "yes"}


def _next_case_id() -> str:
    """Generate the next CASE_ID for resolved_cases.csv."""
    if not RESOLVED_CASES_PATH.is_file():
        return "CASE000001"

    dataframe = pd.read_csv(RESOLVED_CASES_PATH)
    if dataframe.empty:
        return "CASE000001"

    max_number = max(
        int(str(case_id).replace("CASE", ""))
        for case_id in dataframe["CASE_ID"]
    )
    return f"CASE{max_number + 1:06d}"


def _outcome_from_resolution(resolution_row: dict[str, str]) -> str:
    """Infer resolved-case OUTCOME from escalation fields in the resolution log."""
    if _parse_bool(resolution_row.get("ESCALATION_REQUIRED", "")):
        return "Escalated - Review Required"
    return "Resolved - Copilot Assisted"


def append_helpful_resolved_case(resolution_row: dict[str, str]) -> str:
    """Append a helpful agent-validated case to resolved_cases.csv."""
    transaction = lookup_transaction(
        resolution_row["MID"],
        resolution_row["ORDER_ID"],
        resolution_row["CUST_ID"],
    )

    age_hours = transaction.get("AGE_HOURS", 0) if transaction else 0
    payment_mode = transaction.get("PAYMENT_MODE", "UPI") if transaction else "UPI"
    txn_amount = transaction.get("TXN_AMOUNT", 0.0) if transaction else 0.0

    case_id = _next_case_id()
    row = {
        "CASE_ID": case_id,
        "ISSUE": resolution_row.get("ISSUE", ""),
        "COMPLAINT": resolution_row.get("COMPLAINT_TEXT", ""),
        "RESOLUTION_SUMMARY": resolution_row.get("CASE_NOTE", ""),
        "OUTCOME": _outcome_from_resolution(resolution_row),
        "AGE_HOURS": age_hours,
        "PAYMENT_MODE": payment_mode,
        "TXN_AMOUNT": txn_amount,
        "RESOLUTION_TIMESTAMP": resolution_row.get("TIMESTAMP", ""),
        "RATING": "helpful",
    }
    _append_csv_row(RESOLVED_CASES_PATH, RESOLVED_CASE_HEADERS, row)
    logger.info("Appended helpful resolved case %s from resolution %s", case_id, resolution_row["RESOLUTION_ID"])
    return case_id


def feedback_summary() -> dict[str, Any]:
    """Return aggregate stats from resolution, feedback, and resolved-case logs."""
    resolution_count = 0
    if RESOLUTION_LOG_PATH.is_file():
        resolution_count = max(0, sum(1 for _ in RESOLUTION_LOG_PATH.open(encoding="utf-8")) - 1)

    feedback_rows: list[dict[str, str]] = []
    if FEEDBACK_LOG_PATH.is_file():
        with FEEDBACK_LOG_PATH.open(newline="", encoding="utf-8") as handle:
            feedback_rows = list(csv.DictReader(handle))

    helpful_feedback = sum(1 for row in feedback_rows if row.get("RATING") == "helpful")
    not_helpful_feedback = sum(1 for row in feedback_rows if row.get("RATING") == "not_helpful")

    resolved_df = (
        pd.read_csv(RESOLVED_CASES_PATH)
        if RESOLVED_CASES_PATH.is_file()
        else pd.DataFrame(columns=list(RESOLVED_CASE_HEADERS))
    )
    helpful_cases = (
        int((resolved_df["RATING"] == "helpful").sum())
        if not resolved_df.empty and "RATING" in resolved_df.columns
        else 0
    )
    feedback_grown_cases = 0
    if not resolved_df.empty and "CASE_ID" in resolved_df.columns:
        numeric_ids = resolved_df["CASE_ID"].astype(str).str.replace("CASE", "", regex=False)
        feedback_grown_cases = int((numeric_ids.astype(int) > 50).sum())

    return {
        "total_resolutions_logged": resolution_count,
        "total_feedback_entries": len(feedback_rows),
        "helpful_feedback": helpful_feedback,
        "not_helpful_feedback": not_helpful_feedback,
        "helpful_cases_in_resolved_cases_csv": helpful_cases,
        "cases_added_via_helpful_feedback": feedback_grown_cases,
        "latest_feedback": feedback_rows[-1] if feedback_rows else None,
    }
