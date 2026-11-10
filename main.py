"""
main.py
=======
Application launcher for the Smart Office Security and Reporting System.

This is the recommended entry point. It performs a few safety checks and then
opens the desktop dashboard:

  1. Ensures the reports/ folder exists.
  2. Reports how many approved reference photos are in known_faces/.
  3. Reports whether e-mail alerts are configured.
  4. Launches the PyQt5 dashboard.

Run with:   python main.py
"""

import os
import sys
import platform

import config


def check_cameras_and_permissions():
    """
    Briefly open each webcam-index camera from the MAIN thread and report
    availability.

    This matters on macOS: the camera-permission dialog can only be shown from
    the main thread. The dashboard opens cameras inside worker threads, where
    macOS silently refuses unauthorized access - the feeds would sit at
    "retrying..." forever with no prompt. Opening the cameras here first makes
    the permission dialog appear on the very first run.
    """
    try:
        import cv2
    except Exception:
        return   # dependency problems are reported later with a clear message

    for source in (config.CAMERA_1_SOURCE, config.CAMERA_2_SOURCE):
        # Only integer indexes are local hardware needing an OS permission.
        if not (isinstance(source, int)
                or (isinstance(source, str) and source.isdigit())):
            print(f" [..] Camera source {source!r:20}: network/file source - "
                  "checked when the dashboard opens it")
            continue
        idx = int(source)
        if platform.system() == "Darwin":
            cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        else:
            cap = cv2.VideoCapture(idx)
        available = cap.isOpened()
        cap.release()
        if available:
            print(f" [OK] Camera index {idx}       : available")
        else:
            print(f" [..] Camera index {idx}       : not available yet. "
                  "If macOS asks for camera permission, click Allow and "
                  "restart. The dashboard will keep retrying meanwhile.")


def preflight_checks():
    """Create folders and print a short readiness report to the console."""
    print("=" * 60)
    print(" Smart Office Security and Reporting System")
    print("=" * 60)

    # 1) Folders
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    print(f" [OK] Reports folder      : {config.REPORTS_DIR}/")

    # 2) Approved reference photos
    faces_dir = config.KNOWN_FACES_DIR
    photos = [f for f in os.listdir(faces_dir)
              if f.lower().endswith((".jpg", ".jpeg", ".png"))] if os.path.isdir(faces_dir) else []
    if photos:
        print(f" [OK] Approved face photos: {len(photos)} in {faces_dir}/")
    else:
        print(f" [!!] Approved face photos: none found in {faces_dir}/ - "
              "every face will be treated as UNAUTHORIZED.")

    # 3) E-mail
    if config.email_is_configured():
        print(f" [OK] E-mail alerts       : configured ({config.EMAIL_SENDER})")
    else:
        print(" [..] E-mail alerts       : NOT configured - detections will still "
              "be logged. Edit config.py or set the ALERT_EMAIL_* variables.")

    # 4) Cameras: availability check + macOS permission prompt (main thread).
    print(f" [..] Camera 1 source     : {config.CAMERA_1_SOURCE}")
    print(f" [..] Camera 2 source     : {config.CAMERA_2_SOURCE}")
    check_cameras_and_permissions()
    print("=" * 60)


def main():
    preflight_checks()

    # Import PyQt5 only after the checks so a missing-dependency message is clear.
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception as exc:
        print(f"\n[ERROR] PyQt5 is not installed ({exc}).")
        print("Run:  pip install -r requirements.txt")
        sys.exit(1)

    from dashboard import SecurityDashboard

    app = QApplication(sys.argv)
    window = SecurityDashboard()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
