#!/usr/bin/env bash
# Export YOLOX checkpoint → ONNX (Megvii tools). Run inside YOLOX checkout.
# Usage:
#   bash export_yolox_onnx.sh /path/to/best_ckpt.pth /path/to/out.onnx
set -euo pipefail

CKPT="${1:?ckpt path}"
OUT="${2:?output onnx path}"
YOLOX_ROOT="${YOLOX_ROOT:-$PWD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP="${COMSTAR_YOLOX_EXP:-$SCRIPT_DIR/yolox_exps/rtw_nano.py}"

cd "$YOLOX_ROOT"
python tools/export_onnx.py \
  -f "$EXP" \
  -c "$CKPT" \
  --output-name "$OUT" \
  --decode_in_inference false

sha256sum "$OUT" | tee "${OUT}.sha256"
echo "Record sha256 in overlay detect_rtw_campaign.yaml via publish_rtw_weights.py"
