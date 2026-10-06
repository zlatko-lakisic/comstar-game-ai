"""Label corrections sit beside labels.json and do not rewrite it."""

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

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


def test_regression_mode_reports_counts_and_does_not_write_a_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    sessions = tmp_path / "sessions"
    gate = sessions / "reg"
    gate.mkdir(parents=True)
    labels = []
    for name, xy in (("a.png", [1, 2]), ("b.png", [3, 4]), ("c.png", [5, 6])):
        Image.new("RGB", (4, 4)).save(gate / name)
        labels.append({"file": name, "xy": xy, "label_source": "operator"})
    (gate / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    split_path = tmp_path / "split.json"
    report = tmp_path / "gate_report_v2.json"
    split_path.write_text(
        json.dumps({"gates_reader": False, "regression": ["reg"], "test": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(score, "SPLIT", split_path)
    monkeypatch.setattr(score, "REPORT", report)
    monkeypatch.setattr(score, "SESSIONS", sessions)

    def fake_read(path: Path):
        got = {"a.png": (1, 2), "b.png": None, "c.png": (0, 0)}[path.name]
        return got, None, ""

    monkeypatch.setattr(score, "_read_xy", fake_read)
    assert score.main(["--regression"]) == 0
    assert not report.exists()
    assert not (gate / "review_crops").exists()
    out = capsys.readouterr().out
    assert "read=1" in out
    assert "miss=1" in out
    assert "wrong=1" in out


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
