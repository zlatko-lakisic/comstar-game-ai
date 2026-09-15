"""Publish trained ONNX → overlay detect_rtw_campaign.yaml + print Ada cache hint.

Computes sha256, writes agent YAML from the example template, optionally copies
the ONNX next to a share path for HTTPS hosting / Ada artifact seed.

Usage::

    python scripts/detection/publish_rtw_weights.py --onnx path/to/yolox_rtw_nano.onnx
    python scripts/detection/publish_rtw_weights.py --onnx model.onnx --uri https://host/yolox_rtw_nano.onnx
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "overlay" / "agent_providers" / "detect_rtw_campaign.yaml.example"
ACTIVE = ROOT / "overlay" / "agent_providers" / "detect_rtw_campaign.yaml"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onnx", type=Path, required=True)
    parser.add_argument(
        "--uri",
        default="",
        help="HTTPS URI Ada can fetch (default artifact://<sha256>)",
    )
    parser.add_argument(
        "--copy-to",
        type=Path,
        default=None,
        help="Optional directory to copy the ONNX into for hosting",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Write overlay/agent_providers/detect_rtw_campaign.yaml",
    )
    args = parser.parse_args()

    if not args.onnx.is_file():
        print(f"FAIL: missing {args.onnx}", flush=True)
        return 2
    if not EXAMPLE.is_file():
        print(f"FAIL: missing example {EXAMPLE}", flush=True)
        return 3

    digest = _sha256(args.onnx)
    uri = args.uri.strip() or f"artifact://{digest}"
    print(f"sha256={digest}", flush=True)
    print(f"uri={uri}", flush=True)
    print(f"size_bytes={args.onnx.stat().st_size}", flush=True)

    if args.copy_to is not None:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        dest = args.copy_to / args.onnx.name
        shutil.copy2(args.onnx, dest)
        print(f"copied → {dest}", flush=True)

    text = EXAMPLE.read_text(encoding="utf-8")
    # Drop "example only" banner lines for active file
    lines = [
        ln
        for ln in text.splitlines()
        if not ln.startswith("# Example only")
        and not ln.startswith("#   python scripts")
        and not ln.startswith("# Active YAML")
    ]
    body = "\n".join(lines) + "\n"
    body = body.replace("REPLACE_WITH_HTTPS_OR_ARTIFACT_URI", uri)
    body = body.replace("REPLACE_WITH_64_HEX_SHA256", digest)

    out_path = ACTIVE if args.activate else ROOT / "data" / "detection" / "detect_rtw_campaign.yaml.generated"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    if not args.activate:
        print("Re-run with --activate to install into overlay/agent_providers/", flush=True)
    print(
        "Ada: ensure weights are in AGENTIC_DETECTION_ARTIFACT_CACHE as "
        f"{digest}.onnx (or fetchable via uri), then refresh Reach overlay.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
