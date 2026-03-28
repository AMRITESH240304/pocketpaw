# Tests for ee/instinct — decision pipeline store (SQLite).
# Created: 2026-03-28

from __future__ import annotations

from pathlib import Path

import pytest

from ee.instinct.models import ActionTrigger, ActionContext
from ee.instinct.store import InstinctStore


@pytest.fixture
def store(tmp_path: Path) -> InstinctStore:
    return InstinctStore(tmp_path / "test.db")


def trigger(source: str = "claude") -> ActionTrigger:
    return ActionTrigger(type="agent", source=source, reason="test")


class TestActionLifecycle:
    @pytest.mark.asyncio
    async def test_propose(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Reorder inventory",
            description="Stock at 4 units", recommendation="Order 20 units",
            trigger=trigger(),
        )
        assert action.id.startswith("act-")
        assert action.status.value == "pending"

    @pytest.mark.asyncio
    async def test_approve(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Test", description="",
            recommendation="Do it", trigger=trigger(),
        )
        approved = await store.approve(action.id, "user:prakash")
        assert approved is not None
        assert approved.status.value == "approved"
        assert approved.approved_by == "user:prakash"

    @pytest.mark.asyncio
    async def test_reject(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Test", description="",
            recommendation="Do it", trigger=trigger(),
        )
        rejected = await store.reject(action.id, "Not needed")
        assert rejected is not None
        assert rejected.status.value == "rejected"

    @pytest.mark.asyncio
    async def test_execute(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Test", description="",
            recommendation="Do it", trigger=trigger(),
        )
        await store.approve(action.id)
        executed = await store.mark_executed(action.id, "Done successfully")
        assert executed is not None
        assert executed.status.value == "executed"
        assert executed.outcome == "Done successfully"

    @pytest.mark.asyncio
    async def test_fail(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Test", description="",
            recommendation="Do it", trigger=trigger(),
        )
        failed = await store.mark_failed(action.id, "API error")
        assert failed is not None
        assert failed.status.value == "failed"
        assert failed.error == "API error"


class TestQueries:
    @pytest.mark.asyncio
    async def test_pending(self, store: InstinctStore) -> None:
        await store.propose(pocket_id="p1", title="A", description="", recommendation="", trigger=trigger())
        await store.propose(pocket_id="p1", title="B", description="", recommendation="", trigger=trigger())
        pending = await store.pending()
        assert len(pending) == 2

    @pytest.mark.asyncio
    async def test_pending_count(self, store: InstinctStore) -> None:
        a = await store.propose(pocket_id="p1", title="A", description="", recommendation="", trigger=trigger())
        await store.propose(pocket_id="p1", title="B", description="", recommendation="", trigger=trigger())
        await store.approve(a.id)
        count = await store.pending_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_for_pocket(self, store: InstinctStore) -> None:
        await store.propose(pocket_id="p1", title="A", description="", recommendation="", trigger=trigger())
        await store.propose(pocket_id="p2", title="B", description="", recommendation="", trigger=trigger())
        p1_actions = await store.for_pocket("p1")
        assert len(p1_actions) == 1


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_auto_logs_lifecycle(self, store: InstinctStore) -> None:
        action = await store.propose(
            pocket_id="p1", title="Test action", description="",
            recommendation="Do it", trigger=trigger(),
        )
        await store.approve(action.id)
        await store.mark_executed(action.id, "Done")

        entries = await store.query_audit(pocket_id="p1")
        events = [e.event for e in entries]
        assert "action_proposed" in events
        assert "action_approved" in events
        assert "action_executed" in events

    @pytest.mark.asyncio
    async def test_manual_log(self, store: InstinctStore) -> None:
        await store.log(
            actor="system", event="connector_synced",
            description="Stripe synced 42 records", pocket_id="p1",
        )
        entries = await store.query_audit(event="connector_synced")
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_export(self, store: InstinctStore) -> None:
        await store.log(actor="system", event="test", description="Test", pocket_id="p1")
        exported = await store.export_audit("p1")
        import json
        parsed = json.loads(exported)
        assert len(parsed) == 1
