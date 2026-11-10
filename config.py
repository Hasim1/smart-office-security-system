"""
config.py
=========
Central configuration for the Smart Office Security and Reporting System.

EDIT THIS FILE ONLY. You should never need to change the other code files to
configure the system. Every value a student/operator needs to change lives here
and is clearly marked with  <-- CHANGE THIS  where a real value is required.

There are two ways to set the e-mail credentials:

  Option A (recommended, more secure):
      Set environment variables before running. Nothing secret is stored in code.

          export ALERT_EMAIL_SENDER="youraddress@gmail.com"
          export ALERT_EMAIL_PASSWORD="your_app_password"        # Gmail App Password
          export ALERT_EMAIL_RECIPIENT="admin@office.com"
          export ALERT_SMTP_SERVER="smtp.gmail.com"              # optional
          export ALERT_SMTP_PORT="587"                           # optional

      On Windows PowerShell use:  $env:ALERT_EMAIL_SENDER="..."

  Option B (simplest, for a quick demo):
      Just replace the placeholder strings in the EMAIL section below.
      If an environment variable is set it always wins over the value here.
"""

import os
from datetime import datetime

# Absolute path of the project folder (where this config.py lives). All data
# paths below are anchored here, so logs/model land in the SAME place no
# matter which directory the app is launched from (Terminal, IDE, etc.).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _int_env(name, default):
    """Read an integer environment variable, tolerating empty/invalid values."""
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return int(raw)
    if raw:
        print(f"[CONFIG] Ignoring invalid {name}={raw!r}; using {default}.")
    return default


# ==========================================================================
# 1. CAMERA SETTINGS
# ==========================================================================
# A camera "source" can be:
#   - an integer webcam index:        0, 1, 2 ...
#   - an IP / RTSP camera URL string: "rtsp://user:pass@192.168.1.50:554/stream1"
#   - an HTTP MJPEG URL string:       "http://192.168.1.50:8080/video"
#   - a video file path string:       "samples/test_clip.mp4"   (useful for demos)
#
# Use integers for built-in / USB webcams, or a URL string for IP cameras.
CAMERA_1_SOURCE = 0          # <-- CHANGE THIS (e.g. 0 for laptop webcam, or an RTSP URL)
CAMERA_2_SOURCE = 1          # <-- CHANGE THIS (e.g. 1 for a second USB cam, or an RTSP URL)

# Friendly names shown on the dashboard and in the logs / e-mails.
CAMERA_1_NAME = "Camera 1"
CAMERA_2_NAME = "Camera 2"

# Frame resize (downscale) applied to every captured frame BEFORE detection.
# Smaller = faster and lighter on the CPU / Raspberry Pi. 640x480 is a good default.
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ==========================================================================
# 2. DETECTION / YOLO MODEL SETTINGS
# ==========================================================================
# Path to the YOLO model file. The default ships in the models/ folder.
# If the file is missing, the system will auto-download yolov8n.pt on first run
# (an internet connection is required for that first download only).
MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8n.pt")   # <-- CHANGE THIS only if you use a different model

# Minimum confidence (0.0 - 1.0) for a detection to count as a "person".
# Raise it to reduce false positives, lower it to catch more.
CONF_THRESHOLD = 0.50

# Inference image size passed to YOLO. Smaller = faster, larger = more accurate.
# 416 is a good speed/accuracy balance for live video. 320 is faster on a Pi.
IMAGE_SIZE = 416

# Run YOLO on only every Nth captured frame to lower CPU load.
#   1 = run on every frame (heaviest / smoothest detection)
#   2 = run on every 2nd frame, etc. Raise this on the Raspberry Pi if FPS is low.
DETECT_EVERY_N_FRAMES = 2

# ==========================================================================
# 2b. FACE RECOGNITION / AUTHORIZATION SETTINGS
# ==========================================================================
# Folder with one reference photo per approved person. The file name (without
# extension) is the person's name, e.g. known_faces/Alex.jpg. Photos are
# private: the folder is git-ignored and must never be committed.
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")

# Who is allowed in.
#   None             -> everyone who has a reference photo is AUTHORIZED.
#   ["Alex", "Sam"]  -> only these names are AUTHORIZED; anyone else who is
#                       recognised is shown by name but treated as UNAUTHORIZED.
# A face that matches no reference photo is always UNAUTHORIZED.
AUTHORIZED_PEOPLE = None

# Maximum face distance that counts as a match (0.6 is the face_recognition
# library default). Lower = stricter, fewer false matches.
FACE_MATCH_TOLERANCE = 0.6

# ==========================================================================
# 2c. ARDUINO BUZZER SETTINGS (optional)
# ==========================================================================
# Serial port of the Arduino that drives the buzzer. Leave empty to run
# without a buzzer. Examples:
#   macOS   "/dev/cu.usbmodemXXXX"
#   Windows "COM3"
#   Linux   "/dev/ttyACM0"
ARDUINO_PORT = os.environ.get("ARDUINO_PORT", "")
ARDUINO_BAUD_RATE = 9600

# ==========================================================================
# 3. E-MAIL ALERT SETTINGS
# ==========================================================================
# Placeholders are used if you do NOT set environment variables.
# Replace the three placeholder strings for the simplest setup (Option B above).
EMAIL_SENDER = os.environ.get("ALERT_EMAIL_SENDER", "youraddress@gmail.com")          # <-- CHANGE THIS
EMAIL_PASSWORD = os.environ.get("ALERT_EMAIL_PASSWORD", "your_16_char_app_password")  # <-- CHANGE THIS (Gmail App Password)
EMAIL_RECIPIENT = os.environ.get("ALERT_EMAIL_RECIPIENT", "youraddress@gmail.com")         # <-- CHANGE THIS

# SMTP server / port. Gmail defaults shown. (Outlook: smtp.office365.com / 587)
SMTP_SERVER = os.environ.get("ALERT_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = _int_env("ALERT_SMTP_PORT", 587)

# Minimum seconds between two e-mail alerts FROM THE SAME camera.
# Prevents one person standing in view from triggering dozens of e-mails.
# Lower this (e.g. 10) for a quick demo; raise it (e.g. 60) for real use.
EMAIL_COOLDOWN_SECONDS = 30

# These sentinel strings are the default placeholders above. They are used to
# detect "not yet configured" so the system does not try to log in with fake
# credentials. Do not change them; just change EMAIL_SENDER / EMAIL_PASSWORD.
_PLACEHOLDER_SENDER = "youraddress@gmail.com"
_PLACEHOLDER_PASSWORD = "your_16_char_app_password"
_PLACEHOLDER_RECIPIENT = "admin@office.com"


def email_is_configured():
    """Return True only when real e-mail credentials have been supplied."""
    if not (EMAIL_SENDER and EMAIL_PASSWORD and EMAIL_RECIPIENT):
        return False
    if EMAIL_SENDER == _PLACEHOLDER_SENDER:
        return False
    if EMAIL_PASSWORD == _PLACEHOLDER_PASSWORD:
        return False
    if EMAIL_RECIPIENT == _PLACEHOLDER_RECIPIENT:
        return False
    return True


# ==========================================================================
# 4. LOGGING / REPORTING SETTINGS
# ==========================================================================
# Folder where the persistent activity log and exported reports are written.
# Created automatically at startup if it does not exist.
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Persistent master log file (the permanent audit trail). Always Excel-readable.
MASTER_LOG_FILE = os.path.join(REPORTS_DIR, "activity_log.csv")

# Columns used everywhere (dashboard table, master log, exported reports).
LOG_COLUMNS = ["Timestamp", "Camera ID", "Detection Status", "Action Taken"]

# Human-readable timestamp format used in the logs and e-mails.
TIMESTAMP_FORMAT = "%d-%m-%Y %H:%M:%S"

# ==========================================================================
# 5. RESTRICTED-TIME MONITORING (optional)
# ==========================================================================
# The project monitors for unauthorized people "during restricted times".
# When ENABLE_TIME_RESTRICTION is False the system alerts 24/7 (best for a demo,
# so a detection always fires). Set it True to only alert inside a time window,
# e.g. after office hours.
ENABLE_TIME_RESTRICTION = False

# 24-hour clock. Example below = restricted from 19:00 (7 PM) to 07:00 (7 AM).
# The window may wrap past midnight (start hour > end hour is allowed).
RESTRICTED_START_HOUR = 19
RESTRICTED_END_HOUR = 7


def is_alert_time():
    """
    Return True if alerts are allowed to fire right now.

    Always True when ENABLE_TIME_RESTRICTION is False. Otherwise True only when
    the current hour is inside the [RESTRICTED_START_HOUR, RESTRICTED_END_HOUR)
    window (the window may wrap past midnight).
    """
    if not ENABLE_TIME_RESTRICTION:
        return True
    hour = datetime.now().hour
    start, end = RESTRICTED_START_HOUR, RESTRICTED_END_HOUR
    if start <= end:
        return start <= hour < end
    # Window wraps past midnight, e.g. 19:00 -> 07:00
    return hour >= start or hour < end
