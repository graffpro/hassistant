"""
VectorStore — семантический поиск workflows через ChromaDB.
Позволяет находить подходящие workflows по смыслу команды.
"""
import json
from typing import Optional
from core.config import config
from core.logger import logger


class VectorStore:
    def __init__(self):
        self._client = None
        self._collection = None
        self._available = False
        self._init()

    def _init(self):
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=config.memory.chroma_path,
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(
                name="ue5_workflows",
                metadata={"hnsw:space": "cosine"}
            )
            self._available = True
            logger.info(f"VectorStore ready. Workflows: {self._collection.count()}")
        except ImportError:
            logger.warning("ChromaDB not installed — semantic search disabled")
        except Exception as e:
            logger.error(f"VectorStore init error: {e}")

    def add_workflow(self, workflow_id: int, name: str, action: str,
                     object_type: str, command: str):
        """Добавляет workflow в векторный индекс."""
        if not self._available:
            return
        try:
            doc = f"{action} {object_type} {name} {command}"
            self._collection.upsert(
                ids=[str(workflow_id)],
                documents=[doc],
                metadatas=[{
                    "workflow_id": workflow_id,
                    "name": name,
                    "action": action,
                    "object_type": object_type,
                }]
            )
        except Exception as e:
            logger.error(f"VectorStore add error: {e}")

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Семантический поиск похожих workflows."""
        if not self._available or not query:
            return []
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, max(1, self._collection.count())),
            )
            matches = []
            for i, meta in enumerate(results["metadatas"][0]):
                matches.append({
                    "workflow_id": meta["workflow_id"],
                    "name": meta["name"],
                    "action": meta["action"],
                    "object_type": meta["object_type"],
                    "score": 1 - results["distances"][0][i],  # cosine similarity
                })
            return matches
        except Exception as e:
            logger.error(f"VectorStore search error: {e}")
            return []

    def is_available(self) -> bool:
        return self._available
