"""Hardcoded campaign driver — observe, clear modals, issue fair orders, end turn."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Callable

from comstar_game_ai.agent.belief.entities import Army, ExistenceStatus
from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.directive import Directive, neutral_directive
from comstar_game_ai.game_io.campaign.combat import CombatDirector
from comstar_game_ai.game_io.campaign.modal import ensure_campaign_map, localize_colored_modal_buttons
from comstar_game_ai.game_io.campaign.orders import CampaignPlanner
from comstar_game_ai.game_io.campaign.ui_mode import (
    CampaignUiMode,
    grab_and_classify,
    grab_rgb_image,
    save_debug_capture,
)
from comstar_game_ai.game_io.console.actuator import ConsoleActuator
from comstar_game_ai.game_io.intent_record import IntentRecordWriter
from comstar_game_ai.game_io.logs.campaign_probe import latest_julii_autosave_turn, summarize_julii_turn_markers
from comstar_game_ai.game_io.logs.message_log import MessageLogTailer, default_message_log_path
from comstar_game_ai.game_io.logs.turn_boundary import (
    latest_turn_end,
    latest_turn_start,
    newest_turn_start_marker,
)
from comstar_game_ai.game_io.logs.scripting_log import ScriptingLogTailer
from comstar_game_ai.game_io.state_machine import GameState, GameStateDetector
from comstar_game_ai.game_io.verification import VerificationPipeline, VerificationResult
from comstar_game_ai.shared.ipc.events import EventKind
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

_LOGGER = logging.getLogger(__name__)


def phase2_accepted(result: Mapping[str, object], *, turns: int) -> bool:
    """Did a run meet Phase 2 acceptance: `turns` turns driven with zero desyncs?

    The campaign's own turn counter must agree with our cycle count. Without that,
    cycles that report success without moving the game on still pass, which is how a run
    of 20 attempts was scored 19 OK while the campaign advanced 10 turns.
    """
    return (
        int(result.get("desyncs", 1) or 0) == 0
        and int(result.get("turns_ok", 0) or 0) >= turns
        and int(result.get("turns_advanced", 0) or 0) >= turns
    )


@dataclass
class HardcodedCampaignDriver:
    """Campaign-map loop without AO reasoning."""

    belief: BeliefStore = field(default_factory=BeliefStore)
    actuator: ConsoleActuator = field(default_factory=ConsoleActuator)
    state: GameStateDetector = field(default_factory=GameStateDetector)
    log_tailer: ScriptingLogTailer = field(default_factory=ScriptingLogTailer)
    message_tailer: MessageLogTailer = field(default_factory=MessageLogTailer)
    intent_writer: IntentRecordWriter = field(default_factory=IntentRecordWriter)
    verification: VerificationPipeline = field(default_factory=VerificationPipeline)
    player_faction: str = "julii"
    turn_wait_timeout_s: float = 180.0
    auto_end_turn: bool = False
    # Max seconds to poll for map-clear readiness before End Turn (not a fixed sleep).
    end_turn_ready_timeout_s: float = 30.0
    # Deprecated alias kept for callers/tests; treated as ready-timeout when set.
    end_turn_delay_s: float = 0.0
    use_vision: bool = False
    # Read the opening position out of Rome's own campaign files at startup. Without
    # it the belief store begins empty and stays that way, because the only other
    # writer is script telemetry that cannot carry entities.
    seed_from_setup: bool = True
    planner: CampaignPlanner | None = None
    # Answer a Battle Deployment panel with auto-resolve before the modal handler
    # sees it. That panel reads as a plain modal, and the handler is willing to click
    # a decision button on it — 'fight' would hand control to a battle map no loop
    # can drive. Phase 2 lost a run to exactly this.
    auto_resolve_battles: bool = True
    # The attack step is opt-in: it needs a measured Lists row for the stack and at
    # least one target, and it refuses to act on anything less than the game's own
    # evidence (full stack in the HUD, attack glyph under the cursor).
    attack_enabled: bool = False
    army_lists_row_norm: tuple[float, float] | None = None
    attack_targets: tuple[tuple[float, float], ...] = ()
    # Called on every pass of a wait, to tell the safety layer this loop is alive.
    # Waiting for Rome's AI round takes minutes and the deadman allows ten seconds,
    # so without this the watchdog kills the run partway through the first turn.
    on_heartbeat: Callable[[], None] | None = None
    # Set to feed the operator overlay (Process C). None means nobody is watching,
    # which is the normal case: the campaign loop must never wait on a spectator.
    publisher: EventPublisher | None = None
    # Where Process B leaves its directives. None keeps the loop on its own hardcoded
    # policy; set it and AO gets a say, with "hold" whenever it has nothing fresh.
    directive_store: DirectiveStore | None = None
    # Wall-clock ceiling, so a directive left on disk by an earlier session is never
    # adopted. Turn-count expiry alone would still honour a day-old file once.
    directive_max_age_s: float = 900.0
    last_directive: str = field(default="", init=False)
    _directive_question_id: str = field(default="", init=False)
    _directive_adopted_turn: int = field(default=0, init=False)
    battles_resolved: int = field(default=0, init=False)
    attacks_ordered: int = field(default=0, init=False)
    _publish_failures: int = field(default=0, init=False)
    _combat: CombatDirector | None = field(default=None, init=False)
    _turn_advances: int = field(default=0, init=False)
    _last_started_seen: int = field(default=0, init=False)
    _turn_baseline_resets: int = field(default=0, init=False)
    _julii_turns_seen: int = field(default=0, init=False)
    _julii_turn_ready: bool = field(default=False, init=False)
    _julii_round_starts: int = field(default=0, init=False)
    _last_autosave_turn: int = field(default=0, init=False)
    _autosave_events: int = field(default=0, init=False)
    last_ui_mode: str = field(default="unknown", init=False)
    last_ui_confidence: float = field(default=0.0, init=False)
    last_ui_detail: str = field(default="", init=False)
    last_orders: list[str] = field(default_factory=list, init=False)
    _last_debug_capture_ts: float = field(default=0.0, init=False)
    _turn_marker_cache: dict[str, tuple[float, int]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.actuator.state = self.state
        if self.planner is None:
            self.planner = CampaignPlanner(player_faction=self.player_faction)
        if self.seed_from_setup:
            self._seed_belief_from_setup()

    def _seed_belief_from_setup(self) -> None:
        """Give the director a map to reason about before the first turn."""
        from comstar_game_ai.game_io.campaign.start_position import seed_belief_from_setup

        try:
            seeded = seed_belief_from_setup(self.belief, player_faction=self.player_faction)
        except Exception as exc:  # noqa: BLE001 - never let reading a file stop a run
            _LOGGER.warning("could not read the campaign setup: %s", exc)
            return
        if seeded:
            _LOGGER.info("seeded %s entities from the campaign setup files", seeded)
            self._save_belief()
        else:
            _LOGGER.warning("campaign setup gave no entities — the director will be blind")

    def _heartbeat(self) -> None:
        """Say the loop is still running. Never let the watchdog's own call kill it."""
        if self.on_heartbeat is None:
            return
        try:
            self.on_heartbeat()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("heartbeat failed: %s", exc)

    def _save_belief(self) -> None:
        """Put the snapshot where the agent process reads it.

        Process B does not share this object: it calls `BeliefStore.load()`, which
        reads `data/belief_snapshot.json`. Nothing wrote that file, so every
        observation this driver made stayed in its own memory and the director was
        handed an empty map no matter how much we had seen.
        """
        try:
            self.belief.save()
        except OSError as exc:
            _LOGGER.warning("could not write the belief snapshot: %s", exc)

    def _publish(self, kind: EventKind, payload: dict[str, object] | None = None) -> None:
        """Tell the overlay what just happened. Never let it cost the run.

        A publish to an overlay that died costs a connect timeout every call, so the
        publisher is dropped after a few failures rather than taxing every turn.
        """
        if self.publisher is None:
            return
        try:
            self.publisher.publish(kind, dict(payload or {}))
            self._publish_failures = 0
        except Exception:
            self._publish_failures += 1
            if self._publish_failures >= 3:
                _LOGGER.warning("overlay stopped accepting events — no longer publishing")
                self.publisher = None

    def _resolve_hwnd(self) -> int | None:
        try:
            shell = self.actuator.shell
            if shell is None:
                return None
            return shell.resolve_hwnd()
        except Exception:
            return None

    def current_directive(self) -> Directive | None:
        """The directive in force this turn, or None when AO is not in the loop.

        Deliberation happens in Process B and lands in a file; this side never waits
        for it. Everything that is not a fresh, parseable directive becomes the
        neutral "hold", so an AO that is down, slow, or talking nonsense costs a turn
        of standing still rather than a guessed move.
        """
        if self.directive_store is None:
            return None

        stored = self.directive_store.read()
        if stored is None:
            return self._neutral("no directive on disk")

        age_s = max(0.0, time.time() - float(stored.ts or 0.0))
        if age_s > self.directive_max_age_s:
            return self._neutral(f"directive {age_s:.0f}s old")

        directive = stored.to_directive()
        turn_now = self._known_game_turn()
        if stored.question_id != self._directive_question_id:
            self._directive_question_id = stored.question_id
            self._directive_adopted_turn = turn_now

        plies = max(1, int(directive.valid_for_plies or 1))
        elapsed = turn_now - self._directive_adopted_turn
        if elapsed >= plies:
            return self._neutral(f"directive expired after {plies} plies")

        self.last_directive = directive.intent.objective
        return directive

    def _neutral(self, reason: str) -> Directive:
        _LOGGER.info("campaign directive: neutral (%s)", reason)
        self.last_directive = f"hold ({reason})"
        return neutral_directive(reason)

    def combat_director(self) -> CombatDirector | None:
        """Combat helper bound to the live window, or None in a dry run."""
        hwnd = self._resolve_hwnd()
        shell = self.actuator.shell
        controller = shell.input_controller if shell else None
        if hwnd is None or controller is None:
            return None
        if self._combat is None or self._combat.hwnd != hwnd:
            self._combat = CombatDirector(hwnd=hwnd, controller=controller)
        return self._combat

    def resolve_pending_battle(self) -> bool:
        """Auto-resolve a pending battle. True only when one was there and cleared."""
        if not (self.use_vision and self.auto_resolve_battles):
            return False
        director = self.combat_director()
        if director is None or not director.battle_pending():
            return False
        self._publish(EventKind.INTENT_DECLARED, {"summary": "battle deployment up — auto-resolving"})
        resolved = director.resolve_battle()
        self._publish(
            EventKind.VERIFICATION,
            {"ok": resolved, "summary": "battle auto-resolved" if resolved else "battle panel stuck"},
        )
        if resolved:
            self.battles_resolved += 1
            self.belief.history.append(
                {
                    "event": "BattleAutoResolved",
                    "source": "combat_director",
                    "turn": str(self.state.turn or ""),
                }
            )
        else:
            _LOGGER.warning("battle panel did not clear after auto-resolve")
        return resolved

    def _sync_ui(self, *, handle_modal: bool = True) -> CampaignUiMode:
        """Classify the live window. Dry tests leave use_vision=False so this is a no-op."""
        if not self.use_vision:
            return CampaignUiMode.UNKNOWN
        hwnd = self._resolve_hwnd()
        if hwnd is None:
            return CampaignUiMode.UNKNOWN
        # Before the modal handler, not after: it cannot tell Battle Deployment from
        # any other parchment panel, and its decision-button click is irreversible.
        self.resolve_pending_battle()
        if handle_modal:
            shell = self.actuator.shell
            classification = ensure_campaign_map(
                hwnd,
                input_controller=shell.input_controller if shell else None,
                turn=self.state.turn,
                # A vision round can outlast the deadman on a busy GPU, and when it
                # did, the watchdog killed input mid-turn while the answer was still
                # in flight — the panel got dismissed correctly a moment after the
                # run had already lost control of the game.
                on_heartbeat=self.on_heartbeat,
            )
        else:
            classification = grab_and_classify(hwnd)
        self.last_ui_mode = classification.mode.value
        self.last_ui_confidence = float(getattr(classification, "confidence", 0.0) or 0.0)
        self.last_ui_detail = str(getattr(classification, "detail", "") or "")
        # Vision is advisory. A bad classify must not wipe campaign_map from logs.
        if classification.confidence >= 0.7:
            self.state.apply_ui_classification(classification)
        return classification.mode

    def _refresh_turn_from_message_log(self) -> None:
        """Continuously infer current turn from full message_log snapshot."""
        path = default_message_log_path()
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        markers = summarize_julii_turn_markers(text, player_faction=self.player_faction)
        rounds = int(markers.get("round_starts") or 0)
        self._julii_round_starts = max(self._julii_round_starts, rounds)
        autosave_turn = int(markers.get("autosave_turn") or 0)
        if autosave_turn > self._last_autosave_turn:
            self._last_autosave_turn = autosave_turn
            self._autosave_events += 1
        inferred = self.state.infer_from_message_log(text, player_faction=self.player_faction)
        known_turn = markers.get("known_turn")
        if isinstance(known_turn, int):
            self.state.turn = max(self.state.turn or 0, known_turn)
        if inferred is not None:
            self._julii_turn_ready = True

    def bootstrap_from_logs(self) -> int:
        """Ingest existing logs (script + message_log inference) before live tailing."""
        self.log_tailer.reset()
        self.message_tailer.reset()

        path = default_message_log_path()
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            markers = summarize_julii_turn_markers(text, player_faction=self.player_faction)
            self._julii_round_starts = int(markers.get("round_starts") or 0)
            autosave_turn = markers.get("autosave_turn")
            known_turn = markers.get("known_turn")
            self._last_autosave_turn = int(autosave_turn or known_turn or 0)
            inferred = self.state.infer_from_message_log(text, player_faction=self.player_faction)
            if known_turn is not None and self.state.turn is None:
                self.state.turn = int(known_turn)
            if inferred is not None:
                self.belief.history.append(
                    {
                        "event": "CampaignMapReady",
                        "source": "message_log_infer",
                        "turn": str(self.state.turn or ""),
                    }
                )
            self._julii_turn_ready = self.state.allows_campaign_orders()
            self.message_tailer.seek_end()

        return self.poll_observation()

    def _poll_message_log_turns(self) -> int:
        from comstar_game_ai.game_io.logs.campaign_probe import player_faction_log_name

        log_faction = player_faction_log_name(self.player_faction)
        ingested = 0
        for line in self.message_tailer.poll():
            lower = line.lower()
            if "new round start turn(" in lower:
                start = lower.index("new round start turn(") + len("new round start turn(")
                end = lower.index(")", start)
                faction = line[start:end].strip().lower()
                if faction == log_faction.lower():
                    self._julii_round_starts += 1
                    ingested += 1
                    self._record_message_log_turn()
            elif "campaign saved:" in lower and "house of julii" in lower and "turn" in lower:
                turn = latest_julii_autosave_turn(line)
                if turn is not None:
                    self._last_autosave_turn = turn
                    self._autosave_events += 1
                    ingested += 1
                    self._record_message_log_turn(turn=turn)
        return ingested

    def _record_message_log_turn(self, *, turn: int | None = None) -> None:
        if turn is None:
            turn = self.state.turn
            if turn is None:
                turn = self._julii_round_starts
            else:
                turn = max(turn, self._julii_round_starts)
        else:
            turn = max(turn, self._last_autosave_turn)
        self.state.turn = turn
        record = {
            "event": "NewTurnStart",
            "source": "message_log",
            "turn": str(turn),
            "faction": self.player_faction,
        }
        self.state.update_from_script_event(record)
        self.belief.history.append(dict(record))

    def poll_observation(self) -> int:
        self._refresh_turn_from_message_log()
        self._note_turn_started(self.turn_started)
        count = self._poll_message_log_turns()
        for record in self.log_tailer.poll():
            count += 1
            self._ingest_script_record(record)
        if count:
            self.belief.decay()
            self._save_belief()
        return count

    def _note_turn_started(self, started: int) -> None:
        """Track turn advances as they happen, from the turn Rome says we are playing.

        Counted here rather than subtracted from the endpoints at the end of a run.
        Rome's saves folder keeps earlier campaigns, so before this session ends its
        first turn the newest `Turn N End.sav` necessarily belongs to a previous one:
        a run from turn 2 to 20 measured itself against a leftover turn 25 and scored
        -6, which the old `max(0, ...)` reported as zero turns driven.

        A number going *down* is that same leftover, or a reloaded save. It is never a
        turn going backwards, so it re-baselines instead of counting.
        """
        if started <= 0:
            return
        if self._last_started_seen == 0:
            self._last_started_seen = started
            return
        if started < self._last_started_seen:
            self._last_started_seen = started
            self._turn_baseline_resets += 1
            return
        if started > self._last_started_seen:
            self._turn_advances += started - self._last_started_seen
            self._last_started_seen = started

    def _ingest_script_record(self, record: dict[str, str]) -> None:
        event = record.get("event")
        if not event:
            return

        self.state.update_from_script_event(record)
        self.belief.history.append(dict(record))

        if event == "NewTurnStart":
            self._julii_turns_seen += 1
            if record.get("source") != "message_log" and record.get("turn"):
                try:
                    script_turn = int(record["turn"])
                    if self.state.turn is None or script_turn > self.state.turn:
                        self.state.turn = script_turn
                except ValueError:
                    pass
            elif self.state.turn is None:
                self.state.turn = self._julii_turns_seen

        self._ingest_entity_record(record)

    def _ingest_entity_record(self, record: dict[str, str]) -> None:
        entity_type = record.get("entity")
        entity_id = record.get("id")
        if not entity_type or not entity_id:
            return

        provenance = "script_telemetry"
        confidence = float(record.get("confidence", "1.0"))
        existence = ExistenceStatus.OBSERVED_PRESENT

        if entity_type == "army":
            self.belief.update(
                Army(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    faction=record.get("faction", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    strength=float(record.get("strength", "0")),
                    general=record.get("general"),
                )
            )
        elif entity_type == "settlement":
            from comstar_game_ai.agent.belief.entities import Settlement

            pop = record.get("population")
            self.belief.update(
                Settlement(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    region=record.get("region", ""),
                    owner=record.get("owner", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    population=int(pop) if pop else None,
                )
            )
        elif entity_type == "character":
            from comstar_game_ai.agent.belief.entities import Character

            self.belief.update(
                Character(
                    entity_id=entity_id,
                    provenance=provenance,
                    confidence=confidence,
                    existence=existence,
                    name=record.get("name", entity_id),
                    faction=record.get("faction", ""),
                    x=float(record.get("x", "0")),
                    y=float(record.get("y", "0")),
                    role=record.get("role", ""),
                )
            )

    def _known_game_turn(self) -> int:
        """Best available Julii turn from autosave / inferred state (game truth)."""
        return max(
            int(self.state.turn or 0),
            int(self._last_autosave_turn or 0),
            self.turn_started,
        )

    @property
    def game_turn(self) -> int:
        """The campaign's own turn number, as last observed from the logs."""
        return self._known_game_turn()

    @property
    def turns_ended(self) -> int:
        """Highest turn Rome has autosaved as *ended*, or 0 before the first End Turn.

        Measuring from the autosave rather than the inferred turn keeps the count immune
        to 'Turn N Start' markers, which would read a fresh campaign as already one turn
        in and leave a 20-turn run one short of acceptance.
        """
        return self._cached_turn("end", latest_turn_end)

    @property
    def turn_started(self) -> int:
        """Turn the player is currently on, i.e. the AI round has handed control back."""
        return self._cached_turn("start", latest_turn_start)

    def _cached_turn(self, key: str, source: Callable[[], int | None]) -> int:
        """Read a turn marker, briefly cached — these scan the saves folder on disk.

        Progress reporting asks for the turn on every line it prints, and the wait loops
        poll several times a second.
        """
        now = time.monotonic()
        cached_at, value = self._turn_marker_cache.get(key, (0.0, 0))
        if now - cached_at < 0.5:
            return value
        value = int(source() or 0)
        self._turn_marker_cache[key] = (now, value)
        return value

    def _blocking_ui_present(self) -> bool:
        """Decision buttons, or a panel over the map centre that swallows End Turn.

        Notice cards in the left dock are deliberately not blocking: they ask for
        nothing and the map stays playable behind them.
        """
        if not self.use_vision:
            return False
        hwnd = self._resolve_hwnd()
        if hwnd is None:
            return False
        image = grab_rgb_image(hwnd)
        if image is None:
            return False
        from comstar_game_ai.game_io.campaign.modal import blocking_ui_present

        return blocking_ui_present(image)

    def wait_until_ready_for_end_turn(
        self,
        *,
        timeout_s: float | None = None,
        on_progress: Callable[..., None] | None = None,
        index: int = 0,
        total: int = 0,
    ) -> bool:
        """Poll until campaign map is clear of blocking diplomacy UI — no fixed sleep."""
        legacy = max(0.0, float(self.end_turn_delay_s or 0.0))
        timeout = timeout_s
        if timeout is None:
            timeout = max(float(self.end_turn_ready_timeout_s), legacy) if self.use_vision else legacy
        if timeout <= 0 and not self.use_vision:
            return True
        deadline = time.time() + max(0.5, float(timeout))
        last_report = 0.0
        while time.time() < deadline:
            self._heartbeat()
            self.poll_observation()
            mode = self._sync_ui(handle_modal=True)
            buttons = self._blocking_ui_present()
            map_ok = mode == CampaignUiMode.CAMPAIGN_MAP or (
                not self.use_vision and self.state.allows_campaign_orders()
            )
            ready = map_ok and not buttons and self.state.allows_campaign_orders()
            now = time.time()
            if on_progress and now - last_report >= 1.0:
                on_progress(
                    index=index,
                    total=total,
                    phase=(
                        f"end-turn ready check ui={self.last_ui_mode} "
                        f"buttons={'yes' if buttons else 'no'} "
                        f"game_turn={self._known_game_turn()}"
                    ),
                )
                last_report = now
            if ready:
                if on_progress:
                    on_progress(index=index, total=total, phase="ready for End Turn")
                return True
            time.sleep(0.25)
        _LOGGER.warning(
            "timed out waiting for End Turn readiness (ui=%s buttons=%s)",
            self.last_ui_mode,
            self._blocking_ui_present(),
        )
        return False

    def wait_for_turn_event(
        self,
        *,
        timeout_s: float | None = None,
        on_progress: Callable[..., None] | None = None,
        index: int = 0,
        total: int = 0,
        turn_before: int | None = None,
        since: float | None = None,
    ) -> bool:
        """Wait until Julii's turn returns after End Turn.

        The proof is `Turn N Start.sav`, which Rome writes when the AI round hands
        control back. A new Julii round-start line used to count too, but that arrives
        late and often after the next attempt has begun waiting, so it scored the
        previous turn twice; and the inferred turn from message_log counts for nothing
        when Rome writes no log at all, which stalled every attempt for the full
        timeout while the campaign advanced normally underneath.
        """
        timeout = timeout_s if timeout_s is not None else self.turn_wait_timeout_s
        started_baseline = self.turn_started
        baseline = int(turn_before if turn_before is not None else self._known_game_turn())
        # When Rome last handed a turn back, as a write time rather than a number.
        # Numbers only tell us about progress if they keep climbing, and they stop
        # doing that the moment a new campaign starts: run beside a finished one,
        # this waited for turn 21 against a game sitting on turn 1 and timed out on
        # every turn of the run. A save written after we pressed End Turn is proof
        # whatever the number on it says.
        #
        # The caller should pass the time from *before* it pressed End Turn. Reading
        # it here instead loses the fast turns: ending the turn already polls this
        # folder for up to ten seconds, so a quick AI round lands `Turn N Start.sav`
        # before this line runs, and the wait then sits out its full timeout waiting
        # for the turn after the one it already had.
        if since is None:
            marker_baseline = newest_turn_start_marker()
            since = marker_baseline[1] if marker_baseline else 0.0
        deadline = time.time() + timeout
        last_ui = -999.0
        while time.time() < deadline:
            self._heartbeat()
            self.poll_observation()
            self._refresh_turn_from_message_log()
            current = self._known_game_turn()
            started = self.turn_started
            marker = newest_turn_start_marker()
            handed_back = marker is not None and marker[1] > since
            if handed_back or started > started_baseline or current > baseline:
                if on_progress:
                    if handed_back:
                        why = f"Rome handed turn {marker[0]} back"
                    elif started > started_baseline:
                        why = f"player turn began {started_baseline} -> {started}"
                    else:
                        why = f"game turn advanced {baseline} -> {current}"
                    on_progress(index=index, total=total, phase=why)
                return True
            now = time.time()
            if self.use_vision and now - last_ui >= 3.0:
                # Lightweight sync: dismiss only if something modal-like is present.
                mode = self._sync_ui(handle_modal=True)
                if on_progress:
                    on_progress(
                        index=index,
                        total=total,
                        phase=(
                            f"wait status game_turn={current} baseline={baseline} "
                            f"turn_started={started} (from {started_baseline}) "
                            f"ui={mode.value} rounds={self._julii_round_starts} "
                            f"autosaves={self._autosave_events}"
                        ),
                    )
                if mode in (CampaignUiMode.MODAL, CampaignUiMode.PAUSE, CampaignUiMode.PRE_BATTLE):
                    if on_progress:
                        on_progress(
                            index=index,
                            total=total,
                            phase=f"dialog while waiting: {mode.value} (resolving)",
                        )
                    if now - self._last_debug_capture_ts >= 10.0:
                        hwnd = self._resolve_hwnd()
                        if hwnd is not None:
                            stamp = int(now)
                            out = f"data/runtime/dialog-{index}-{stamp}.png"
                            if save_debug_capture(hwnd, out):
                                on_progress(
                                    index=index,
                                    total=total,
                                    phase=f"saved dialog frame: {out}",
                                )
                                self._last_debug_capture_ts = now
                last_ui = now
            time.sleep(0.25)
        _LOGGER.warning(
            "timed out waiting for player turn advance "
            "(baseline=%s now=%s turn_started=%s from %s rounds=%s autosaves=%s)",
            baseline,
            self._known_game_turn(),
            self.turn_started,
            started_baseline,
            self._julii_round_starts,
            self._autosave_events,
        )
        return False

    def _run_combat_step(
        self,
        *,
        on_progress: Callable[..., None] | None = None,
        index: int = 0,
        total: int = 0,
    ) -> None:
        """Acquire the whole stack, order one attack, and resolve the battle it opens.

        A refusal is a normal outcome, not a turn failure: on most turns no target
        offers the attack glyph, and the alternative to refusing is a bodyguard
        charging a settlement alone or a click that declares a war.
        """
        if not (self.use_vision and self.attack_enabled and self.attack_targets):
            return
        director = self.combat_director()
        if director is None:
            return

        if self.army_lists_row_norm is not None:
            selection = director.acquire_stack(self.army_lists_row_norm)
        else:
            selection = director.selected_stack()
        if not selection.safe_to_attack:
            if on_progress:
                on_progress(
                    index=index,
                    total=total,
                    phase=f"attack skipped — {selection.reason}",
                )
            self._publish(
                EventKind.INTENT_DECLARED,
                {"summary": f"attack skipped — {selection.reason}"},
            )
            return

        for target in self.attack_targets:
            outcome = director.attack(target)
            if not outcome.ordered:
                continue
            self.attacks_ordered += 1
            self.battles_resolved += int(outcome.battle_resolved)
            self._publish(
                EventKind.INTENT_DECLARED,
                {"summary": f"attack {target} with {outcome.unit_cards} unit cards"},
            )
            if on_progress:
                on_progress(
                    index=index,
                    total=total,
                    phase=(
                        f"attacked {target} with {outcome.unit_cards} unit cards, "
                        f"battle {'resolved' if outcome.battle_resolved else 'left open'}"
                    ),
                )
            return

        if on_progress:
            on_progress(
                index=index,
                total=total,
                phase=f"no target offered an attack order ({director.last_reason})",
            )

    def run_turn_stub(
        self,
        *,
        wait_for_next_turn: bool = True,
        on_progress: Callable[..., None] | None = None,
        index: int = 0,
        total: int = 0,
    ) -> bool:
        """Clear modals, observe, optional move, End Turn only on open map."""
        self._refresh_turn_from_message_log()
        if on_progress:
            on_progress(index=index, total=total, phase=f"sync UI on turn {self.state.turn}")
        self._sync_ui(handle_modal=True)

        if not self.state.allows_campaign_orders():
            _LOGGER.info("skip turn — state=%s ui=%s", self.state.state.value, self.last_ui_mode)
            if on_progress:
                on_progress(
                    index=index,
                    total=total,
                    phase=f"skip — state={self.state.state.value} ui={self.last_ui_mode}",
                )
            return False

        assert self.planner is not None
        directive = self.current_directive()
        orders = self.planner.plan(self.belief, directive)
        self.last_orders = [o.command for o in orders]
        intent = {"objective": "campaign_turn", "turn": self.state.turn, "ui": self.last_ui_mode}
        if directive is not None:
            # Recorded on the intent so a run can be read back against what AO asked
            # for, including the turns where it asked for nothing.
            intent["directive"] = {
                "objective": directive.intent.objective,
                "question_id": self._directive_question_id,
                "commentary": directive.commentary,
            }
            if on_progress:
                on_progress(
                    index=index,
                    total=total,
                    phase=f"directive: {self.last_directive}",
                )
            self._publish(
                EventKind.AO_RESULT,
                {"summary": f"directive {self.last_directive}", "question_id": self._directive_question_id},
            )
        action = {"type": "campaign_plan", "commands": self.last_orders}
        expected = {"state": GameState.CAMPAIGN_MAP.value}

        record = self.intent_writer.declare(
            question_id=self._directive_question_id or "hardcoded-turn",
            ply_or_tick=self.state.turn,
            state_hash=str(self.state.turn or 0),
            intent=intent,
            action=action,
            expected_effect=expected,
        )

        if on_progress:
            on_progress(
                index=index,
                total=total,
                phase=f"orders on turn {self.state.turn}: {', '.join(self.last_orders)}",
            )
        self._publish(
            EventKind.INTENT_DECLARED,
            {"summary": f"turn {self.state.turn}: {', '.join(self.last_orders)}"},
        )

        start = time.perf_counter()
        ok = True
        for order in orders:
            sent = self.actuator.send(order.command, require_campaign=True)
            if not sent:
                _LOGGER.warning("order failed: %s (%s)", order.command, order.reason)
            ok = sent and ok

        self._run_combat_step(on_progress=on_progress, index=index, total=total)

        if self.auto_end_turn and ok:
            ready = self.wait_until_ready_for_end_turn(
                on_progress=on_progress,
                index=index,
                total=total,
            )
            if not ready:
                if on_progress:
                    on_progress(
                        index=index,
                        total=total,
                        phase="WARN End Turn skipped — UI not ready",
                    )
                ok = False
            else:
                turn_before = self._known_game_turn()
                # Read before pressing, because Rome may hand the turn back while
                # `end_turn` is still confirming its own actuation.
                before = newest_turn_start_marker()
                handback_since = before[1] if before else 0.0
                ended = self.actuator.end_turn(on_heartbeat=self.on_heartbeat)
                if on_progress:
                    phase = (
                        f"ended turn (game_turn={turn_before})"
                        if ended
                        else "WARN End Turn did not register"
                    )
                    on_progress(index=index, total=total, phase=phase)
                ok = ended and ok
                if wait_for_next_turn and ok:
                    self._julii_turn_ready = False
                    if on_progress:
                        on_progress(
                            index=index,
                            total=total,
                            phase=f"waiting for next Julii turn (after {turn_before})",
                        )
                    ok = (
                        self.wait_for_turn_event(
                            on_progress=on_progress,
                            index=index,
                            total=total,
                            turn_before=turn_before,
                            since=handback_since,
                        )
                        and ok
                    )
                    if ok:
                        self._julii_turn_ready = True
                        # The wait loop spends its time classifying AI-turn banners and
                        # hover tooltips as modals, and returns the moment the turn
                        # lands without looking again. Verifying on that leftover state
                        # failed a cycle whose turn had demonstrably advanced.
                        self._sync_ui(handle_modal=False)

        if wait_for_next_turn and ok and not self.auto_end_turn:
            # Orders-only mode: still wait for an external turn advance if requested.
            self._julii_turn_ready = False
            if on_progress:
                on_progress(
                    index=index,
                    total=total,
                    phase="waiting for next Julii turn",
                )
            ok = self.wait_for_turn_event(on_progress=on_progress, index=index, total=total) and ok
            if ok:
                self._julii_turn_ready = True

        observed = {"state": self.state.state.value, "ui": self.last_ui_mode}
        outcomes = self.verification.verify(action, expected, observed=observed)
        verified = all(o.result != VerificationResult.FAIL for o in outcomes)
        ok = ok and verified
        self._publish(
            EventKind.VERIFICATION,
            {
                "ok": bool(ok),
                "summary": f"turn {self.state.turn} ui={self.last_ui_mode} game_turn={self._known_game_turn()}",
            },
        )

        latency_ms = (time.perf_counter() - start) * 1000.0
        observed["verification"] = [o.result.value for o in outcomes]
        self.intent_writer.complete(record, observed_effect=observed, latency_ms=latency_ms)
        return ok

    def run_turns(
        self,
        n: int,
        *,
        require_ok: bool = True,
        wait_for_next_turn: bool = True,
        on_progress: Callable[..., None] | None = None,
    ) -> dict[str, int]:
        ok_count = 0
        fail_count = 0
        self.poll_observation()
        self._refresh_turn_from_message_log()
        self._publish(EventKind.CONTROL_STATE, {"state": "agent"})
        turn_at_start = self.turns_ended
        for i in range(n):
            self.poll_observation()
            idx = i + 1
            if self.run_turn_stub(
                wait_for_next_turn=wait_for_next_turn,
                on_progress=on_progress,
                index=idx,
                total=n,
            ):
                ok_count += 1
                if on_progress:
                    on_progress(index=idx, total=n, phase="turn cycle complete", ok=True)
            else:
                fail_count += 1
                if on_progress:
                    on_progress(index=idx, total=n, phase="turn cycle failed or timed out", ok=False)
                if require_ok:
                    break
        self._refresh_turn_from_message_log()
        turn_at_end = self.turns_ended
        self._publish(EventKind.CONTROL_STATE, {"state": "idle"})
        return {
            "turns_ok": ok_count,
            "turns_failed": fail_count,
            "requested": n,
            "desyncs": fail_count,
            # Endpoints are reported for context only. They are read from Rome's saves
            # folder, which keeps earlier campaigns, so subtracting them can produce a
            # negative and once scored an 18-turn run as zero.
            "game_turn_start": turn_at_start,
            "game_turn_end": turn_at_end,
            # Every advance counted as it was proven by a new `Turn N Start.sav`, so a
            # cycle still cannot pass by reporting success without moving the game on.
            "turns_advanced": self._turn_advances,
            "turn_baseline_resets": self._turn_baseline_resets,
            "attacks_ordered": self.attacks_ordered,
            "battles_resolved": self.battles_resolved,
        }
