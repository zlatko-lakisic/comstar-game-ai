import pytest

from comstar_game_ai.agent.reach.kb_ingest import ingest_observable
from comstar_game_ai.shared.config import load_config

pytestmark = pytest.mark.integration_ada


def test_kb_ingest_observable_record():
    payload = '{"type":"after_action","observable":{"outcome":"win","surprise":0.12}}'
    result = ingest_observable(payload, config=load_config())
    assert result.get("ok") is True
