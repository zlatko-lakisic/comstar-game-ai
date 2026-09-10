"""Process B runtime — AO deliberation, directive store, KB ingest."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from comstar_game_ai.agent.answer_cache import assert_answer_cache_disabled
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_accept import (
    accept_campaign_answer,
    default_campaign_prediction_log,
)
from comstar_game_ai.agent.campaign_ids import CampaignIdMap
from comstar_game_ai.agent.campaign_payload import compose_campaign_payload
from comstar_game_ai.agent.directive import neutral_directive
from comstar_game_ai.agent.learning.consolidator import consolidate_offline
from comstar_game_ai.agent.reach.context_builder import ObservableContext, build_observable_brief
from comstar_game_ai.agent.reach.director import call_campaign_director, call_battle_director
from comstar_game_ai.agent.reach.prompts import (
    battle_directive_question,
    campaign_directive_question,
)
from comstar_game_ai.agent.reach.kb_ingest import ingest_after_action as kb_ingest_after_action
from comstar_game_ai.agent.reach.session import ReachSession
from comstar_game_ai.agent.records.after_action import AfterActionRecord
from comstar_game_ai.agent.standing import (
    StandingDirectiveStore,
    accept_into_standing,
)
from comstar_game_ai.agent.tool_usage import default_tool_usage_log
from comstar_game_ai.game_io.drivers.hardcoded_campaign import HardcodedCampaignDriver
from comstar_game_ai.game_io.logs.turn_boundary import latest_turn_start
from comstar_game_ai.shared.config import load_config
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
    standing_store: StandingDirectiveStore = field(default_factory=StandingDirectiveStore)
    session: ReachSession | None = None
    id_map: CampaignIdMap = field(default_factory=lambda: CampaignIdMap.load())

    async def start(self) -> None:
        assert_answer_cache_disabled(load_config())
        self.session = ReachSession()
        await self.session.start()

    async def stop(self) -> None:
        if self.session:
            await self.session.stop(clear_remote=True)
            self.session = None
        self.publisher.close()

    def _fresh_belief(self) -> BeliefStore:
        """Re-read the snapshot rather than trusting the process-wide cache.

        `default_belief_store()` memoises the first load for the life of the process.
        In a deliberation loop that runs beside the game for an hour, that means every
        turn after the first reasons about the opening position: the driver keeps
        writing the snapshot and this process never looks again.
        """
        return BeliefStore.load()

    def _hold_without_asking(self, turn: int, qid: str, reason: str) -> None:
        directive = neutral_directive(reason)
        self.directive_store.write(qid, directive)
        _LOGGER.warning("turn %s: %s — holding without asking AO", turn, reason)
        self.publisher.publish(
            EventKind.AO_RESULT,
            {"summary": f"hold ({reason})", "question_id": qid},
        )

    async def deliberate_campaign_turn(self, turn: int, belief_summary: str = "") -> None:
        assert self.session is not None
        qid = f"campaign-{turn}-{uuid.uuid4().hex[:8]}"
        belief = self._fresh_belief()
        if not (belief.get_characters() or belief.get_armies() or belief.get_settlements()):
            # An empty map is not a strategic question, and asking one anyway went
            # badly in both directions: the prompt had to carry an instruction about
            # what to do with nothing, and the model then reached for that sentence
            # on a turn where the map was full — answering "hold, the map is empty"
            # with two idle generals and three reachable towns in front of it.
            # Deciding it here costs no GPU and cannot be misread.
            self._hold_without_asking(turn, qid, "belief_empty")
            return

        standing = self.standing_store.refresh_status(
            current_turn=turn,
            prediction_log=default_campaign_prediction_log(),
        )
        standing_view = standing.to_view() if standing is not None else None
        payload = compose_campaign_payload(
            belief=belief,
            question_id=qid,
            turn=turn,
            player_faction=self.player_faction,
            standing=standing_view,
            id_map=self.id_map,
        )
        self.id_map = payload.id_map
        self.id_map.save()

        self.publisher.publish(
            EventKind.AO_REQUEST,
            {
                "summary": f"campaign turn {turn}",
                "question_id": qid,
                "state_hash": payload.state_hash,
            },
        )
        # JSON mode returns raw text via the bridge; we re-accept through the
        # contract so unknown ids / optimistic expects never reach the planner.
        raw_directive = await call_campaign_director(
            self.session,
            text=campaign_directive_question(
                turn, self.player_faction, question_id=qid
            ),
            context=payload.text,
            question_id=qid,
            on_status=lambda s: self.publisher.publish(
                EventKind.AO_STATUS, {"summary": getattr(s, "phase", str(s))[:80]}
            ),
        )
        # Prefer the raw JSON from the model when present; otherwise commentary
        # already explains the failure and we accept that as neutral.
        raw_text = ""
        if raw_directive.raw:
            import json as _json

            raw_text = _json.dumps(raw_directive.raw)
        elif raw_directive.commentary.startswith(
            ("timeout:", "reach_error:", "error:", "malformed", "empty", "not_object")
        ):
            raw_text = ""
        else:
            # Flat schema answers land as objective + commentary via parse_directive.
            import json as _json

            raw_text = _json.dumps(
                {
                    "question_id": qid,
                    "objective": raw_directive.intent.objective,
                    "actor": (raw_directive.play_params or {}).get("actor"),
                    "target": (raw_directive.play_params or {}).get("target"),
                    "abandon_if": dict(raw_directive.intent.abort_if or {}),
                    "expects": (raw_directive.play_params or {}).get("expects") or {},
                    "because": raw_directive.commentary,
                }
            )

        prediction_log = default_campaign_prediction_log()
        if raw_text:
            accepted = accept_campaign_answer(
                raw_text,
                payload=payload,
                current_turn=turn,
                prediction_log=prediction_log,
            )
            directive = accepted.to_legacy_directive(issued_turn=turn)
            pred_id = (accepted.raw or {}).get("prediction_entry_id")
            accept_into_standing(
                self.standing_store,
                accepted,
                current_turn=turn,
                prediction_entry_id=pred_id if isinstance(pred_id, str) else None,
            )
        else:
            directive = raw_directive
            _LOGGER.warning(
                "turn %s: empty/failed director answer — %s",
                turn,
                directive.commentary or "neutral",
            )

        usage = default_tool_usage_log().summary()
        _LOGGER.info(
            "turn %s game_query usage: calls=%s changed=%s",
            turn,
            usage["calls"],
            usage["changed_directive"],
        )

        self.directive_store.write(qid, directive)
        _LOGGER.info(
            "turn %s directive: %s (%s) state_hash=%s",
            turn,
            directive.intent.objective,
            directive.commentary or "no commentary",
            payload.state_hash,
        )
        self.publisher.publish(
            EventKind.AO_RESULT,
            {
                "summary": directive.intent.objective,
                "question_id": qid,
                "state_hash": payload.state_hash,
            },
        )

    async def deliberate_battle_tick(self, tick: int, battle_id: str) -> None:
        assert self.session is not None
        qid = f"battle-{battle_id}-{tick}"
        ctx = build_observable_brief(
            ObservableContext(
                phase="battle",
                tick=tick,
                battle_id=battle_id,
                player_faction=self.player_faction,
                summary=f"tick {tick}",
            ),
            self._fresh_belief(),
        )
        self.publisher.publish(EventKind.AO_REQUEST, {"summary": f"battle tick {tick}", "question_id": qid})
        directive = await call_battle_director(
            self.session,
            text=battle_directive_question(tick, battle_id),
            context=ctx,
            question_id=qid,
            stale_question_ids=[qid],
        )
        self.directive_store.write(qid, directive)
        self.publisher.publish(EventKind.AO_RESULT, {"summary": directive.intent.objective})

    async def run_campaign(self, *, turns: int | None = None, use_ao: bool = True) -> dict[str, object]:
        n = turns if turns is not None else self.turns
        # Hand the driver the same store this runtime writes to, or the deliberation
        # would run beside the turns without ever reaching them.
        driver = HardcodedCampaignDriver(
            player_faction=self.player_faction,
            directive_store=self.directive_store if use_ao else None,
        )
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

    async def run_deliberation_loop(
        self,
        *,
        interval_s: float = 45.0,
        max_calls: int | None = None,
    ) -> dict[str, object]:
        """Write directives on a cadence without driving the game.

        The companion to a live Process A run: that process owns the game and reads
        whatever directive is current, this one thinks about the next turn while it
        plays. Keeping them apart is what stops a slow model from stalling a turn.

        The turn stamped on each directive comes from Rome's own autosave marker, so
        a directive is tied to the turn it was reasoned about rather than to a count
        of how many times this loop has gone round.
        """
        await self.start()
        calls = 0
        try:
            while max_calls is None or calls < max_calls:
                turn = latest_turn_start() or (calls + 1)
                await self.deliberate_campaign_turn(turn)
                calls += 1
                _LOGGER.info("directive written for turn %s (%s calls)", turn, calls)
                if max_calls is not None and calls >= max_calls:
                    break
                await asyncio.sleep(max(1.0, interval_s))
            return {"ok": True, "calls": calls}
        except (KeyboardInterrupt, asyncio.CancelledError):
            return {"ok": True, "calls": calls, "stopped": "interrupted"}
        finally:
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


async def run_deliberation_loop_cli(*, interval_s: float, max_calls: int | None) -> int:
    runtime = AgentRuntime()
    try:
        result = await runtime.run_deliberation_loop(interval_s=interval_s, max_calls=max_calls)
        print(result)
        return 0 if result.get("ok") else 1
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("deliberation loop failed: %s", exc)
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
