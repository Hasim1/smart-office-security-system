"""
download_model.py
=================
Helper that downloads the YOLOv8-nano model and places it in models/yolov8n.pt.

Run this ONCE (with an internet connection) before the demo, or just run the
app normally - the model also auto-downloads on first use. This helper simply
guarantees the file is in the expected models/ folder ahead of time.

Run with:   python download_model.py
"""

import os
import shutil

import config


def main():
    os.makedirs(os.path.dirname(config.MODEL_PATH) or ".", exist_ok=True)

    if os.path.exists(config.MODEL_PATH):
        print(f"[OK] Model already present: {config.MODEL_PATH}")
        return

    try:
        from ultralytics import YOLO
    except Exception as exc:
        print(f"[ERROR] ultralytics not installed ({exc}).")
        print("Run:  pip install -r requirements.txt")
        return

    print("Downloading yolov8n.pt (first time only)...")
    # YOLO("yolov8n.pt") downloads the weights to the current directory if absent.
    YOLO("yolov8n.pt")

    # Move/copy the downloaded file into the models/ folder if needed.
    if os.path.exists("yolov8n.pt") and not os.path.exists(config.MODEL_PATH):
        shutil.move("yolov8n.pt", config.MODEL_PATH)

    if os.path.exists(config.MODEL_PATH):
        print(f"[OK] Model ready: {config.MODEL_PATH}")
    else:
        print("[WARN] Download finished but the model was not found in models/. "
              "The app will still auto-download on first run.")


if __name__ == "__main__":
    main()
