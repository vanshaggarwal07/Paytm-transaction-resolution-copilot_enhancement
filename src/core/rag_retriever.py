"""Retrieve Standard Operating Procedures via semantic search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_SOPS_DIR = Path("data/sops")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Cached embedding index and SOP documents — built once at module load.
_SOP_DOCUMENTS: list[dict[str, str]] = []
_EMBEDDING_MODEL: SentenceTransformer | None = None
_EMBEDDING_INDEX: faiss.IndexFlatIP | None = None


def _parse_issue_name(markdown_text: str, file_path: Path) -> str:
    """Extract the issue title from the first markdown heading."""
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    raise ValueError(f"No issue heading found in SOP file: {file_path}")


def _load_sop_documents(sops_dir: Path = DEFAULT_SOPS_DIR) -> list[dict[str, str]]:
    """Load all SOP markdown files from disk."""
    if not sops_dir.is_dir():
        raise FileNotFoundError(f"SOP directory not found: {sops_dir}")

    sop_paths = sorted(sops_dir.glob("*.md"))
    if not sop_paths:
        raise ValueError(f"No SOP markdown files found in {sops_dir}")

    documents: list[dict[str, str]] = []
    for path in sop_paths:
        try:
            content = path.read_text(encoding="utf-8")
            issue_name = _parse_issue_name(content, path)
            documents.append(
                {
                    "issue_name": issue_name,
                    "file_path": str(path),
                    "content": content,
                }
            )
        except OSError as exc:
            logger.error("Failed to read SOP file %s: %s", path, exc)
            raise OSError(f"Failed to read SOP file {path}: {exc}") from exc

    return documents


def _build_embedding_index(
    documents: list[dict[str, str]],
    model_name: str = EMBEDDING_MODEL_NAME,
) -> tuple[SentenceTransformer, faiss.IndexFlatIP]:
    """Embed SOP texts and build a normalized inner-product FAISS index."""
    try:
        model = SentenceTransformer(model_name)
        texts = [document["content"] for document in documents]
        embeddings = model.encode(texts, normalize_embeddings=True)
        embedding_matrix = np.asarray(embeddings, dtype=np.float32)

        index = faiss.IndexFlatIP(embedding_matrix.shape[1])
        index.add(embedding_matrix)
        logger.info("Built FAISS index with %s SOP documents", len(documents))
        return model, index
    except Exception as exc:
        logger.error("Failed to build embedding index: %s", exc)
        raise RuntimeError(f"Failed to build embedding index: {exc}") from exc


def _initialize_retriever(sops_dir: Path = DEFAULT_SOPS_DIR) -> None:
    """Load SOP documents and build the cached retriever state."""
    global _SOP_DOCUMENTS, _EMBEDDING_MODEL, _EMBEDDING_INDEX

    if _EMBEDDING_INDEX is not None:
        return

    documents = _load_sop_documents(sops_dir)
    model, index = _build_embedding_index(documents)
    _SOP_DOCUMENTS = documents
    _EMBEDDING_MODEL = model
    _EMBEDDING_INDEX = index


def retrieve_sop(query: str, top_k: int = 1) -> list[dict[str, Any]]:
    """Return the top matching SOP documents for a natural-language query."""
    if not query.strip():
        raise ValueError("Query must not be empty")

    try:
        _initialize_retriever()
    except (FileNotFoundError, ValueError, OSError, RuntimeError):
        raise

    assert _EMBEDDING_MODEL is not None
    assert _EMBEDDING_INDEX is not None

    try:
        query_embedding = _EMBEDDING_MODEL.encode([query], normalize_embeddings=True)
        query_matrix = np.asarray(query_embedding, dtype=np.float32)
        scores, indices = _EMBEDDING_INDEX.search(query_matrix, top_k)

        results: list[dict[str, Any]] = []
        for rank, doc_index in enumerate(indices[0]):
            if doc_index < 0:
                continue
            document = _SOP_DOCUMENTS[doc_index]
            results.append(
                {
                    "issue_name": document["issue_name"],
                    "file_path": document["file_path"],
                    "content": document["content"],
                }
            )
        return results
    except Exception as exc:
        logger.error("SOP retrieval failed for query %r: %s", query, exc)
        raise RuntimeError(f"SOP retrieval failed: {exc}") from exc


_initialize_retriever()
