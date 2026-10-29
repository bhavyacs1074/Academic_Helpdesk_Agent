"""Shared local embedding and Chroma configuration for RAG scripts."""

from __future__ import annotations

import os
import re
from pathlib import Path

import chromadb
import requests


ROOT = Path(__file__).resolve().parents[1]
DB_DIR = Path(os.getenv("ACADEMIC_CHROMA_DIR", ROOT / "artifacts" / "chroma_db"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
BATCH_SIZE = 32


def collection_name(model: str = EMBEDDING_MODEL) -> str:
    """Keep differently embedded indexes separate instead of mixing vectors."""
    suffix = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")[:32] or "model"
    return f"academic_documents_{suffix}"


def embed_texts(
    texts: list[str],
    model: str = EMBEDDING_MODEL,
    api_base: str = OLLAMA_BASE_URL,
    batch_size: int = BATCH_SIZE,
) -> list[list[float]]:
    """Generate local vectors through Ollama's /api/embed endpoint."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not texts:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            response = requests.post(
                f"{api_base.rstrip('/')}/api/embed",
                json={"model": model, "input": batch, "truncate": False},
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Embedding request to Ollama failed at {api_base}. Start Ollama, "
                f"then run `ollama pull {model}`. Details: {exc}"
            ) from exc
        except ValueError as exc:
            raise RuntimeError("Ollama returned invalid JSON for an embedding request") from exc

        batch_vectors = payload.get("embeddings")
        if not isinstance(batch_vectors, list) or len(batch_vectors) != len(batch):
            raise RuntimeError("Ollama returned an unexpected embeddings response")
        if any(not isinstance(vector, list) or not vector for vector in batch_vectors):
            raise RuntimeError("Ollama returned an empty or invalid embedding vector")
        dimension = len(batch_vectors[0])
        if any(len(vector) != dimension for vector in batch_vectors):
            raise RuntimeError("Ollama returned vectors with inconsistent dimensions")
        vectors.extend(batch_vectors)
    return vectors


def get_collection(
    persist_dir: Path = DB_DIR,
    model: str = EMBEDDING_MODEL,
):
    """Get the cosine-similarity collection corresponding to an embed model."""
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection(
        name=collection_name(model),
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": model,
            "description": "Academic helpdesk document chunks",
        },
    )
    indexed_model = (collection.metadata or {}).get("embedding_model")
    if indexed_model and indexed_model != model:
        raise RuntimeError(
            f"This collection was indexed with {indexed_model!r}, not {model!r}. "
            "Use a separate collection for each embedding model."
        )
    return collection
