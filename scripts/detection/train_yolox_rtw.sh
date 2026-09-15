#!/usr/bin/env bash
# Train Megvii YOLOX-nano on RTW COCO (run inside a YOLOX checkout on CUDA).
# Usage:
#   export COMSTAR_DETECTION_COCO=/path/to/data/detection/coco
#   bash /path/to/comstar/scripts/detection/train_yolox_rtw.sh
set -euo pipefail

YOLOX_ROOT="${YOLOX_ROOT:-$PWD}"
EXP="${COMSTAR_YOLOX_EXP:-}"
if [[ -z "$EXP" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  EXP="$SCRIPT_DIR/yolox_exps/rtw_nano.py"
fi

cd "$YOLOX_ROOT"
echo "YOLOX_ROOT=$YOLOX_ROOT"
echo "EXP=$EXP"
echo "COMSTAR_DETECTION_COCO=${COMSTAR_DETECTION_COCO:-unset}"

python tools/train.py \
  -f "$EXP" \
  -d "${COMSTAR_YOLOX_GPUS:-1}" \
  -b "${COMSTAR_YOLOX_BATCH:-16}" \
  --fp16 \
  -c "${COMSTAR_YOLOX_PRETRAIN:-}" \
  "$@"
