"""Process B runtime — AO deliberation, directive store, KB ingest."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from comstar_game_ai.agent.directive import neutral_directive
from comstar_game_ai.agent.learning.consolidator import consolidate_offline
from comstar_game_ai.agent.reach.context_builder import ObservableContext, build_observable_brief
from comstar_game_ai.agent.reach.director import call_campaign_director, call_battle_director
from comstar_game_ai.agent.reach.kb_ingest import ingest_after_action as kb_ingest_after_action
from comstar_game_ai.agent.reach.session import ReachSession
from comstar_game_ai.agent.records.after_action import AfterActionRecord
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.shared.ipc.events import EventKind
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

_LOGGER = logging.getLogger(__name__)


@dataclass
class AgentRuntime:
    """Non-blocking AO integration for campaign and battle loops."""

    turns: int = 20
    player_faction: str = "julii"
    publisher: EventPublisher = field(default_factory=EventPublisher)
    directive_store: DirectiveStore = field(default_factory=DirectiveStore)
    session: ReachSession | None = None

    async def start(self) -> None:
        self.session = ReachSession()
        await self.session.start()

    async def stop(self) -> None:
        if self.session:
            await self.session.stop(clear_remote=True)
            self.session = None
        self.publisher.close()

    async def deliberate_campaign_turn(self, turn: int, belief_summary: str = "") -> None:
        assert self.session is not None
        qid = f"campaign-{turn}-{uuid.uuid4().hex[:8]}"
        ctx = build_observable_brief(
            ObservableContext(
                phase="campaign",
                turn=turn,
                player_faction=self.player_faction,
                summary=belief_summary or f"turn {turn}",
            )
        )
        self.publisher.publish(EventKind.AO_REQUEST, {"summary": f"campaign turn {turn}", "question_id": qid})
        directive = await call_campaign_director(
            self.session,
            text=f"Campaign turn {turn}. Propose directive JSON.",
            context=ctx,
            question_id=qid,
            on_status=lambda s: self.publisher.publish(
                EventKind.AO_STATUS, {"summary": getattr(s, "phase", str(s))[:80]}
            ),
        )
        self.directive_store.write(qid, directive)
        self.publisher.publish(
            EventKind.AO_RESULT,
            {"summary": directive.intent.objective, "question_id": qid},
        )

    async def deliberate_battle_tick(self, tick: int, battle_id: str) -> None:
        assert self.session is not None
        qid = f"battle-{battle_id}-{tick}"
        ctx = build_observable_brief(
            ObservableContext(phase="battle", tick=tick, battle_id=battle_id, summary=f"tick {tick}")
        )
        self.publisher.publish(EventKind.AO_REQUEST, {"summary": f"battle tick {tick}", "question_id": qid})
        directive = await call_battle_director(
            self.session,
            text=f"Battle tick {tick}. Return battle directive JSON.",
            context=ctx,
            question_id=qid,
            stale_question_ids=[qid],
        )
        self.directive_store.write(qid, directive)
        self.publisher.publish(EventKind.AO_RESULT, {"summary": directive.intent.objective})

    async def run_campaign(self, *, turns: int | None = None, use_ao: bool = True) -> dict[str, object]:
        n = turns if turns is not None else self.turns
        driver = HardcodedCampaignDriver(player_faction=self.player_faction)
        if use_ao:
            await self.start()
        ao_calls = 0
        try:
            for turn in range(1, n + 1):
                driver.poll_observation()
                if use_ao:
                    await self.deliberate_campaign_turn(turn)
                    ao_calls += 1
                driver.run_turn_stub(wait_for_next_turn=False)
                await asyncio.sleep(0.01)
            return {"ok": True, "turns": n, "ao_calls": ao_calls}
        finally:
            if use_ao:
                await self.stop()

    async def run_battle_deliberation(self, *, ticks: int = 3, battle_id: str = "sim") -> dict[str, object]:
        await self.start()
        try:
            for tick in range(ticks):
                await self.deliberate_battle_tick(tick, battle_id)
            return {"ok": True, "ticks": ticks}
        finally:
            await self.stop()

    async def ingest_after_action(self, record: AfterActionRecord, *, live: bool = False) -> dict[str, object]:
        if live:
            return kb_ingest_after_action(
                observable=record.observable,
                privileged=record.privileged,
                user_goal=f"after-action {record.battle_id}",
            )
        return {"ok": True, "dry_run": True, "record_id": record.battle_id}

    def run_consolidator_offline(self) -> list[dict[str, object]]:
        return [p.to_dict() for p in consolidate_offline()]


async def run_campaign_cli(*, turns: int, use_ao: bool) -> int:
    runtime = AgentRuntime(turns=turns)
    try:
        result = await runtime.run_campaign(turns=turns, use_ao=use_ao)
        print(result)
        return 0 if result.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("campaign runtime failed: %s", exc)
        return 1


async def run_deliberate_once(*, phase: str = "campaign") -> int:
    runtime = AgentRuntime()
    await runtime.start()
    try:
        if phase == "battle":
            await runtime.deliberate_battle_tick(0, "probe")
        else:
            await runtime.deliberate_campaign_turn(1)
        stored = runtime.directive_store.read()
        print(stored.to_directive() if stored else neutral_directive())
        return 0
    finally:
        await runtime.stop()
