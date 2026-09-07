"""What AO requires of our overlay, checked here instead of at turn 1 of a live run.

Both of these were found the expensive way. A provider without `role` and a skill
without a body are each rejected by the engine as invalid_request, before any model
runs, and the driver reads that rejection as a neutral directive — so the campaign
plays on, holding every turn, looking merely cautious.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ao_reach.overlay_packer import OverlayPacker

from comstar_game_ai.agent.reach.session import overlay_root

# agentic-orchestration builds a crew agent from these three and raises
# "Agent provider '<id>' is missing '<field>'" if any is blank.
REQUIRED_AGENT_FIELDS = ("role", "goal", "backstory")


def _provider_paths() -> list[Path]:
    return sorted((overlay_root() / "agent_providers").glob("*.yaml"))


def _skill_paths() -> list[Path]:
    return sorted((overlay_root() / "agent_skills").glob("*.yaml"))


def test_there_are_providers_to_check():
    assert _provider_paths()


@pytest.mark.parametrize("path", _provider_paths(), ids=lambda p: p.stem)
def test_every_provider_declares_what_the_engine_demands(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))

    for field in REQUIRED_AGENT_FIELDS:
        assert str(doc.get(field) or "").strip(), f"{path.stem} is missing {field}"


@pytest.mark.parametrize("path", _skill_paths(), ids=lambda p: p.stem)
def test_every_skill_can_be_resolved_to_a_body(path: Path):
    """A skill file may exist without a body, but then no agent may name it."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    content = doc.get("content")
    if not isinstance(content, dict):
        pytest.skip(f"{path.stem} is data-only, not injectable")

    body = content.get("body")
    if body is None:
        body = (path.parent / str(content["file"])).read_text(encoding="utf-8")

    assert str(body).strip(), f"{path.stem} resolves to an empty body"


def test_the_packed_agents_keep_all_the_skills_they_name():
    """The packer drops a bodyless skill silently, so compare intent against result."""
    pack = OverlayPacker().pack(overlay_root())

    for agent in pack.agents:
        declared = yaml.safe_load(
            (overlay_root() / "agent_providers" / f"{agent['id'].split('.')[-1]}.yaml").read_text(
                encoding="utf-8"
            )
        )
        wanted = [f"client.{name}" for name in (declared.get("skills") or [])]
        assert (agent.get("skills") or []) == wanted, agent["id"]


def test_the_campaign_director_still_gets_its_three_skills():
    """The regression that mattered: one empty file cost it all three."""
    pack = OverlayPacker().pack(overlay_root())
    director = next(a for a in pack.agents if a["id"] == "client.campaign_director")

    assert director["skills"] == [
        "client.campaign_ui_facts",
        "client.campaign_info_sources",
        "client.campaign_learnings",
    ]
    assert "## Campaign UI facts" in director["backstory"]


@pytest.mark.parametrize(
    "name", ("campaign_ui_facts", "campaign_info_sources", "campaign_learnings")
)
def test_generated_bodies_fit_their_inject_budget(name: str):
    root = overlay_root() / "agent_skills"
    skill = yaml.safe_load((root / f"{name}.yaml").read_text(encoding="utf-8"))
    body = (root / f"{name}.md").read_text(encoding="utf-8")

    assert len(body) <= skill["inject"]["max_chars"], name
