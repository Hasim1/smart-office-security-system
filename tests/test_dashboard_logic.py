"""
Dashboard logic tests with a stand-in camera, face library and Arduino.

These confirm that the corrected rule reaches the status labels, the log, the
e-mail trigger and the buzzer command. They do NOT test real cameras, real
face recognition accuracy, a real Arduino or real e-mail delivery.
"""
import csv

import numpy as np
import pytest

pytest.importorskip("PyQt5")
pytest.importorskip("cv2")

from PyQt5.QtWidgets import QApplication

import config
import dashboard

APP = QApplication.instance() or QApplication([])

ALEX = np.random.default_rng(1).normal(0, 0.1, 128)
STRANGER = np.random.default_rng(99).normal(0, 0.1, 128)


class FakeArduino:
    def __init__(self, fail=False):
        self.sent, self.fail, self.closed = [], fail, False

    def write(self, data):
        if self.fail:
            raise OSError("device disconnected")
        self.sent.append(data)

    def close(self):
        self.closed = True


class FakeCapture:
    """Returns `frames` pictures, then stops the thread."""

    def __init__(self, thread, frames, ok=True):
        self.thread, self.left, self.ok = thread, frames, ok

    def read(self):
        self.left -= 1
        if self.left <= 0:
            self.thread._run_flag = False
        return self.ok, (np.zeros((120, 160, 3), dtype=np.uint8) if self.ok else None)

    def release(self):
        pass


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "MASTER_LOG_FILE", str(tmp_path / "activity_log.csv"))
    monkeypatch.setattr(dashboard.SecurityDashboard, "start_cameras", lambda self: None)
    win = dashboard.SecurityDashboard()
    win.arduino = FakeArduino()
    return win


def run_camera(monkeypatch, *, faces, known=(ALEX,), names=("Alex",), frames=5,
               locations=None, fail=False, frame_ok=True):
    """Run the camera loop over fake frames and collect what it reports."""
    monkeypatch.setattr(dashboard, "known_face_encodings", list(known))
    monkeypatch.setattr(dashboard, "known_face_names", list(names))
    monkeypatch.setattr(config, "AUTHORIZED_PEOPLE", None)
    boxes = locations if locations is not None else [(10, 30, 30, 10)] * len(faces)

    def face_locations(image):
        if fail:
            raise RuntimeError("recognition crashed")
        return boxes

    monkeypatch.setattr(dashboard.face_recognition, "face_locations", face_locations)
    monkeypatch.setattr(dashboard.face_recognition, "face_encodings",
                        lambda image, locs=None: list(faces))

    thread = dashboard.VideoThread(0, config.CAMERA_1_NAME)
    monkeypatch.setattr(thread, "_open_with_retry",
                        lambda: FakeCapture(thread, frames, ok=frame_ok))
    monkeypatch.setattr(thread, "msleep", lambda ms: None)
    seen = {"states": [], "alerts": [], "errors": [], "status": []}
    thread.det_state_signal.connect(lambda cam, flag: seen["states"].append(flag))
    thread.detection_signal.connect(lambda cam, ts, status: seen["alerts"].append(status))
    thread.error_signal.connect(lambda cam, ts, status: seen["errors"].append(status))
    thread.status_signal.connect(lambda cam, msg: seen["status"].append(msg))
    thread.run()
    return seen


# ---- camera loop: classification and alert trigger -------------------------
def test_approved_face_raises_no_alert(monkeypatch):
    seen = run_camera(monkeypatch, faces=[ALEX])
    assert seen["states"] == [False] and seen["alerts"] == []


def test_unknown_face_raises_one_alert_despite_many_frames(monkeypatch):
    seen = run_camera(monkeypatch, faces=[STRANGER], frames=8)
    assert seen["states"] == [True]
    assert seen["alerts"] == ["Unauthorized Person Detected"]     # no duplicates


def test_no_reference_photos_treats_face_as_unauthorized(monkeypatch):
    seen = run_camera(monkeypatch, faces=[ALEX], known=(), names=())
    assert seen["states"] == [True] and len(seen["alerts"]) == 1


def test_face_located_but_not_encoded_is_unauthorized(monkeypatch):
    seen = run_camera(monkeypatch, faces=[], locations=[(10, 30, 30, 10)])
    assert seen["states"] == [True]


def test_empty_room_raises_no_alert(monkeypatch):
    seen = run_camera(monkeypatch, faces=[])
    assert seen["states"] == [False] and seen["alerts"] == []


def test_recognition_failure_is_reported_and_never_authorized(monkeypatch):
    seen = run_camera(monkeypatch, faces=[ALEX], fail=True)
    assert seen["errors"] == ["Recognition Error"]                # logged once
    assert False not in seen["states"]                            # never shown as clear
    assert "Recognition error - not verified" in seen["status"]


def test_missing_frames_never_report_authorized(monkeypatch):
    seen = run_camera(monkeypatch, faces=[ALEX], frame_ok=False, frames=5)
    assert seen["states"] == [] and seen["alerts"] == []


def test_restricted_hours_suppress_alert_but_not_status(monkeypatch):
    monkeypatch.setattr(config, "is_alert_time", lambda: False)
    seen = run_camera(monkeypatch, faces=[STRANGER])
    assert seen["states"] == [True] and seen["alerts"] == []


# ---- dashboard: labels, buzzer, log, e-mail --------------------------------
def test_buzzer_and_label_follow_unauthorized_state(window):
    window.update_detection_state(config.CAMERA_1_NAME, True)
    assert window.arduino.sent[-1] == b"1"
    assert "UNAUTHORIZED" in window.cam1_status.text()
    window.update_detection_state(config.CAMERA_1_NAME, False)
    assert window.arduino.sent[-1] == b"0"
    assert "UNAUTHORIZED" not in window.cam1_status.text()


def test_buzzer_stays_on_while_either_camera_has_an_alert(window):
    window.update_detection_state(config.CAMERA_1_NAME, True)
    window.update_detection_state(config.CAMERA_2_NAME, True)
    window.update_detection_state(config.CAMERA_1_NAME, False)
    assert window.arduino.sent[-1] == b"1"
    window.update_detection_state(config.CAMERA_2_NAME, False)
    assert window.arduino.sent[-1] == b"0"


def test_arduino_failure_does_not_crash_the_dashboard(window):
    window.arduino = FakeArduino(fail=True)
    window.update_detection_state(config.CAMERA_1_NAME, True)
    assert window.arduino is None


def test_running_without_arduino_is_safe(window):
    window.arduino = None
    window.update_detection_state(config.CAMERA_1_NAME, True)


def test_unauthorized_event_is_logged_emailed_and_exported(window, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(config, "email_is_configured", lambda: True)
    monkeypatch.setattr(dashboard, "send_alert_email",
                        lambda cam, ts, status: sent.append((cam, status)) or True)
    window.add_detection(config.CAMERA_1_NAME, "10-11-2026 12:00:00",
                         "Unauthorized Person Detected")
    for worker in list(window.email_workers):
        worker.wait(5000)
    APP.processEvents()

    assert sent == [(config.CAMERA_1_NAME, "Unauthorized Person Detected")]
    assert window.alerts_table.rowCount() == 1
    assert window.alerts_table.item(0, 3).text() == "Alert Email Sent"

    with open(config.MASTER_LOG_FILE, encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == config.LOG_COLUMNS
    assert rows[1] == ["10-11-2026 12:00:00", config.CAMERA_1_NAME,
                       "Unauthorized Person Detected", "Alert Email Sent"]

    export = tmp_path / "export.csv"
    window.security_logger.export_rows(rows[1:], str(export))
    with open(export, encoding="utf-8-sig") as handle:
        assert list(csv.reader(handle)) == rows


def test_event_without_email_settings_is_still_logged(window, monkeypatch):
    monkeypatch.setattr(config, "email_is_configured", lambda: False)
    monkeypatch.setattr(dashboard, "send_alert_email", lambda cam, ts, status: False)
    window.add_detection(config.CAMERA_2_NAME, "10-11-2026 12:05:00",
                         "Unauthorized Person Detected")
    for worker in list(window.email_workers):
        worker.wait(5000)
    APP.processEvents()
    assert window.alerts_table.item(0, 3).text() == "Logged (email not configured)"


def test_recognition_error_is_logged_without_email(window, monkeypatch):
    sent = []
    monkeypatch.setattr(dashboard, "send_alert_email", lambda *a: sent.append(a) or True)
    window.log_recognition_error(config.CAMERA_1_NAME, "10-11-2026 12:10:00", "Recognition Error")
    assert sent == [] and window.alerts_table.item(0, 2).text() == "Recognition Error"
    with open(config.MASTER_LOG_FILE, encoding="utf-8-sig") as handle:
        assert "Recognition Error" in handle.read()


def test_closing_switches_buzzer_off(window):
    window.thread1 = window.thread2 = type("T", (), {"stop": lambda self: None})()
    fake = window.arduino
    window.update_detection_state(config.CAMERA_1_NAME, True)
    window.close()
    assert fake.sent[-1] == b"0" and fake.closed
