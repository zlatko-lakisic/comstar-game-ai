"""Upload local RTW COCO to Ada and start Megvii YOLOX train (background).

Reads ``.cursor/secrets/.ada`` (IP/Username). Uses ``~/.ssh/id_rsa``.
Never prints credentials.

Usage::

    python scripts/detection/train_on_ada.py --probe-only
    python scripts/detection/train_on_ada.py --epochs 40
    python scripts/detection/train_on_ada.py --status
    python scripts/detection/train_on_ada.py --export
"""

from __future__ import annotations

import argparse
import io
import re
import tarfile
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[2]
SECRETS = ROOT / ".cursor" / "secrets" / ".ada"
COCO_LOCAL = ROOT / "data" / "detection" / "coco"
EXP_LOCAL = ROOT / "scripts" / "detection" / "yolox_exps" / "rtw_nano.py"
NANO_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/"
    "0.1.1rc0/yolox_nano.pth"
)


def _load_ada() -> tuple[str, str]:
    vals = dict(re.findall(r"^(\w+)=(.*)$", SECRETS.read_text(encoding="utf-8"), re.M))
    return vals["IP"], vals["Username"]


def _connect() -> paramiko.SSHClient:
    host, user = _load_ada()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.load_host_keys(str(Path.home() / ".ssh" / "known_hosts"))
    pkey = paramiko.RSAKey.from_private_key_file(str(Path.home() / ".ssh" / "id_rsa"))
    c.connect(host, username=user, pkey=pkey, timeout=20, allow_agent=False, look_for_keys=False)
    return c


def _run(c: paramiko.SSHClient, cmd: str, *, timeout: int = 120) -> tuple[int, str]:
    _stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", out + err)
    return code, text


def _tar_coco() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for sub in ("annotations", "train2017", "val2017"):
            path = COCO_LOCAL / sub
            if not path.exists():
                raise FileNotFoundError(path)
            tar.add(path, arcname=f"coco/{sub}")
        summary = COCO_LOCAL / "auto_label_summary.json"
        if summary.is_file():
            tar.add(summary, arcname="coco/auto_label_summary.json")
    return buf.getvalue()


def _remote_setup_script(*, epochs: int, batch: int, nano_url: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail
BASE="$HOME/comstar-yolox-rtw"
YOLOX="$BASE/YOLOX"
COCO="$BASE/coco"
VENV="$BASE/venv"
EPOCHS={epochs}
BATCH={batch}
mkdir -p "$BASE/weights" "$BASE/logs"
if [ ! -f "$YOLOX/tools/train.py" ]; then
  git clone --depth 1 https://github.com/Megvii-BaseDetection/YOLOX.git "$YOLOX"
fi
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -q --upgrade pip
python -m pip install -q numpy opencv-python-headless Pillow pycocotools tabulate tensorboard tqdm thop ninja
echo "Installing torch (CUDA 12.1 wheels if available)..."
python -m pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
cd "$YOLOX"
# Shallow clones often report version "unknown"; pin so setuptools accepts it.
python - <<'PY'
from pathlib import Path
p = Path("setup.py")
t = p.read_text(encoding="utf-8")
if 'version="0.3.0"' not in t:
    t2 = t.replace("version=version,", 'version="0.3.0",', 1)
    if t2 == t:
        t2 = t.replace("version=version", 'version="0.3.0"', 1)
    p.write_text(t2, encoding="utf-8")
print("setup version pin ok")
PY
# Skip onnx-simplifier (broken metadata on some pip/setuptools); train does not need it.
python -m pip install -q --no-build-isolation --no-deps -e .
python -m pip install -q loguru psutil onnx opencv-python-headless || true
python -c "from yolox.exp import get_exp; print('yolox ok')"
mkdir -p exps/comstar
cp -f "$BASE/rtw_nano.py" exps/comstar/rtw_nano.py
sed -i "s/self.max_epoch = [0-9]*/self.max_epoch = $EPOCHS/" exps/comstar/rtw_nano.py
if [ ! -f "$BASE/weights/yolox_nano.pth" ]; then
  curl -L --fail -o "$BASE/weights/yolox_nano.pth" "{nano_url}"
fi
export COMSTAR_DETECTION_COCO="$COCO"
export PYTHONPATH="$YOLOX:${{PYTHONPATH:-}}"
LOG="$BASE/logs/train_$(date +%Y%m%d-%H%M%S).log"
if [ -f "$BASE/logs/train.pid" ]; then
  old=$(cat "$BASE/logs/train.pid" || true)
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" || true
    sleep 2
  fi
fi
nohup python tools/train.py -f exps/comstar/rtw_nano.py -d 1 -b "$BATCH" -c "$BASE/weights/yolox_nano.pth" --fp16 >"$LOG" 2>&1 &
echo $! > "$BASE/logs/train.pid"
echo "$LOG" > "$BASE/logs/train.logpath"
echo TRAIN_PID=$(cat "$BASE/logs/train.pid")
echo TRAIN_LOG=$(cat "$BASE/logs/train.logpath")
sleep 5
head -n 60 "$LOG" || true
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export best_ckpt to ONNX on Ada and download locally",
    )
    parser.add_argument(
        "--onnx-out",
        type=Path,
        default=ROOT / "data" / "detection" / "weights" / "yolox_rtw_nano.onnx",
    )
    args = parser.parse_args()

    if not SECRETS.is_file():
        print("FAIL: missing .cursor/secrets/.ada", flush=True)
        return 2

    print("connecting…", flush=True)
    c = _connect()
    try:
        if args.export:
            host, user = _load_ada()
            base = f"/home/{user}/comstar-yolox-rtw"
            remote_onnx = f"{base}/weights/yolox_rtw_nano.onnx"
            export_sh = f"""#!/usr/bin/env bash
set -euo pipefail
BASE="{base}"
source "$BASE/venv/bin/activate"
cd "$BASE/YOLOX"
export PYTHONPATH="$BASE/YOLOX:${{PYTHONPATH:-}}"
CKPT=""
if [ -f YOLOX_outputs/rtw_yolox_nano/best_ckpt.pth ]; then
  CKPT=YOLOX_outputs/rtw_yolox_nano/best_ckpt.pth
elif [ -f YOLOX_outputs/rtw_yolox_nano/latest_ckpt.pth ]; then
  CKPT=YOLOX_outputs/rtw_yolox_nano/latest_ckpt.pth
fi
test -n "$CKPT" && test -f "$CKPT"
echo USING_CKPT=$CKPT
# Torch 2.x removed torch.onnx._export; Megvii export still calls it.
python - <<'PY'
from pathlib import Path
p = Path("tools/export_onnx.py")
t = p.read_text(encoding="utf-8")
if "torch.onnx._export" in t:
    t = t.replace("torch.onnx._export(", "torch.onnx.export(")
    p.write_text(t, encoding="utf-8")
    print("patched export_onnx.py for torch.onnx.export")
PY
python tools/export_onnx.py -f exps/comstar/rtw_nano.py -c "$CKPT" --output-name "{remote_onnx}" --no-onnxsim
sha256sum "{remote_onnx}"
ls -lh "{remote_onnx}"
"""
            sftp = c.open_sftp()
            try:
                with sftp.file(f"{base}/run_export.sh", "wb") as rf:
                    rf.write(export_sh.encode("utf-8"))
            finally:
                sftp.close()
            print("exporting ONNX on Ada…", flush=True)
            code, out = _run(c, f"bash {base}/run_export.sh", timeout=300)
            print((out[-4000:] if len(out) > 4000 else out).encode("ascii", "replace").decode("ascii"), flush=True)
            if code != 0:
                print(f"FAIL export exit={code}", flush=True)
                return code
            args.onnx_out.parent.mkdir(parents=True, exist_ok=True)
            sftp = c.open_sftp()
            try:
                sftp.get(remote_onnx, str(args.onnx_out))
            finally:
                sftp.close()
            print(f"downloaded {args.onnx_out} ({args.onnx_out.stat().st_size} bytes)", flush=True)
            return 0

        if args.status:
            code, out = _run(
                c,
                "BASE=$HOME/comstar-yolox-rtw; "
                "echo PID=$(cat $BASE/logs/train.pid 2>/dev/null); "
                "LOG=$(cat $BASE/logs/train.logpath 2>/dev/null); echo LOG=$LOG; "
                "if [ -n \"$LOG\" ] && [ -f \"$LOG\" ]; then tail -n 40 \"$LOG\"; fi; "
                "ps -p $(cat $BASE/logs/train.pid 2>/dev/null) -o pid,etime,cmd 2>/dev/null || echo NOT_RUNNING",
            )
            print(out, flush=True)
            return code

        code, out = _run(
            c,
            "hostname; nvidia-smi -L 2>/dev/null | head -3; "
            "python3 -c 'import torch; print(\"torch\", torch.__version__, \"cuda\", torch.cuda.is_available())' 2>&1 | tail -2; "
            "df -h $HOME | tail -1",
        )
        print(out, flush=True)
        if args.probe_only:
            return 0 if code == 0 else code

        host, user = _load_ada()
        base = f"/home/{user}/comstar-yolox-rtw"
        _run(c, f"mkdir -p {base}/logs {base}/weights")

        if not args.skip_upload:
            ann = COCO_LOCAL / "annotations" / "instances_train2017.json"
            if not ann.is_file():
                print("FAIL: local COCO missing", flush=True)
                return 3
            print("uploading COCO + exp…", flush=True)
            blob = _tar_coco()
            sftp = c.open_sftp()
            try:
                with sftp.file(f"{base}/coco.tgz", "wb") as rf:
                    rf.write(blob)
                with sftp.file(f"{base}/rtw_nano.py", "wb") as rf:
                    rf.write(EXP_LOCAL.read_bytes())
                setup = _remote_setup_script(
                    epochs=args.epochs, batch=args.batch, nano_url=NANO_URL
                )
                with sftp.file(f"{base}/run_train.sh", "wb") as rf:
                    rf.write(setup.encode("utf-8"))
            finally:
                sftp.close()
            code, out = _run(
                c,
                f"tar -xzf {base}/coco.tgz -C {base} && "
                f"echo TRAIN=$(ls {base}/coco/train2017 | wc -l) VAL=$(ls {base}/coco/val2017 | wc -l)",
                timeout=180,
            )
            print(out, flush=True)
            if code != 0:
                return code
        else:
            # still refresh setup script / exp
            sftp = c.open_sftp()
            try:
                with sftp.file(f"{base}/rtw_nano.py", "wb") as rf:
                    rf.write(EXP_LOCAL.read_bytes())
                setup = _remote_setup_script(
                    epochs=args.epochs, batch=args.batch, nano_url=NANO_URL
                )
                with sftp.file(f"{base}/run_train.sh", "wb") as rf:
                    rf.write(setup.encode("utf-8"))
            finally:
                sftp.close()

        print("cloning/installing YOLOX + starting train (may take several minutes)…", flush=True)
        code, out = _run(c, f"chmod +x {base}/run_train.sh && bash {base}/run_train.sh", timeout=900)
        print((out[-6000:] if len(out) > 6000 else out).encode("ascii", "replace").decode("ascii"), flush=True)
        if code != 0:
            print(f"FAIL setup/train start exit={code}", flush=True)
            return code
        print("Train started on Ada. Check with: python scripts/detection/train_on_ada.py --status", flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
