"""Automate train → ONNX export → overlay publish (#3).

Requires Megvii YOLOX + CUDA (prefer Ada). Clones YOLOX if needed, downloads
nano pretrained weights, trains on ``data/detection/coco``, exports ONNX, publishes.

Usage::

    python scripts/detection/automate_train.py --yolox-root D:/src/YOLOX --activate
    python scripts/detection/automate_train.py --skip-train --onnx path/to/model.onnx --activate
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "scripts" / "detection" / "yolox_exps" / "rtw_nano.py"
PUBLISH = ROOT / "scripts" / "detection" / "publish_rtw_weights.py"
OFFLINE = ROOT / "scripts" / "detection" / "offline_val_check.py"

YOLOX_GIT = "https://github.com/Megvii-BaseDetection/YOLOX.git"
NANO_PRETRAIN = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/"
    "0.1.1rc0/yolox_nano.pth"
)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(cwd) if cwd else None, env=env)


def _ensure_yolox(yolox_root: Path) -> int:
    if (yolox_root / "tools" / "train.py").is_file():
        return 0
    yolox_root.parent.mkdir(parents=True, exist_ok=True)
    if not yolox_root.exists():
        return _run(["git", "clone", "--depth", "1", YOLOX_GIT, str(yolox_root)])
    print(f"FAIL: {yolox_root} exists but is not a YOLOX tree", flush=True)
    return 2


def _ensure_pretrain(path: Path) -> int:
    if path.is_file():
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {NANO_PRETRAIN} → {path}", flush=True)
    try:
        urllib.request.urlretrieve(NANO_PRETRAIN, path)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: download pretrain: {exc}", flush=True)
        return 3
    return 0


def _find_ckpt(yolox_root: Path, exp_name: str = "rtw_yolox_nano") -> Path | None:
    candidates = sorted(
        yolox_root.glob(f"YOLOX_outputs/{exp_name}/**/*.pth"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if "best" in p.name.lower() or "latest" in p.name.lower():
            return p
    return candidates[0] if candidates else None


def _install_exp(yolox_root: Path, epochs: int) -> Path:
    exp_dst = yolox_root / "exps" / "comstar" / "rtw_nano.py"
    exp_dst.parent.mkdir(parents=True, exist_ok=True)
    text = EXP.read_text(encoding="utf-8")
    text = re.sub(r"self\.max_epoch\s*=\s*\d+", f"self.max_epoch = {epochs}", text)
    exp_dst.write_text(text, encoding="utf-8")
    return exp_dst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yolox-root",
        type=Path,
        default=Path(os.environ.get("YOLOX_ROOT", ROOT / "third_party" / "YOLOX")),
    )
    parser.add_argument(
        "--coco",
        type=Path,
        default=ROOT / "data" / "detection" / "coco",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--gpus", type=int, default=1)
    parser.add_argument(
        "--pretrain",
        type=Path,
        default=ROOT / "data" / "detection" / "weights" / "yolox_nano.pth",
    )
    parser.add_argument(
        "--onnx-out",
        type=Path,
        default=ROOT / "data" / "detection" / "weights" / "yolox_rtw_nano.onnx",
    )
    parser.add_argument("--skip-clone", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--uri", default="")
    parser.add_argument("--onnx", type=Path, default=None)
    parser.add_argument("--offline-check-image", type=Path, default=None)
    parser.add_argument("--no-fp16", action="store_true")
    args = parser.parse_args()

    if args.onnx is not None:
        args.skip_train = True
        args.skip_export = True
        args.onnx_out = args.onnx

    train_ann = args.coco / "annotations" / "instances_train2017.json"
    if not args.skip_train and not train_ann.is_file():
        print(
            f"FAIL: missing {train_ann} — run automate_dataset.py first",
            flush=True,
        )
        return 2

    if not args.skip_clone and not args.skip_train:
        rc = _ensure_yolox(args.yolox_root)
        if rc != 0:
            return rc

    env = os.environ.copy()
    env["COMSTAR_DETECTION_COCO"] = str(args.coco.resolve())
    env["PYTHONPATH"] = str(args.yolox_root.resolve()) + os.pathsep + env.get("PYTHONPATH", "")

    if not args.skip_train:
        rc = _ensure_pretrain(args.pretrain)
        if rc != 0:
            return rc
        exp_dst = _install_exp(args.yolox_root, args.epochs)
        train_cmd = [
            sys.executable,
            "tools/train.py",
            "-f",
            str(exp_dst),
            "-d",
            str(args.gpus),
            "-b",
            str(args.batch),
            "-c",
            str(args.pretrain.resolve()),
        ]
        if not args.no_fp16:
            train_cmd.append("--fp16")
        rc = _run(train_cmd, cwd=args.yolox_root, env=env)
        if rc != 0:
            return rc

    if not args.skip_export:
        ckpt = _find_ckpt(args.yolox_root)
        if ckpt is None:
            print("FAIL: no checkpoint under YOLOX_outputs/", flush=True)
            return 4
        print(f"using ckpt {ckpt}", flush=True)
        args.onnx_out.parent.mkdir(parents=True, exist_ok=True)
        exp_dst = _install_exp(args.yolox_root, args.epochs)
        export_cmd = [
            sys.executable,
            "tools/export_onnx.py",
            "-f",
            str(exp_dst),
            "-c",
            str(ckpt),
            "--output-name",
            str(args.onnx_out.resolve()),
            "--decode_in_inference",
            "False",
        ]
        rc = _run(export_cmd, cwd=args.yolox_root, env=env)
        if rc != 0:
            # Older export_onnx without the flag
            rc = _run(export_cmd[:-2], cwd=args.yolox_root, env=env)
        if rc != 0:
            return rc
        if not args.onnx_out.is_file():
            alt = args.yolox_root / args.onnx_out.name
            if alt.is_file():
                shutil.move(str(alt), str(args.onnx_out))
        if not args.onnx_out.is_file():
            print(f"FAIL: export did not produce {args.onnx_out}", flush=True)
            return 5

    if args.offline_check_image and args.onnx_out.is_file():
        _run(
            [
                sys.executable,
                str(OFFLINE),
                "--onnx",
                str(args.onnx_out),
                "--image",
                str(args.offline_check_image),
            ]
        )

    if not args.skip_publish:
        if not args.onnx_out.is_file():
            print(f"FAIL: missing onnx {args.onnx_out}", flush=True)
            return 6
        pub = [sys.executable, str(PUBLISH), "--onnx", str(args.onnx_out)]
        if args.uri:
            pub.extend(["--uri", args.uri])
        if args.activate:
            pub.append("--activate")
        rc = _run(pub)
        if rc != 0:
            return rc

    print("DONE train/export/publish pipeline", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
