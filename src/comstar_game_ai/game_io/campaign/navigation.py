"""Getting the campaign camera somewhere useful.

An agent that loses the camera is blind, and the campaign map is large enough that
a camera parked in a corner of Arabia can see nothing of a Julii campaign. Everything
here was tested by having the camera deliberately parked at the far map edge — the
decorative border and the black void beyond it in view — and then trying to get back.

The finding that matters is that **there is exactly one exact primitive and one
recovery**, and both are the same key. `capital_zoom` is bound to Home and lands on
the faction capital in a single press, from anywhere, with no calibration. It also
selects the capital as a side effect. Because it always works, exploration is cheap:
anything below can be tried freely, since Home undoes getting lost.

The ranking below is by *precision*, which is not the same as usefulness. Panning has
its place; it just cannot be trusted to cover distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Accuracy(Enum):
    #: Lands on a named target. Verified by a press that produced the intended view.
    EXACT = "exact"
    #: Moves the camera to roughly the right part of the world. Needs a look afterwards.
    COARSE = "coarse"
    #: Moves the camera by an amount that did not scale predictably with input.
    IMPRECISE = "imprecise"


@dataclass(frozen=True)
class Strategy:
    id: str
    accuracy: Accuracy
    #: What it needs before it will work.
    requires: str
    how: str
    evidence: tuple[str, ...] = ()
    note: str = ""


STRATEGIES: tuple[Strategy, ...] = (
    Strategy(
        id="capital_zoom",
        accuracy=Accuracy.EXACT,
        requires="nothing — works from a bare campaign map at any camera position",
        how="tap Home (action capital_zoom, bound in the strat section of both keysets)",
        evidence=(
            "from the far east map edge, one press framed Arretium: nav_start.png -> nav_home.png",
            "used as the recovery step five separate times in one session, never failed",
            "the game names the action 'Zoom to capital' in the shortcut string table",
        ),
        note=(
            "The primitive to build on. Also selects the capital, so the bottom HUD bar "
            "switches to its governor — convenient, but it means the camera move is not "
            "side-effect free with respect to selection."
        ),
    ),
    Strategy(
        id="locate_via_lists",
        accuracy=Accuracy.EXACT,
        requires="Ctrl+5 (Lists), Settlements sub-tab, a row selected",
        how=(
            "open Lists, click the settlement's row, then the magnifier in the footer, "
            "which the game names 'Locate position of settlement'"
        ),
        evidence=(
            "camera parked on an empty western coast, then locate framed Ariminum and "
            "switched the HUD to its governor Quintus Julius: loc_1 -> loc_4",
        ),
        note=(
            "The general form of capital_zoom: reaches any settlement we own, not just the "
            "capital. Closes the Lists panel on use, so it costs no separate dismissal. "
            "Its two neighbouring footer buttons are not harmless — the third sets the "
            "faction capital permanently — so click the magnifier by position, carefully."
        ),
    ),
    Strategy(
        id="radar_click",
        accuracy=Accuracy.COARSE,
        requires="the radar, which is always present unless toggled off with Ctrl+M",
        how="click a point on the radar to centre the camera on the matching map point",
        evidence=(
            "a click at (0.897, 0.140) moved the camera to an empty coast, luminance delta 30.6",
            "a click on the computed Julii centroid landed inside our territory but with no "
            "settlement in frame: nav_blob_julii.png",
        ),
        note=(
            "Coarse for a structural reason, not a fixable one: the radar is about 228 px "
            "wide for the whole Mediterranean, so one radar pixel is a long march, and a "
            "province centroid is not a settlement. Good for 'get me to that region', then "
            "hand off to zoom and a look. Pair with zoom_out first so the landing frame "
            "covers enough ground to contain something."
        ),
    ),
    Strategy(
        id="arrow_pan",
        accuracy=Accuracy.IMPRECISE,
        requires="nothing; not in descr_shortcuts.txt, so Rome handles it natively",
        how="tap or hold the arrow keys",
        evidence=(
            "12 taps of Down drove the camera from Italy to the map's east edge",
            "4 taps of Down from the same start moved it almost not at all: wide_down4.png",
        ),
        note=(
            "Distance per press did not scale with the number of presses, so this is for "
            "nudging a target into frame, never for crossing the map. Reach for Home or "
            "locate_via_lists instead and pan only to fine-tune."
        ),
    ),
)

BY_ID: dict[str, Strategy] = {s.id: s for s in STRATEGIES}

#: Campaign camera zoom, from the strat section of the moderntw keyset.
ZOOM_IN_ACTION = "zoom_in"
ZOOM_OUT_ACTION = "zoom_out"

#: Both clamp well short of a whole-map view, and the clamp is reached in well under
#: ten presses, so repeating them past that buys nothing. At full zoom-out the whole
#: Italian peninsula fits in frame, which is the level at which radar_click becomes
#: usable and at which settlement labels collapse to a crest and a tier glyph.
ZOOM_PRESSES_TO_CLAMP = 8


def exact() -> tuple[Strategy, ...]:
    """The strategies that land on a named target. Prefer these."""
    return tuple(s for s in STRATEGIES if s.accuracy is Accuracy.EXACT)


#: Hovering the radar returns a tooltip naming the region and its owning faction —
#: "Latium / S.P.Q.R." with the faction crest — without moving the camera at all. That
#: makes the radar a survey instrument as well as a navigation control: an agent can
#: enumerate who owns what by sweeping the cursor over it, at zero risk, because a
#: hover cannot change game state. Discovered by accident while the cursor was resting
#: on the radar after a click.
RADAR_HOVER_YIELDS_REGION_AND_OWNER = True

#: The strategic overlay (Tab) is read-only. A click inside it moved the camera not at
#: all and selected nothing, so it cannot be used as a big clickable map. Recorded
#: because it is the obvious thing to try — it looks exactly like a navigable map.
OVERLAY_IS_CLICKABLE = False
