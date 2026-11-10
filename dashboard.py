"""
dashboard.py
============
Smart Office Security and Reporting System
- Two camera feeds
- Face recognition against the reference photos in known_faces/
- Authorization rule in authorization.py: approved face = AUTHORIZED,
  any other face = UNAUTHORIZED (alert: log + e-mail + Arduino buzzer)
- Arduino buzzer over USB serial
"""

import os
import sys
import time
import platform
import threading
from datetime import datetime

import cv2
import face_recognition 
import serial           
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTableWidget, QPushButton, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QStatusBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QIcon

import config
from authorization import (AlertThrottle, FrameDecision, evaluate_frame,
                           load_known_faces)
from email_alert import send_alert_email
from logger import SecurityLogger

EVENT_ID_ROLE = Qt.UserRole + 1
DISPLAY_W, DISPLAY_H = 460, 345

# ==========================================================================
# 1. Reference faces (approved people)
# ==========================================================================
# One photo per approved person in known_faces/; the file name is the person's
# name. Photos are private and are not part of the repository.
known_face_encodings, known_face_names, _face_warnings = load_known_faces(
    config.KNOWN_FACES_DIR, face_recognition)
for _warning in _face_warnings:
    print(f"[FACES] {_warning}")
print(f"[FACES] Loaded {len(known_face_names)} approved face(s).")
if not known_face_names:
    print("[FACES] No approved faces loaded - every face will be treated as "
          "UNAUTHORIZED.")

# إنشاء قفل الذاكرة (Mutex) لمنع انهيار البرنامج
ai_lock = threading.Lock() 

# ==========================================================================
# E-mail worker
# ==========================================================================
class EmailAlertWorker(QThread):
    result_signal = pyqtSignal(str, str, str, int, bool)

    def __init__(self, camera_id, timestamp, status, event_id):
        super().__init__()
        self.camera_id = camera_id
        self.timestamp = timestamp
        self.status = status
        self.event_id = event_id

    def run(self):
        success = send_alert_email(self.camera_id, self.timestamp, self.status)
        self.result_signal.emit(
            self.camera_id, self.timestamp, self.status, self.event_id, success)

# ==========================================================================
# Video capture + Face Recognition worker
# ==========================================================================
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    detection_signal = pyqtSignal(str, str, str)   
    status_signal = pyqtSignal(str, str)           
    det_state_signal = pyqtSignal(str, bool)       # camera, unauthorized person in view
    error_signal = pyqtSignal(str, str, str)       # camera, timestamp, status

    def __init__(self, source, camera_id):
        super().__init__()
        self.source = source
        self.camera_id = camera_id
        self._run_flag = True
        self.frame_count = 0
        self.alert_throttle = AlertThrottle(config.EMAIL_COOLDOWN_SECONDS)
        self.error_throttle = AlertThrottle(config.EMAIL_COOLDOWN_SECONDS)
        self.last_state_emitted = None
        self.recognition_failed = False

    def _emit_state(self, unauthorized_present):
        """Tell the dashboard when this camera's alert state changes."""
        if unauthorized_present != self.last_state_emitted:
            self.det_state_signal.emit(self.camera_id, unauthorized_present)
            self.last_state_emitted = unauthorized_present

    def _open_capture(self):
        source = self.source
        if isinstance(source, str) and not source.isdigit():
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                                     cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
        idx = int(source)
        if platform.system() == "Darwin":
            return cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(idx)

    def _open_with_retry(self):
        announced = False
        while self._run_flag:
            cap = self._open_capture()
            if cap is not None and cap.isOpened():
                self.status_signal.emit(self.camera_id, "Live")
                return cap
            if cap is not None:
                cap.release()
            if not announced:
                self.status_signal.emit(self.camera_id, "Camera not available - retrying...")
                announced = True
            for _ in range(30):
                if not self._run_flag:
                    return None
                self.msleep(100)
        return None

    def run(self):
        self.status_signal.emit(self.camera_id, "Loading Face Recognition...")
        
        cap = self._open_with_retry()
        if cap is None:
            return

        read_failures = 0
        while self._run_flag:
            ret, frame = cap.read()
            if not ret:
                read_failures += 1
                if read_failures >= 30:
                    # No picture: clear this camera's alarm (nothing can be
                    # seen) and show the camera as offline - never as cleared.
                    self._emit_state(False)
                    self.status_signal.emit(self.camera_id, "Reconnecting...")
                    cap.release()
                    cap = self._open_with_retry()
                    if cap is None:
                        return
                    read_failures = 0
                self.msleep(30)
                continue
            read_failures = 0

            self.frame_count += 1

            # تصغير الصورة لتسريع المعالجة
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

            face_locations = []
            face_encodings = []
            recognition_error = None

            # The lock stops the two camera threads running recognition at the
            # same time.
            try:
                with ai_lock:
                    face_locations = face_recognition.face_locations(rgb_small_frame)
                    if face_locations:
                        face_encodings = face_recognition.face_encodings(
                            rgb_small_frame, face_locations)
            except Exception as exc:
                recognition_error = exc

            if recognition_error is not None:
                # Recognition failed for this frame: nobody can be confirmed,
                # so nothing is shown as authorized. Report it and move on.
                if not self.recognition_failed:
                    print(f"[{self.camera_id}] Face recognition failed: {recognition_error}")
                    self.recognition_failed = True
                    self.status_signal.emit(self.camera_id, "Recognition error - not verified")
                if self.error_throttle.should_alert():
                    timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
                    self.error_signal.emit(self.camera_id, timestamp, "Recognition Error")
                decision = FrameDecision([])
            else:
                if self.recognition_failed:
                    self.recognition_failed = False
                    self.last_state_emitted = None   # force a status refresh
                # Approved face -> AUTHORIZED; any other face -> UNAUTHORIZED.
                decision = evaluate_frame(
                    face_encodings, known_face_encodings, known_face_names,
                    tolerance=config.FACE_MATCH_TOLERANCE,
                    approved_names=config.AUTHORIZED_PEOPLE,
                    located_face_count=len(face_locations))

            for (top, right, bottom, left), face in zip(face_locations, decision.faces):
                color = (0, 255, 0) if face.is_authorized else (0, 0, 255)
                top *= 4; right *= 4; bottom *= 4; left *= 4
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.putText(frame, face.label, (left, max(top - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            if recognition_error is None:
                self._emit_state(decision.unauthorized_present)

            if decision.unauthorized_present and config.is_alert_time():
                if self.alert_throttle.should_alert():
                    timestamp = datetime.now().strftime(config.TIMESTAMP_FORMAT)
                    self.detection_signal.emit(
                        self.camera_id, timestamp, "Unauthorized Person Detected")

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt_image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            scaled = qt_image.scaled(DISPLAY_W, DISPLAY_H, Qt.KeepAspectRatio)
            self.change_pixmap_signal.emit(scaled.copy())

            self.msleep(10)

        if cap is not None:
            cap.release()

    def stop(self):
        self._run_flag = False
        if not self.wait(8000):
            self.terminate()
            self.wait(2000)

# ==========================================================================
# Main window
# ==========================================================================
class SecurityDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Office Security & Reporting System")
        self.setGeometry(100, 100, 1040, 800)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        self._set_window_icon()

        self.security_logger = SecurityLogger()
        self.email_workers = []
        self._next_event_id = 1

        self.cam1_alert = False
        self.cam2_alert = False
        self.arduino = None
        self._connect_arduino()

        self._build_ui()
        self.start_cameras()

    def _connect_arduino(self):
        # تأكد من هذا المسار أنه مطابق لمنفذ الأردوينو لديك
        arduino_port = config.ARDUINO_PORT
        if not arduino_port:
            print("[ARDUINO] No port configured (ARDUINO_PORT). Buzzer disabled.")
            return
        try:
            self.arduino = serial.Serial(arduino_port, config.ARDUINO_BAUD_RATE, timeout=1)
            time.sleep(2)
            print("✅ تم الاتصال بالأردوينو بنجاح لتشغيل الإنذار!")
        except Exception as e:
            print("⚠️ تحذير: لم يتم العثور على الأردوينو. لن يعمل الإنذار الصوتي.")
            self.arduino = None

    def _set_window_icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "icons", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _build_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        title = QLabel("Smart Office Security Dashboard")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; "
                            "color: #3498db; padding: 10px;")
        main_layout.addWidget(title)

        cameras_layout = QHBoxLayout()
        self.cam1_label, self.cam1_status = self._make_camera_panel(config.CAMERA_1_NAME)
        self.cam2_label, self.cam2_status = self._make_camera_panel(config.CAMERA_2_NAME)
        cameras_layout.addLayout(self._wrap_camera(self.cam1_label, self.cam1_status))
        cameras_layout.addLayout(self._wrap_camera(self.cam2_label, self.cam2_status))
        main_layout.addLayout(cameras_layout)

        logs_label = QLabel("Security Alerts & Activity Logs")
        logs_label.setStyleSheet("font-size: 20px; font-weight: bold; "
                                 "padding-top: 12px; color: #ecf0f1;")
        main_layout.addWidget(logs_label)

        self.alerts_table = QTableWidget(0, len(config.LOG_COLUMNS))
        self.alerts_table.setHorizontalHeaderLabels(config.LOG_COLUMNS)
        self.alerts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.alerts_table.setStyleSheet("""
            QTableWidget { background-color: #2c3e50; color: white;
                           font-size: 14px; border-radius: 5px; border: none;
                           gridline-color: #34495e; }
            QHeaderView::section { background-color: #34495e; color: white;
                           font-weight: bold; padding: 6px;
                           border: 1px solid #1e1e1e; }
        """)
        self.alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        main_layout.addWidget(self.alerts_table)

        buttons_layout = QHBoxLayout()
        export_btn = QPushButton("Export Report (CSV/Excel)")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setStyleSheet("background-color: #27ae60; color: white; "
                                 "font-size: 16px; font-weight: bold; "
                                 "padding: 10px; border-radius: 5px;")
        export_btn.clicked.connect(self.export_report)

        clear_btn = QPushButton("Clear Logs")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("background-color: #c0392b; color: white; "
                                "font-size: 16px; font-weight: bold; "
                                "padding: 10px; border-radius: 5px;")
        clear_btn.clicked.connect(self.clear_logs)

        buttons_layout.addWidget(export_btn)
        buttons_layout.addWidget(clear_btn)
        main_layout.addLayout(buttons_layout)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.setStatusBar(QStatusBar())
        email_state = "configured" if config.email_is_configured() else "NOT configured"
        self.statusBar().setStyleSheet("color: #bdc3c7;")
        self.statusBar().showMessage(f"System starting... | E-mail alerts: {email_state}")

    def _make_camera_panel(self, name):
        feed = QLabel(f"{name}\n(Starting camera...)")
        feed.setAlignment(Qt.AlignCenter)
        feed.setStyleSheet("background-color: #000000; color: #7f8c8d; "
                           "font-size: 18px; border: 2px solid #e74c3c; "
                           "border-radius: 10px;")
        feed.setMinimumSize(DISPLAY_W, DISPLAY_H)

        status = QLabel(f"{name}: starting...")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet("font-size: 14px; font-weight: bold; "
                             "color: #f39c12; padding: 4px;")
        return feed, status

    @staticmethod
    def _wrap_camera(feed, status):
        col = QVBoxLayout()
        col.addWidget(feed)
        col.addWidget(status)
        return col

    def start_cameras(self):
        self.thread1 = VideoThread(config.CAMERA_1_SOURCE, config.CAMERA_1_NAME)
        self.thread1.change_pixmap_signal.connect(self.update_cam1)
        self.thread1.detection_signal.connect(self.add_detection)
        self.thread1.status_signal.connect(self.show_camera_status)
        self.thread1.det_state_signal.connect(self.update_detection_state)
        self.thread1.error_signal.connect(self.log_recognition_error)
        self.thread1.start()

        self.thread2 = VideoThread(config.CAMERA_2_SOURCE, config.CAMERA_2_NAME)
        self.thread2.change_pixmap_signal.connect(self.update_cam2)
        self.thread2.detection_signal.connect(self.add_detection)
        self.thread2.status_signal.connect(self.show_camera_status)
        self.thread2.det_state_signal.connect(self.update_detection_state)
        self.thread2.error_signal.connect(self.log_recognition_error)
        self.thread2.start()

        self.statusBar().showMessage(
            "System running | Monitoring 2 cameras | "
            f"E-mail alerts: {'configured' if config.email_is_configured() else 'NOT configured'}"
        )

    def update_cam1(self, img):
        self.cam1_label.setPixmap(QPixmap.fromImage(img))

    def update_cam2(self, img):
        self.cam2_label.setPixmap(QPixmap.fromImage(img))

    def _status_label_for(self, camera_id):
        return self.cam1_status if camera_id == config.CAMERA_1_NAME else self.cam2_status

    def show_camera_status(self, camera_id, message):
        label = self._status_label_for(camera_id)
        if message == "Live":
            label.setText(f"{camera_id}: ● Live - Monitoring")
            label.setStyleSheet("font-size: 14px; font-weight: bold; "
                                "color: #2ecc71; padding: 4px;")
        else:
            if "not available" in message or "failed" in message.lower():
                feed = self.cam1_label if camera_id == config.CAMERA_1_NAME else self.cam2_label
                feed.setText(f"{camera_id}\n{message}")
            label.setText(f"{camera_id}: {message}")
            label.setStyleSheet("font-size: 14px; font-weight: bold; "
                                "color: #f39c12; padding: 4px;")

    def update_detection_state(self, camera_id, person_present):
        label = self._status_label_for(camera_id)
        
        if person_present:
            label.setText(f"{camera_id}: ⚠ UNAUTHORIZED DETECTED")
            label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e74c3c; padding: 4px;")
        else:
            label.setText(f"{camera_id}: ● Live - Monitoring")
            label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2ecc71; padding: 4px;")

        if camera_id == config.CAMERA_1_NAME:
            self.cam1_alert = person_present
        else:
            self.cam2_alert = person_present

        self._set_buzzer(self.cam1_alert or self.cam2_alert)

    def _set_buzzer(self, on):
        """Switch the Arduino buzzer. A serial failure must not crash the app."""
        if self.arduino is None:
            return
        try:
            self.arduino.write(b'1' if on else b'0')
        except Exception as exc:
            print(f"[ARDUINO] Lost connection to the buzzer: {exc}")
            self.arduino = None

    def log_recognition_error(self, camera_id, timestamp, status):
        """Record a recognition failure. It is logged, not e-mailed."""
        row = self.alerts_table.rowCount()
        self.alerts_table.insertRow(row)
        self.alerts_table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.alerts_table.setItem(row, 1, QTableWidgetItem(camera_id))
        self.alerts_table.setItem(row, 2, QTableWidgetItem(status))
        self.alerts_table.setItem(row, 3, QTableWidgetItem("Logged (not verified)"))
        self.alerts_table.scrollToBottom()
        self.security_logger.log_event(timestamp, camera_id, status, "Logged (not verified)")

    def add_detection(self, camera_id, timestamp, status):
        event_id = self._next_event_id
        self._next_event_id += 1

        row = self.alerts_table.rowCount()
        self.alerts_table.insertRow(row)

        ts_item = QTableWidgetItem(timestamp)
        ts_item.setData(EVENT_ID_ROLE, event_id)
        self.alerts_table.setItem(row, 0, ts_item)
        self.alerts_table.setItem(row, 1, QTableWidgetItem(camera_id))
        self.alerts_table.setItem(row, 2, QTableWidgetItem(status))

        initial_action = "Sending email..." if config.email_is_configured() else "Logging..."
        self.alerts_table.setItem(row, 3, QTableWidgetItem(initial_action))
        self.alerts_table.scrollToBottom()

        worker = EmailAlertWorker(camera_id, timestamp, status, event_id)
        worker.result_signal.connect(self.update_email_status)
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self.email_workers.append(worker)
        worker.start()

    def _find_row_by_event_id(self, event_id):
        for row in range(self.alerts_table.rowCount()):
            item = self.alerts_table.item(row, 0)
            if item is not None and item.data(EVENT_ID_ROLE) == event_id:
                return row
        return -1

    def update_email_status(self, camera_id, timestamp, status, event_id, success):
        if not config.email_is_configured():
            action = "Logged (email not configured)"
        elif success:
            action = "Alert Email Sent"
        else:
            action = "Email Failed"

        row = self._find_row_by_event_id(event_id)
        if row != -1:
            self.alerts_table.setItem(row, 3, QTableWidgetItem(action))

        self.security_logger.log_event(timestamp, camera_id, status, action)

    def _cleanup_worker(self, worker):
        if worker in self.email_workers:
            self.email_workers.remove(worker)

    def clear_logs(self):
        reply = QMessageBox.question(
            self, "Confirm Clear",
            "Clear all security logs?\n\nThis empties the on-screen table AND the "
            "permanent log file (reports/activity_log.csv).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.alerts_table.setRowCount(0)
            self.security_logger.clear()
            self.statusBar().showMessage("Logs cleared.", 4000)

    def export_report(self):
        if self.alerts_table.rowCount() == 0:
            QMessageBox.information(self, "Nothing to export",
                                    "There are no log entries to export yet.")
            return

        default_name = self.security_logger.default_export_path(
            datetime.now().strftime(config.TIMESTAMP_FORMAT))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", default_name, "CSV Files (*.csv)")
        if not path:
            return

        rows = []
        for row in range(self.alerts_table.rowCount()):
            rows.append([
                self.alerts_table.item(row, col).text()
                if self.alerts_table.item(row, col) else ""
                for col in range(self.alerts_table.columnCount())
            ])
        try:
            self.security_logger.export_rows(rows, path)
            QMessageBox.information(self, "Success",
                                    f"Report exported successfully:\n{path}")
            self.statusBar().showMessage(f"Report exported: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"Could not export report:\n{exc}")

    def closeEvent(self, event):
        self.thread1.stop()
        self.thread2.stop()
        self._set_buzzer(False)
        if self.arduino is not None:
            try:
                self.arduino.close()
            except Exception:
                pass
        
        for worker in list(self.email_workers):
            if worker.isRunning():
                worker.wait(3000)
        QApplication.processEvents()
        self.email_workers.clear()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SecurityDashboard()
    window.show()
    sys.exit(app.exec_())