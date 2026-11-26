#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Make the ONNX YOLO11n the all-apps page's Object detection fetches.

    python3 export_yolo11n_onnx.py --out yolo11n_coco_320.onnx

Run it in a virtual environment with Ultralytics (``pip install ultralytics
onnx onnxslim``; the CPU build of PyTorch is enough). It downloads
Ultralytics' ``yolo11n.pt`` (COCO, the 80 classes), exports it to ONNX at a
320 x 320 input, opset 17, simplified, and prints its size and SHA-256.
``scripts/build_wasm_allapps.py`` writes the hosted file's into the page's
note (``DETECT_BYTES`` and ``DETECT_SHA256``): two exports give the same
size but not the same bytes, so a new export means new values there. The
weights are Ultralytics', under AGPL-3.0.
"""

import argparse
import hashlib
import shutil
from pathlib import Path

INPUT = 320
OPSET = 17


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="where to write the .onnx file")
    ap.add_argument("--weights", default="yolo11n.pt", help="Ultralytics weights to export (default: %(default)s)")
    args = ap.parse_args()

    from ultralytics import YOLO

    made = Path(YOLO(args.weights).export(format="onnx", imgsz=INPUT, opset=OPSET, simplify=True, dynamic=False))
    shutil.copyfile(made, args.out)
    data = args.out.read_bytes()
    print("%s: %d bytes, sha256 %s" % (args.out, len(data), hashlib.sha256(data).hexdigest()))


if __name__ == "__main__":
    main()
