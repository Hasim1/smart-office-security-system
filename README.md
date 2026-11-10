# Smart Office Security and Reporting System

**Capstone Project II — Computer Engineering, Bahçeşehir University**
Completed and submitted in 2026 by a team of four.

A desktop application that watches two camera feeds and checks every face it
sees against a set of approved reference photos. An approved person is shown as
**AUTHORIZED**. Anyone else is shown as **UNAUTHORIZED**, and the system logs
the event, sends an e-mail alert and switches on an Arduino buzzer.

---

## What the final system does

1. `main.py` runs start-up checks and opens the PyQt5 dashboard.
2. The dashboard starts one background thread per camera. Each thread reads
   frames with OpenCV and runs the `face_recognition` library on them.
3. Every face is passed to the authorization rule in `authorization.py`.
4. The dashboard draws a green box and the person's name for an authorized
   face, and a red box labelled `Unknown - UNAUTHORIZED` for any other face.
5. While an unauthorized face is in view, the dashboard:
   - shows `UNAUTHORIZED DETECTED` under that camera,
   - adds a row to the alerts table and to `reports/activity_log.csv`,
   - sends an e-mail alert on a background thread,
   - sends `1` to the Arduino over USB serial, which switches the buzzer on.
6. When no unauthorized face is in view on either camera, it sends `0` and the
   buzzer stops.

### Authorization rule

| What the camera sees | Result | Alert |
|---|---|---|
| A face that matches an approved reference photo | AUTHORIZED | No |
| A face that matches no reference photo | UNAUTHORIZED | Yes |
| A face, but no reference photos are loaded | UNAUTHORIZED | Yes |
| A face that was located but could not be encoded | UNAUTHORIZED | Yes |
| A recognised person who is not on `AUTHORIZED_PEOPLE` (if that list is set) | UNAUTHORIZED | Yes |
| No face in the frame | No decision | No |
| Face recognition fails with an error | "Recognition error - not verified"; logged | No e-mail or buzzer |
| The camera delivers no picture | Camera shown as reconnecting | No |

Nothing becomes AUTHORIZED by default: a face is authorized only after a clear
match with an approved photo. Errors and missing frames are never reported as
authorized.

Repeated detections are limited by a per-camera cooldown
(`EMAIL_COOLDOWN_SECONDS`, 30 s by default), so a person who stays in view
produces one logged alert and one e-mail per cooldown period, not one per frame.

---

## Development history

This section separates what was tried during development from what the final
code does.

**Raspberry Pi stage.** The team first set the system up on a Raspberry Pi 5.
On that hardware the project ran into power and performance limits that kept
the system from operating as intended.

**Move to a Mac.** Hashim Hamza Al-Hasani proposed running the system on a Mac
instead, using its cameras and processing power. The team adopted this, and the
final dashboard was developed and demonstrated on macOS. The code in this
repository is that Mac-based version: it contains no Raspberry Pi-specific
code, and it has not been verified on a Raspberry Pi in this form.

**YOLOv8.** YOLOv8 person detection (Ultralytics) was used during development
and experimentation. It is kept in `detector.py`, which can be run on its own,
but **the final dashboard does not use it**. The dashboard's live pipeline is
face recognition only.

---

## Project structure

```
smart-office-security-system/
├── main.py                 # launcher: start-up checks, then the dashboard
├── dashboard.py            # PyQt5 UI, camera threads, alerts, Arduino link
├── authorization.py        # the AUTHORIZED / UNAUTHORIZED rule (no GUI or hardware)
├── email_alert.py          # SMTP e-mail alert
├── logger.py               # CSV event log, export, clear
├── config.py               # all settings
├── detector.py             # experimental: YOLOv8 + face recognition (not used by the dashboard)
├── download_model.py       # experimental: downloads yolov8n.pt for detector.py
├── test_cam.py             # early single-camera prototype script
├── requirements.txt
├── requirements-dev.txt    # pytest
├── pytest.ini
├── tests/
│   ├── test_authorization.py     # the rule, tested on its own
│   └── test_dashboard_logic.py   # labels, log, e-mail trigger, buzzer command
├── arduino/buzzer_alarm/buzzer_alarm.ino
├── known_faces/            # reference photos (private, git-ignored)
├── models/                 # yolov8n.pt for detector.py (git-ignored)
├── reports/                # activity_log.csv (git-ignored)
├── assets/icons/
└── screenshots/
```

---

## Hardware

| Component | Purpose | Required |
|---|---|---|
| Computer (developed and demonstrated on macOS) | Runs the application | Yes |
| Two cameras (built-in, USB, or a network stream) | The two monitored feeds | Yes |
| Arduino board + buzzer on pin 11 + USB cable | Audible alarm | Optional |

---

## Installation

Requires Python 3.9–3.12.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`face_recognition` builds **dlib** during installation, which needs CMake and a
C++ compiler (macOS: `brew install cmake`; Debian/Ubuntu:
`sudo apt install cmake build-essential`).

---

## Setup

### 1. Approved people
Put one clear, front-facing photo of each approved person in `known_faces/`.
The file name is the person's name, for example `known_faces/Alex.jpg`.
Photos are private and git-ignored — never commit them.

To approve only some of the people who have a photo, set
`AUTHORIZED_PEOPLE = ["Alex", "Sam"]` in `config.py`. With the default `None`,
everyone with a photo is approved.

### 2. Cameras (`config.py`)
```python
CAMERA_1_SOURCE = 0     # camera index
CAMERA_2_SOURCE = 1     # second camera, or a stream URL such as "rtsp://..."
```

### 3. E-mail alerts (optional)
Keep credentials out of the code. Set them as environment variables:
```bash
export ALERT_EMAIL_SENDER="youraddress@gmail.com"
export ALERT_EMAIL_PASSWORD="your_app_password"     # Gmail App Password
export ALERT_EMAIL_RECIPIENT="admin@office.com"
```
For Gmail, create an App Password (Google Account → App passwords); the normal
account password does not work. Never write a password into a source file. If a
password is ever committed, revoke it.

Without credentials the system still detects and logs; the table shows
*Logged (email not configured)*.

### 4. Arduino buzzer (optional)
1. Upload `arduino/buzzer_alarm/buzzer_alarm.ino` with the Arduino IDE and
   connect a buzzer to pin 11.
2. Set the serial port:
   ```bash
   export ARDUINO_PORT="/dev/cu.usbmodemXXXX"   # Windows: COM3, Linux: /dev/ttyACM0
   ```
If no port is set or the board is not found, the app runs without the buzzer.

### 5. Restricted hours (optional, `config.py`)
```python
ENABLE_TIME_RESTRICTION = False   # True = alert only inside the window below
RESTRICTED_START_HOUR = 19
RESTRICTED_END_HOUR = 7
```

---

## Running

```bash
python main.py
```

Other scripts:
```bash
python email_alert.py     # send one test e-mail
python test_cam.py        # single-camera prototype
python detector.py        # experimental YOLOv8 + face recognition window
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover the software logic:

- `tests/test_authorization.py` — approved faces are authorized; unknown faces,
  missing reference photos, bad encodings and unencoded faces are unauthorized;
  the alert cooldown prevents duplicates.
- `tests/test_dashboard_logic.py` — an unauthorized state reaches the status
  label, the log file, the exported CSV, the e-mail trigger and the buzzer
  command; an authorized face triggers none of them; recognition errors and
  missing frames are never reported as authorized; a lost Arduino connection
  does not crash the app.

The dashboard tests replace the camera, the face-recognition library, the
Arduino and the mail server with stand-ins. **They do not test real hardware.**

Hardware check: the system was run with the cameras and the Arduino buzzer by
the project owner in November 2026 and reported working. That was a manual
check; there are no automated hardware tests and no recorded measurements.

---

## Known limitations

- Detection is face-based. A person whose face is hidden or turned away is not
  detected.
- Recognition accuracy depends on lighting, camera quality and the reference
  photos. No accuracy, frame-rate or latency figures have been measured.
- Hardware behaviour has been checked manually, not by automated tests.
- YOLOv8 (`detector.py`) is not connected to the dashboard.
- The final version was developed on macOS and has not been verified on other
  systems or on a Raspberry Pi.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Camera not available - retrying...` | Wrong camera index, camera in use by another app, or missing permission. On macOS, allow camera access for your terminal or IDE. |
| Everyone is shown as UNAUTHORIZED | No reference photos were loaded. Check `known_faces/` and the start-up messages. |
| `face_recognition` fails to install | Install CMake and a C++ compiler first. |
| No buzzer | `ARDUINO_PORT` is not set or is wrong, or the board is not connected. |
| `Authentication failed` (e-mail) | Use a Gmail App Password. |
| `Numpy is not available` on an Intel Mac | `pip install "numpy<2" "opencv-python<4.12"` (already pinned in `requirements.txt`). |
