"""Label corrections sit beside labels.json and do not rewrite it."""

import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "score_cursorstat_gate.py"
_SPEC = importlib.util.spec_from_file_location("score_cursorstat_gate", _PATH)
score = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(score)

_LABELS = [{"file": "sweep0_00.png", "xy": [10, 20], "label_source": "operator"}]


def _write_labels(session: Path) -> bytes:
    path = session / "labels.json"
    path.write_text(json.dumps(_LABELS, indent=2) + "\n", encoding="utf-8")
    return path.read_bytes()


def test_valid_correction_is_stored(tmp_path: Path):
    _write_labels(tmp_path)
    entry = score.record_correction(
        tmp_path,
        "sweep0_00.png",
        (11, 20),
        "pos line reads 11, 20",
        {"sweep0_00.png"},
        timestamp="2026-10-05T22:00:00Z",
    )
    assert entry == {
        "frame": "sweep0_00.png",
        "old_xy": [10, 20],
        "new_xy": [11, 20],
        "reason": "pos line reads 11, 20",
        "timestamp": "2026-10-05T22:00:00Z",
    }
    stored = json.loads((tmp_path / "label_corrections.json").read_text(encoding="utf-8"))
    assert stored == [entry]


def test_correction_refused_when_frame_is_not_on_the_wrong_list(tmp_path: Path):
    before = _write_labels(tmp_path)
    with pytest.raises(score.CorrectionRefused):
        score.record_correction(
            tmp_path,
            "sweep0_01.png",
            (11, 20),
            "not a wrong read",
            {"sweep0_00.png"},
            timestamp="2026-10-05T22:00:00Z",
        )
    assert not (tmp_path / "label_corrections.json").exists()
    assert (tmp_path / "labels.json").read_bytes() == before


def test_labels_json_is_left_unchanged(tmp_path: Path):
    before = _write_labels(tmp_path)
    score.record_correction(
        tmp_path,
        "sweep0_00.png",
        (12, 21),
        "operator recheck",
        {"sweep0_00.png"},
        timestamp="2026-10-05T22:01:00Z",
    )
    assert (tmp_path / "labels.json").read_bytes() == before
