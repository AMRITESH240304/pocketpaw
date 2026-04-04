"""Agent knowledge service — thin wrapper over the core KnowledgeEngine.

Delegates all operations to KnowledgeEngine(scope="agent:{agent_id}").
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Agent-scoped knowledge operations via the core KnowledgeEngine."""

    @staticmethod
    def _engine(agent_id: str):
        from pocketpaw.knowledge import KnowledgeEngine
        return KnowledgeEngine(scope=f"agent:{agent_id}")

    @staticmethod
    async def ingest_text(agent_id: str, text: str, source: str = "manual") -> dict:
        engine = KnowledgeService._engine(agent_id)
        article = await engine.ingest_text(text, source)
        return {"article": article.to_dict(), "source": source}

    @staticmethod
    async def ingest_url(agent_id: str, url: str) -> dict:
        try:
            engine = KnowledgeService._engine(agent_id)
            article = await engine.ingest_url(url)
            return {"article": article.to_dict(), "url": url}
        except Exception as exc:
            return {"error": str(exc), "url": url}

    @staticmethod
    async def ingest_file(agent_id: str, file_path: str) -> dict:
        try:
            engine = KnowledgeService._engine(agent_id)
            article = await engine.ingest_file(file_path)
            return {"article": article.to_dict(), "file": article.title}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    async def search(agent_id: str, query: str, limit: int = 5) -> list[str]:
        engine = KnowledgeService._engine(agent_id)
        articles = await engine.search(query, limit)
        return [a.summary or a.content[:500] for a in articles]

    @staticmethod
    async def search_context(agent_id: str, query: str, limit: int = 3) -> str:
        """Get formatted knowledge context for agent prompt injection."""
        engine = KnowledgeService._engine(agent_id)
        return await engine.search_context(query, limit)

    @staticmethod
    async def clear(agent_id: str) -> dict:
        engine = KnowledgeService._engine(agent_id)
        engine.clear()
        return {"ok": True}

    @staticmethod
    def stats(agent_id: str) -> dict:
        engine = KnowledgeService._engine(agent_id)
        return engine.stats()

    @staticmethod
    async def lint(agent_id: str) -> list[dict]:
        engine = KnowledgeService._engine(agent_id)
        issues = await engine.lint()
        return [i.to_dict() for i in issues]
