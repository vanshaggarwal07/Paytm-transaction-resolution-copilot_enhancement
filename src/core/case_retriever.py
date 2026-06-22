"""Retrieve historically resolved cases via semantic search."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_CASES_PATH = Path("data/resolved_cases.csv")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
SIMILARITY_THRESHOLD = 0.4

# Cached embedding index and resolved-case metadata — built lazily on first search.
CASE_METADATA: list[dict[str, Any]] = []
CASE_INDEX: faiss.IndexFlatIP | None = None
_CASE_EMBEDDING_MODEL: SentenceTransformer | None = None
_CASE_RETRIEVER_UNAVAILABLE = False


def _build_search_text(issue: str, complaint: str, resolution_summary: str) -> str:
    """Construct the text embedded for each historical case."""
    return f"{issue}: {complaint} Resolution: {resolution_summary}"


def _load_case_documents(
    cases_path: Path = DEFAULT_CASES_PATH,
) -> list[dict[str, Any]]:
    """Load helpful resolved cases from CSV and attach search_text."""
    if not cases_path.is_file():
        raise FileNotFoundError(f"Resolved cases file not found: {cases_path}")

    dataframe = pd.read_csv(cases_path)
    required_columns = {
        "CASE_ID",
        "ISSUE",
        "COMPLAINT",
        "RESOLUTION_SUMMARY",
        "OUTCOME",
        "RATING",
    }
    missing = required_columns - set(dataframe.columns)
    if missing:
        raise ValueError(f"Resolved cases CSV missing columns: {sorted(missing)}")

    helpful_cases = dataframe[dataframe["RATING"] == "helpful"].copy()
    if helpful_cases.empty:
        raise ValueError("No helpful resolved cases available to index")

    documents: list[dict[str, Any]] = []
    for row in helpful_cases.to_dict(orient="records"):
        issue = str(row["ISSUE"])
        complaint = str(row["COMPLAINT"])
        resolution_summary = str(row["RESOLUTION_SUMMARY"])
        documents.append(
            {
                "CASE_ID": str(row["CASE_ID"]),
                "ISSUE": issue,
                "COMPLAINT": complaint,
                "RESOLUTION_SUMMARY": resolution_summary,
                "OUTCOME": str(row["OUTCOME"]),
                "RATING": str(row["RATING"]),
                "search_text": _build_search_text(issue, complaint, resolution_summary),
            }
        )

    logger.info(
        "Loaded %s helpful resolved cases from %s (%s total rows)",
        len(documents),
        cases_path,
        len(dataframe),
    )
    return documents


def _build_case_index(
    documents: list[dict[str, Any]],
    model_name: str = EMBEDDING_MODEL_NAME,
) -> tuple[SentenceTransformer, faiss.IndexFlatIP]:
    """Embed case search_text values and build a normalized inner-product FAISS index."""
    try:
        model = SentenceTransformer(model_name)
        texts = [document["search_text"] for document in documents]
        embeddings = model.encode(texts, normalize_embeddings=True)
        embedding_matrix = np.asarray(embeddings, dtype=np.float32)

        index = faiss.IndexFlatIP(embedding_matrix.shape[1])
        index.add(embedding_matrix)
        logger.info("Built FAISS case index with %s documents", len(documents))
        return model, index
    except Exception as exc:
        logger.error("Failed to build case embedding index: %s", exc)
        raise RuntimeError(f"Failed to build case embedding index: {exc}") from exc


def _initialize_case_retriever(cases_path: Path = DEFAULT_CASES_PATH) -> bool:
    """Load resolved cases and build the cached case retriever state."""
    global CASE_METADATA, CASE_INDEX, _CASE_EMBEDDING_MODEL, _CASE_RETRIEVER_UNAVAILABLE

    if CASE_INDEX is not None:
        return True
    if _CASE_RETRIEVER_UNAVAILABLE:
        return False

    try:
        documents = _load_case_documents(cases_path)
        model, index = _build_case_index(documents)
        CASE_METADATA = documents
        CASE_INDEX = index
        _CASE_EMBEDDING_MODEL = model
        return True
    except Exception as exc:
        _CASE_RETRIEVER_UNAVAILABLE = True
        logger.warning(
            "Case retriever unavailable; similar-case lookup disabled: %s",
            exc,
        )
        return False


def rebuild_case_index(cases_path: Path = DEFAULT_CASES_PATH) -> None:
    """Rebuild the cached FAISS case index after resolved_cases.csv changes."""
    global CASE_METADATA, CASE_INDEX, _CASE_EMBEDDING_MODEL, _CASE_RETRIEVER_UNAVAILABLE

    try:
        documents = _load_case_documents(cases_path)

        if _CASE_EMBEDDING_MODEL is None:
            model, index = _build_case_index(documents)
            _CASE_EMBEDDING_MODEL = model
        else:
            texts = [document["search_text"] for document in documents]
            embeddings = _CASE_EMBEDDING_MODEL.encode(texts, normalize_embeddings=True)
            embedding_matrix = np.asarray(embeddings, dtype=np.float32)
            index = faiss.IndexFlatIP(embedding_matrix.shape[1])
            index.add(embedding_matrix)
            logger.info("Rebuilt FAISS case index with %s documents", len(documents))

        CASE_METADATA = documents
        CASE_INDEX = index
        _CASE_RETRIEVER_UNAVAILABLE = False
    except Exception as exc:
        logger.warning("Failed to rebuild case index: %s", exc)


def _search_case_index(query: str, top_k: int) -> tuple[list[int], list[float]]:
    """Run FAISS search and return case indices with cosine similarity scores."""
    if not query.strip():
        return [], []

    if not _initialize_case_retriever():
        return [], []

    assert _CASE_EMBEDDING_MODEL is not None
    assert CASE_INDEX is not None

    try:
        query_embedding = _CASE_EMBEDDING_MODEL.encode([query], normalize_embeddings=True)
        query_matrix = np.asarray(query_embedding, dtype=np.float32)
        scores, indices = CASE_INDEX.search(query_matrix, top_k)

        case_indices: list[int] = []
        case_scores: list[float] = []
        for rank, case_index in enumerate(indices[0]):
            if case_index < 0:
                continue
            case_indices.append(int(case_index))
            case_scores.append(float(scores[0][rank]))
        return case_indices, case_scores
    except Exception as exc:
        logger.warning("Case retrieval failed for query %r: %s", query, exc)
        return [], []


def retrieve_similar_cases(
    complaint_text: str,
    rule_based_issue: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return top historically resolved cases similar to the current complaint."""
    query = f"{rule_based_issue} {complaint_text}".strip()
    case_indices, case_scores = _search_case_index(query, top_k)

    results: list[dict[str, Any]] = []
    for case_index, similarity_score in zip(case_indices, case_scores):
        if similarity_score < SIMILARITY_THRESHOLD:
            continue

        document = CASE_METADATA[case_index]
        results.append(
            {
                "CASE_ID": document["CASE_ID"],
                "ISSUE": document["ISSUE"],
                "COMPLAINT": document["COMPLAINT"],
                "RESOLUTION_SUMMARY": document["RESOLUTION_SUMMARY"],
                "OUTCOME": document["OUTCOME"],
                "RATING": document["RATING"],
                "similarity_score": similarity_score,
            }
        )

    return results
