"""Hybrid academic-document retrieval with citations and safe abstention."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from threading import Lock
from typing import Any

if __package__:
    from scripts.rag import (
        DB_DIR,
        EMBEDDING_MODEL,
        OLLAMA_BASE_URL,
        embed_texts,
        get_collection,
    )
else:
    from rag import (
        DB_DIR,
        EMBEDDING_MODEL,
        OLLAMA_BASE_URL,
        embed_texts,
        get_collection,
    )

from agents.review_tickets import create_ticket


DEFAULT_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.35"))
COURSE_CODE_RE = re.compile(r"\b[A-Za-z]{2,5}\s*-?\s*\d{3,5}\b")
TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _identifier_codes(text: str) -> list[str]:
    return [re.sub(r"[^A-Z0-9]", "", match.upper()) for match in COURSE_CODE_RE.findall(text)]


def _contains_query_code(text: str, codes: list[str]) -> bool:
    if not codes:
        return False
    normalized = re.sub(r"[^A-Z0-9]", "", text.upper())
    return any(code in normalized for code in codes)


def _citation(metadata: dict[str, Any]) -> str:
    source = str(metadata.get("source", "unknown source"))
    path = source if source.startswith("data/") else f"data/{source}"
    if metadata.get("page_number") is not None:
        return f"{path}, page {metadata['page_number']}"
    if metadata.get("row_index") is not None:
        return f"{path}, row {metadata['row_index']}"
    chunk_number = metadata.get("chunk_number")
    if chunk_number is not None:
        return f"{path}, chunk {int(chunk_number) + 1}"
    return path


def _bm25_scores(query: str, documents: list[str]) -> list[float]:
    """Compute lightweight BM25 scores over the small local corpus."""
    query_terms = list(dict.fromkeys(_tokens(query)))
    if not query_terms or not documents:
        return [0.0] * len(documents)

    tokenized = [_tokens(document) for document in documents]
    lengths = [len(document_tokens) for document_tokens in tokenized]
    average_length = sum(lengths) / max(1, len(lengths))
    document_frequency: dict[str, int] = {}
    for document_tokens in tokenized:
        for term in set(document_tokens):
            document_frequency[term] = document_frequency.get(term, 0) + 1

    count = len(documents)
    scores: list[float] = []
    for document_tokens, length in zip(tokenized, lengths):
        frequencies: dict[str, int] = {}
        for term in document_tokens:
            frequencies[term] = frequencies.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            term_frequency = frequencies.get(term, 0)
            if term_frequency == 0:
                continue
            doc_frequency = document_frequency[term]
            inverse_frequency = math.log(
                1.0 + (count - doc_frequency + 0.5) / (doc_frequency + 0.5)
            )
            denominator = term_frequency + 1.2 * (
                0.25 + 0.75 * length / max(1.0, average_length)
            )
            score += inverse_frequency * (term_frequency * 2.2 / denominator)
        scores.append(score)
    return scores


class AcademicRetriever:
    """Reusable hybrid retriever; local corpus text is loaded once per instance."""

    def __init__(
        self,
        persist_dir: Path = DB_DIR,
        model: str = EMBEDDING_MODEL,
        api_base: str = OLLAMA_BASE_URL,
    ) -> None:
        self.model = model
        self.api_base = api_base
        self.collection = get_collection(persist_dir=persist_dir, model=model)
        count = self.collection.count()
        stored = self.collection.get(
            limit=count,
            include=["documents", "metadatas"],
        )
        self.ids: list[str] = stored["ids"]
        self.documents: list[str] = stored["documents"]
        self.metadatas: list[dict[str, Any]] = stored["metadatas"]
        self.index_by_id = {doc_id: index for index, doc_id in enumerate(self.ids)}

    def search(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 30,
        minimum_similarity: float = DEFAULT_MIN_SIMILARITY,
        log_unanswered: bool = True,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {
                "query": query,
                "has_evidence": False,
                "reason": "The query is empty.",
                "evidence": [],
            }
        if top_k < 1 or candidate_k < 1:
            raise ValueError("top_k and candidate_k must be positive")
        if not 0.0 <= minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between 0 and 1")
        if not self.ids:
            response: dict[str, Any] = {
                "query": query,
                "has_evidence": False,
                "reason": "The academic index is empty; no source evidence is available.",
                "minimum_similarity": minimum_similarity,
                "evidence": [],
            }
            if log_unanswered:
                ticket = create_ticket(
                    query,
                    reason="The academic index is empty; no source evidence is available.",
                )
                response["review_ticket"] = {
                    "ticket_id": ticket["ticket_id"],
                    "status": ticket["status"],
                    "occurrence_count": ticket["occurrence_count"],
                    "best_similarity": None,
                }
            return response

        query_vector = embed_texts(
            [query], model=self.model, api_base=self.api_base
        )[0]
        semantic_result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(candidate_k, len(self.ids)),
            include=["distances"],
        )
        semantic_rank: dict[str, int] = {}
        similarities: dict[str, float] = {}
        for rank, (doc_id, distance) in enumerate(
            zip(semantic_result["ids"][0], semantic_result["distances"][0]), start=1
        ):
            semantic_rank[doc_id] = rank
            similarities[doc_id] = 1.0 - float(distance)

        keyword_scores = _bm25_scores(query, self.documents)
        lexical_indices = sorted(
            (index for index, score in enumerate(keyword_scores) if score > 0.0),
            key=lambda index: keyword_scores[index],
            reverse=True,
        )[:candidate_k]
        lexical_rank = {self.ids[index]: rank for rank, index in enumerate(lexical_indices, start=1)}

        candidate_ids = set(semantic_rank) | {self.ids[index] for index in lexical_indices}
        codes = _identifier_codes(query)
        candidates: list[dict[str, Any]] = []
        for doc_id in candidate_ids:
            index = self.index_by_id[doc_id]
            metadata = self.metadatas[index]
            sem_rank = semantic_rank.get(doc_id)
            lex_rank = lexical_rank.get(doc_id)
            fused_score = sum(
                1.0 / (60 + rank)
                for rank in (sem_rank, lex_rank)
                if rank is not None
            )
            similarity = similarities.get(doc_id)
            exact_code_match = _contains_query_code(self.documents[index], codes)
            candidates.append({
                "text": self.documents[index],
                "citation": _citation(metadata),
                "source": metadata.get("source", "unknown source"),
                "location": {
                    key: metadata[key]
                    for key in ("page_number", "row_index", "chunk_number")
                    if key in metadata
                },
                "similarity": similarity,
                "keyword_score": keyword_scores[index],
                "rank_score": fused_score,
                "exact_code_match": exact_code_match,
            })
        candidates.sort(key=lambda hit: hit["rank_score"], reverse=True)

        # A strict semantic floor prevents generic keyword overlap from becoming
        # evidence. Exact course-code hits are retained even when vector rank is low.
        evidence = [
            hit for hit in candidates
            if (hit["similarity"] is not None and hit["similarity"] >= minimum_similarity)
            or hit["exact_code_match"]
        ][:top_k]
        has_evidence = bool(evidence)
        response: dict[str, Any] = {
            "query": query,
            "has_evidence": has_evidence,
            "reason": (
                "Retrieved source evidence."
                if has_evidence
                else "No retrieved source met the relevance threshold; do not answer from this search."
            ),
            "minimum_similarity": minimum_similarity,
            "evidence": evidence,
        }
        if not has_evidence and log_unanswered:
            best_similarity = max(similarities.values(), default=None)
            ticket = create_ticket(
                query,
                reason="No retrieved source met the relevance threshold.",
                evidence=[
                    {
                        "citation": hit["citation"],
                        "similarity": hit["similarity"],
                    }
                    for hit in candidates[:3]
                ],
            )
            response["review_ticket"] = {
                "ticket_id": ticket["ticket_id"],
                "status": ticket["status"],
                "occurrence_count": ticket["occurrence_count"],
                "best_similarity": best_similarity,
            }
        return response


_retrievers: dict[tuple[str, str, str], AcademicRetriever] = {}
_retrievers_lock = Lock()


def retrieve(
    query: str,
    top_k: int = 5,
    candidate_k: int = 30,
    minimum_similarity: float = DEFAULT_MIN_SIMILARITY,
    persist_dir: Path = DB_DIR,
    model: str = EMBEDDING_MODEL,
    api_base: str = OLLAMA_BASE_URL,
    log_unanswered: bool = True,
) -> dict[str, Any]:
    """Retrieve citation-ready evidence; suitable for an ADK function tool."""
    key = (str(persist_dir.resolve()), model, api_base)
    with _retrievers_lock:
        retriever = _retrievers.get(key)
        if retriever is None:
            retriever = AcademicRetriever(persist_dir, model, api_base)
            _retrievers[key] = retriever
    return retriever.search(
        query,
        top_k=top_k,
        candidate_k=candidate_k,
        minimum_similarity=minimum_similarity,
        log_unanswered=log_unanswered,
    )


def retrieve_academic_evidence(query: str) -> dict[str, Any]:
    """Minimal one-argument wrapper for future agent-tool registration."""
    return retrieve(query)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=30)
    parser.add_argument("--min-similarity", type=float, default=DEFAULT_MIN_SIMILARITY)
    parser.add_argument("--persist-dir", type=Path, default=DB_DIR)
    parser.add_argument("--model", default=EMBEDDING_MODEL)
    parser.add_argument("--ollama-url", default=OLLAMA_BASE_URL)
    parser.add_argument("--no-log-unanswered", action="store_true")
    args = parser.parse_args()
    try:
        result = retrieve(
            args.query,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
            minimum_similarity=args.min_similarity,
            persist_dir=args.persist_dir,
            model=args.model,
            api_base=args.ollama_url,
            log_unanswered=not args.no_log_unanswered,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
