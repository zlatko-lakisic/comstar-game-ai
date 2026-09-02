"""Unit tests for Phase 7 learning stubs."""

from comstar_game_ai.agent.learning.consolidator import consolidate_offline
from comstar_game_ai.agent.learning.doctrine import DoctrineDestination, triage_document, triage_summary
from comstar_game_ai.agent.records.privileged_store import PrivilegedRecord, PrivilegedStore


def test_privileged_store_append(tmp_path):
    store = PrivilegedStore(tmp_path / "priv.jsonl")
    store.append(PrivilegedRecord(record_type="battle", privileged={"ai_log": "secret"}))
    assert store.count() == 1
    rec = store.read_all()[0]
    assert rec.privileged["ai_log"] == "secret"


def test_consolidate_offline_stub(tmp_path):
    store = PrivilegedStore(tmp_path / "priv.jsonl")
    store.append(PrivilegedRecord(record_type="battle", privileged={"x": 1}))
    proposals = consolidate_offline(store)
    assert len(proposals) == 1
    assert "privileged records" in proposals[0].body


def test_doctrine_triage():
    text = "# Counters\nSpears get 25% bonus vs cavalry.\n\n# Core doctrine\nAlways preserve the general."
    sections = triage_document(text)
    summary = triage_summary(sections)
    assert summary.get(DoctrineDestination.RULES.value, 0) >= 1
    assert len(sections) >= 2
