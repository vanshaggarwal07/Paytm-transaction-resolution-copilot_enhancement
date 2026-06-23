"""Retrieve Standard Operating Procedures via semantic search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from src.core.hybrid_scorer import compute_hybrid_scores
from src.core.sop_metadata import load_sop_metadata, parse_issue_name, split_sop_markdown

logger = logging.getLogger(__name__)

DEFAULT_SOPS_DIR = Path("data/sops")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
HYBRID_CANDIDATE_POOL_SIZE = 10

# Cached embedding index and SOP documents — built once at module load.
_SOP_DOCUMENTS: list[dict[str, str]] = []
_EMBEDDING_MODEL: SentenceTransformer | None = None
_EMBEDDING_INDEX: faiss.IndexFlatIP | None = None


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
            raw_content = path.read_text(encoding="utf-8")
            _, body = split_sop_markdown(raw_content)
            issue_name = parse_issue_name(raw_content, path)
            documents.append(
                {
                    "issue_name": issue_name,
                    "file_path": str(path),
                    "content": body,
                    "embedding_text": body,
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
        texts = [document["embedding_text"] for document in documents]
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


def _search_sop_index(query: str, top_k: int) -> tuple[list[int], list[float]]:
    """Run FAISS search and return document indices with cosine similarity scores."""
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

        doc_indices: list[int] = []
        doc_scores: list[float] = []
        for rank, doc_index in enumerate(indices[0]):
            if doc_index < 0:
                continue
            doc_indices.append(int(doc_index))
            doc_scores.append(float(scores[0][rank]))
        return doc_indices, doc_scores
    except Exception as exc:
        logger.error("SOP retrieval failed for query %r: %s", query, exc)
        raise RuntimeError(f"SOP retrieval failed: {exc}") from exc


def retrieve_sop(query: str, top_k: int = 1) -> list[dict[str, Any]]:
    """Return the top matching SOP documents for a natural-language query."""
    doc_indices, _scores = _search_sop_index(query, top_k)

    results: list[dict[str, Any]] = []
    for doc_index in doc_indices:
        document = _SOP_DOCUMENTS[doc_index]
        results.append(
            {
                "issue_name": document["issue_name"],
                "file_path": document["file_path"],
                "content": document["content"],
            }
        )
    return results


def retrieve_sop_hybrid(
    query: str,
    extracted_intents: list[dict[str, Any]],
    transaction: dict[str, Any],
    top_k: int = 1,
) -> list[dict[str, Any]]:
    """Return top SOPs after FAISS candidate retrieval and hybrid re-ranking."""
    doc_indices, semantic_scores = _search_sop_index(query, HYBRID_CANDIDATE_POOL_SIZE)

    candidates: list[dict[str, Any]] = []
    for doc_index in doc_indices:
        document = _SOP_DOCUMENTS[doc_index]
        candidates.append(
            {
                "issue_name": document["issue_name"],
                "file_path": document["file_path"],
                "content": document["content"],
                "sop_metadata": load_sop_metadata(document["file_path"]),
            }
        )

    ranked = compute_hybrid_scores(
        candidates=candidates,
        semantic_scores=semantic_scores,
        extracted_intents=extracted_intents,
        transaction=transaction,
    )
    return ranked[:top_k]


_initialize_retriever()
