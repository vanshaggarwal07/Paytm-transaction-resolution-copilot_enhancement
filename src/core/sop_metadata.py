"""Parse structured metadata from SOP markdown frontmatter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Tuple

FRONTMATTER_DELIMITER = "---"


def _parse_scalar(value: str) -> Any:
    """Parse a single YAML-style scalar from frontmatter."""
    stripped = value.strip()
    if stripped.lower() == "null":
        return None
    if stripped.lower() == "true":
        return True
    if stripped.lower() == "false":
        return False
    if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
        return int(stripped)
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1]
    return stripped


def _parse_frontmatter_block(raw: str) -> dict[str, Any]:
    """Parse a simple YAML frontmatter block into a dictionary."""
    metadata: dict[str, Any] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = _parse_scalar(value)
    return metadata


def split_sop_markdown(markdown_text: str) -> Tuple[dict[str, Any], str]:
    """Return frontmatter metadata and the markdown body without frontmatter."""
    if not markdown_text.startswith(f"{FRONTMATTER_DELIMITER}\n"):
        return {}, markdown_text

    try:
        _, frontmatter_raw, body = markdown_text.split(FRONTMATTER_DELIMITER, 2)
    except ValueError:
        return {}, markdown_text

    return _parse_frontmatter_block(frontmatter_raw), body.lstrip("\n")


def load_sop_metadata(file_path: str) -> dict[str, Any]:
    """Parse and return only the frontmatter from an SOP file."""
    path = Path(file_path)
    try:
        markdown_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Failed to read SOP file {path}: {exc}") from exc

    metadata, _ = split_sop_markdown(markdown_text)
    if not metadata:
        raise ValueError(f"No YAML frontmatter found in SOP file: {path}")
    return metadata


def parse_issue_name(markdown_text: str, file_path: Optional[Path] = None) -> str:
    """Extract the issue title from frontmatter or the first markdown heading."""
    metadata, body = split_sop_markdown(markdown_text)
    issue = metadata.get("issue")
    if isinstance(issue, str) and issue.strip():
        return issue.strip()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()

    location = file_path or "SOP markdown"
    raise ValueError(f"No issue heading found in SOP file: {location}")
