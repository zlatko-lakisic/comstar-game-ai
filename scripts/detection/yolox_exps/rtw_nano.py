"""Megvii YOLOX exp for ROME Remastered campaign detection (4 classes).

Use with Megvii YOLOX (Apache-2.0) only — not Ultralytics.
``automate_train.py`` copies this into ``exps/comstar/rtw_nano.py``.

Expects COCO layout from ``auto_label_from_cv.py``::

    $COMSTAR_DETECTION_COCO/
      annotations/instances_train2017.json
      annotations/instances_val2017.json
      train2017/
      val2017/
"""

from __future__ import annotations

import os
from pathlib import Path

from yolox.exp import Exp as MyExp  # type: ignore[import-not-found]


class Exp(MyExp):
    def __init__(self) -> None:
        super().__init__()
        self.num_classes = 4
        self.depth = 0.33
        self.width = 0.25
        # Larger input helps ~28px badges on 1280x720 campaign frames.
        self.input_size = (640, 640)
        self.test_size = (640, 640)
        self.exp_name = "rtw_yolox_nano"
        self.max_epoch = 80
        self.data_num_workers = 4
        self.eval_interval = 5
        # Early-campaign scarcity: less mosaic/mixup so tiny badges survive.
        self.mosaic_prob = 0.4
        self.mixup_prob = 0.0
        self.enable_mixup = False
        self.hsv_prob = 0.8
        self.flip_prob = 0.5
        self.degrees = 5.0
        self.translate = 0.1
        self.shear = 1.0
        self.warmup_epochs = 3
        root = Path(os.environ.get("COMSTAR_DETECTION_COCO", "data/detection/coco"))
        self.data_dir = str(root.resolve())
        self.train_ann = "instances_train2017.json"
        self.val_ann = "instances_val2017.json"
        # Stock YOLOX COCODataset uses name train2017 / val2017 for image folders.
        self.class_names = (
            "settlement_badge",
            "settlement_oval",
            "army_stack",
            "ship",
        )
