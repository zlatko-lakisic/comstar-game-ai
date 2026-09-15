"""Blocking campaign deliberation for Process A.

Phase-2 used to run Process B on a timer while the game advanced turns from a
stale file. That kept Ada busy without gating End Turn. This helper keeps one
Reach session on a background loop and exposes a sync ``deliberate(turn)`` that
does not return until the director has written ``directive.json``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from typing import TYPE_CHECKING

from comstar_game_ai.agent.runtime import AgentRuntime
from comstar_game_ai.shared.config import load_config
from comstar_game_ai.shared.ipc.publisher import EventPublisher
from comstar_game_ai.shared.runtime.directive_store import DirectiveStore

if TYPE_CHECKING:
    from PIL import Image

    from comstar_game_ai.game_io.campaign.map_target_vision import MapTargetHit, SettlementViewHit

_LOGGER = logging.getLogger(__name__)


def _director_timeout_s() -> float:
    """Abort ceiling for one director turn (includes a possible hold-floor reask)."""
    cfg = load_config()
    ao = cfg.get("ao") or {}
    # chat_timeout_sec is per Ollama call; hold floor may reask once.
    per_call = float(ao.get("chat_timeout_sec") or 900.0)
    return max(120.0, per_call * 2.0 + 60.0)


class SyncCampaignDeliberator:
    """Own a Reach session and block callers until each campaign directive lands."""

    def __init__(
        self,
        *,
        directive_store: DirectiveStore | None = None,
        publisher: EventPublisher | None = None,
        player_faction: str = "julii",
        log_path: Path | str | None = None,
    ) -> None:
        self._runtime = AgentRuntime(
            player_faction=player_faction,
            directive_store=directive_store or DirectiveStore(),
            publisher=publisher or EventPublisher(),
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._log_path = Path(log_path) if log_path else None
        self._file_handler: logging.Handler | None = None
        self._closed = False

    @property
    def directive_store(self) -> DirectiveStore:
        return self._runtime.directive_store

    def start(self, *, timeout_s: float = 120.0) -> None:
        if self._thread is not None:
            return
        if self._log_path is not None:
            self._attach_log_file(self._log_path)
        self._thread = threading.Thread(
            target=self._run_loop,
            name="sync-campaign-deliberator",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=timeout_s):
            raise TimeoutError(
                f"AO session did not become ready within {timeout_s:.0f}s"
            )
        if self._start_error is not None:
            raise RuntimeError("AO session failed to start") from self._start_error
        _LOGGER.info("sync deliberator ready")

    def deliberate(
        self,
        turn: int,
        *,
        timeout_s: float | None = None,
        on_heartbeat: Callable[[], None] | None = None,
    ) -> None:
        """Block until the director finishes for ``turn`` (writes directive store)."""
        if self._closed or self._loop is None:
            raise RuntimeError("sync deliberator is not running")
        ceiling = _director_timeout_s() if timeout_s is None else float(timeout_s)
        _LOGGER.info("blocking on AO director for turn %s (ceiling %.0fs)", turn, ceiling)
        fut = asyncio.run_coroutine_threadsafe(
            self._runtime.deliberate_campaign_turn(int(turn)),
            self._loop,
        )
        deadline = time.monotonic() + ceiling
        last_status = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fut.cancel()
                raise TimeoutError(
                    f"AO director did not finish turn {turn} within {ceiling:.0f}s"
                )
            try:
                fut.result(timeout=min(5.0, remaining))
                return
            except concurrent.futures.TimeoutError:
                if on_heartbeat is not None:
                    on_heartbeat()
                try:
                    from comstar_game_ai.agent.reach.agent_lifecycle import (
                        read_agent_status,
                    )

                    status = read_agent_status() or {}
                    line = str(status.get("summary") or status.get("state") or "")
                    if line and line != last_status:
                        _LOGGER.info("AO agent: %s", line)
                        print(f"INFO AO agent: {line}", flush=True)
                        last_status = line
                except Exception:
                    pass

    def query_map_target(
        self,
        image: Image.Image,
        label: str,
        *,
        hint_quadrant: str = "",
        timeout_s: float = 600.0,
        on_heartbeat: Callable[[], None] | None = None,
    ) -> MapTargetHit | None:
        """Locate a settlement on ``image`` using this session (no second Reach start).

        A second ``ReachSession`` while the deliberator is live re-registers the same
        overlay agents and routinely returns empty/unparseable map-target answers —
        which is what produced ``MARCH vision: miss for 'segesta' (none)`` in live
        runs. Always route Phase-2 map vision through this method.
        """
        if self._closed or self._loop is None or self._runtime.session is None:
            raise RuntimeError("sync deliberator is not running")

        from comstar_game_ai.game_io.campaign.map_target_vision import (
            query_map_target_on_session,
        )

        fut = asyncio.run_coroutine_threadsafe(
            query_map_target_on_session(
                self._runtime.session,
                image=image,
                label=label,
                hint_quadrant=hint_quadrant,
                timeout_s=timeout_s,
            ),
            self._loop,
        )
        deadline = time.monotonic() + float(timeout_s) + 5.0
        last_status = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fut.cancel()
                _LOGGER.warning(
                    "map-target vision abort after %.0fs safety net", timeout_s
                )
                return None
            try:
                return fut.result(timeout=min(2.0, remaining))
            except concurrent.futures.TimeoutError:
                if on_heartbeat is not None:
                    on_heartbeat()
                try:
                    from comstar_game_ai.agent.reach.agent_lifecycle import (
                        read_agent_status,
                    )

                    status = read_agent_status() or {}
                    line = str(status.get("summary") or status.get("state") or "")
                    if line and line != last_status:
                        print(f"INFO AO agent: {line}", flush=True)
                        last_status = line
                except Exception:
                    pass

    def query_settlement_scan(
        self,
        image: Image.Image,
        *,
        prefer_label: str = "",
        timeout_s: float = 600.0,
        on_heartbeat: Callable[[], None] | None = None,
    ) -> list[SettlementViewHit]:
        """Scan every settlement oval on ``image`` via this Reach session."""
        if self._closed or self._loop is None or self._runtime.session is None:
            raise RuntimeError("sync deliberator is not running")

        from comstar_game_ai.game_io.campaign.map_target_vision import (
            query_settlement_scan_on_session,
        )

        fut = asyncio.run_coroutine_threadsafe(
            query_settlement_scan_on_session(
                self._runtime.session,
                image=image,
                prefer_label=prefer_label,
                timeout_s=timeout_s,
            ),
            self._loop,
        )
        deadline = time.monotonic() + float(timeout_s) + 5.0
        last_status = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fut.cancel()
                _LOGGER.warning(
                    "settlement scan abort after %.0fs safety net", timeout_s
                )
                return []
            try:
                return fut.result(timeout=min(2.0, remaining))
            except concurrent.futures.TimeoutError:
                if on_heartbeat is not None:
                    on_heartbeat()
                try:
                    from comstar_game_ai.agent.reach.agent_lifecycle import (
                        read_agent_status,
                    )

                    status = read_agent_status() or {}
                    line = str(status.get("summary") or status.get("state") or "")
                    if line and line != last_status:
                        print(f"INFO AO agent: {line}", flush=True)
                        last_status = line
                except Exception:
                    pass

    def query_object_detection(
        self,
        image: Image.Image,
        *,
        agent_provider_id: str | None = None,
        timeout_s: float = 180.0,
        question_id: str = "map-object-detect",
        on_heartbeat: Callable[[], None] | None = None,
    ):
        """Run AO ``object_detection`` on ``image`` via this Reach session."""
        if self._closed or self._loop is None or self._runtime.session is None:
            raise RuntimeError("sync deliberator is not running")

        from comstar_game_ai.agent.compositor.views import ViewBudget, compose_reach_images
        from comstar_game_ai.agent.reach.director import (
            DETECT_YOLOX_NANO,
            _bridge_direct_agent,
            _extract_text,
            _wait_ready,
        )
        from comstar_game_ai.game_io.campaign.map_object_detection import (
            parse_detection_payload,
        )
        from comstar_game_ai.shared.config import load_config

        cfg = load_config()
        ao = cfg.get("ao") or {}
        agent_id = (
            agent_provider_id
            or str(ao.get("detection_agent") or DETECT_YOLOX_NANO).strip()
            or DETECT_YOLOX_NANO
        )

        images, _meta = compose_reach_images(
            [image],
            ViewBudget(max_images=1, jpeg_quality=90),
            names=[f"{question_id}.jpg"],
        )

        async def _call():
            session = self._runtime.session
            if session is None:
                raise RuntimeError("Reach session missing")
            bridge = session.bridge
            if not bridge.is_active or getattr(bridge, "_ws", None) is None:
                raise RuntimeError(
                    f"Session bridge is not active "
                    f"(state={getattr(bridge, 'state', None)!s} "
                    f"error={getattr(bridge, 'error', None)!r}) — "
                    "cannot run object detection"
                )
            # Catalog detectors (e.g. detect_yolox_nano) are not overlay agents and
            # never emit session agent_state — waiting for READY hangs forever.
            registered = {str(x) for x in (bridge.registered_agent_ids or [])}
            if agent_id in registered or bridge.agent_state(agent_id) is not None:
                await _wait_ready(session, agent_id)
            result = await _bridge_direct_agent(
                bridge,
                agent_provider_id=agent_id,
                text="detect",
                context="",
                question_id=question_id,
                priority="high",
                timeout=timeout_s,
                images=images,
            )
            return parse_detection_payload(_extract_text(result))

        fut = asyncio.run_coroutine_threadsafe(_call(), self._loop)
        deadline = time.monotonic() + float(timeout_s) + 30.0
        last_status = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                fut.cancel()
                raise TimeoutError(f"object detection abort after {timeout_s:.0f}s")
            try:
                return fut.result(timeout=min(2.0, remaining))
            except concurrent.futures.TimeoutError:
                if on_heartbeat is not None:
                    on_heartbeat()
                try:
                    from comstar_game_ai.agent.reach.agent_lifecycle import (
                        read_agent_status,
                    )

                    status = read_agent_status() or {}
                    line = str(status.get("summary") or status.get("state") or "")
                    if line and line != last_status:
                        print(f"INFO AO agent: {line}", flush=True)
                        last_status = line
                except Exception:
                    pass

    def stop(self, *, timeout_s: float = 30.0) -> None:
        if self._closed:
            return
        self._closed = True
        loop = self._loop
        if loop is not None and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self._runtime.stop(), loop)
            try:
                fut.result(timeout=timeout_s)
            except Exception:
                _LOGGER.exception("sync deliberator stop failed")
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        self._loop = None
        if self._file_handler is not None:
            logging.getLogger().removeHandler(self._file_handler)
            logging.getLogger("comstar_game_ai").removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None
        _LOGGER.info("sync deliberator stopped")

    def _attach_log_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handler.setLevel(logging.INFO)
        root = logging.getLogger("comstar_game_ai")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        self._file_handler = handler

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._runtime.start())
        except BaseException as exc:
            self._start_error = exc
            _LOGGER.exception("sync deliberator failed during start")
            self._ready.set()
            loop.close()
            self._loop = None
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                if self._runtime.session is not None:
                    loop.run_until_complete(self._runtime.stop())
            except Exception:
                _LOGGER.exception("sync deliberator cleanup failed")
            loop.close()
            self._loop = None
