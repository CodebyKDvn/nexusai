"""Long-term memory — persistent vector storage with ChromaDB."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievedMemory:
    content: str
    metadata: dict[str, Any]
    distance: float
    id: str


class LongTermMemory:
    """Vector-based persistent memory using ChromaDB."""

    COLLECTIONS = ["code_patterns", "decisions", "bugs", "user_preferences", "reflections"]

    def __init__(self, persist_dir: str = ".nexus/memory") -> None:
        self._persist_dir = persist_dir
        self._client: Any = None
        self._collections: dict[str, Any] = {}

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=self._persist_dir)
            for name in self.COLLECTIONS:
                self._collections[name] = self._client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
        except ImportError:
            logger.warning(
                "ChromaDB not installed; long-term memory will use in-memory fallback"
            )
            self._client = "fallback"
            self._fallback: dict[str, list[dict[str, Any]]] = {
                name: [] for name in self.COLLECTIONS
            }

    def store(
        self,
        collection: str,
        content: str,
        *,
        id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._ensure_client()
        import uuid

        doc_id = id or str(uuid.uuid4())
        meta = metadata or {"source": "nexus"}

        if self._client == "fallback":
            self._fallback.setdefault(collection, []).append({
                "id": doc_id,
                "content": content,
                "metadata": meta,
            })
            return doc_id

        coll = self._collections.get(collection)
        if coll is None:
            raise ValueError(f"Unknown collection: {collection}")

        coll.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[meta],
        )
        return doc_id

    def retrieve(
        self,
        collection: str,
        query: str,
        n_results: int = 5,
    ) -> list[RetrievedMemory]:
        self._ensure_client()

        if self._client == "fallback":
            entries = self._fallback.get(collection, [])
            results = []
            query_lower = query.lower()
            for entry in entries:
                if query_lower in entry["content"].lower():
                    results.append(
                        RetrievedMemory(
                            content=entry["content"],
                            metadata=entry["metadata"],
                            distance=0.0,
                            id=entry["id"],
                        )
                    )
            return results[:n_results]

        coll = self._collections.get(collection)
        if coll is None:
            return []

        try:
            results = coll.query(query_texts=[query], n_results=n_results)
        except Exception:
            return []

        memories = []
        if results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
            dists = results["distances"][0] if results["distances"] else [0.0] * len(docs)
            ids = results["ids"][0] if results["ids"] else [""] * len(docs)

            for doc, meta, dist, doc_id in zip(docs, metas, dists, ids, strict=False):
                memories.append(
                    RetrievedMemory(content=doc, metadata=meta, distance=dist, id=doc_id)
                )

        return memories

    def list_collection(self, collection: str, limit: int = 20) -> list[dict[str, Any]]:
        self._ensure_client()

        if self._client == "fallback":
            return self._fallback.get(collection, [])[:limit]

        coll = self._collections.get(collection)
        if coll is None:
            return []

        try:
            results = coll.peek(limit=limit)
            items = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"]):
                    items.append({
                        "id": results["ids"][i] if results["ids"] else "",
                        "content": doc,
                        "metadata": results["metadatas"][i] if results["metadatas"] else {},
                    })
            return items
        except Exception:
            return []
