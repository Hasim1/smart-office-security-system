"""
logger.py
=========
Persistent activity logging and report export for the Smart Office Security
System.

Responsibilities:
  * Create the reports/ folder if it does not exist.
  * Keep a permanent, Excel-readable master log (reports/activity_log.csv).
  * Append each finalized security event (timestamp, camera, status, action).
  * Export the current set of events to a user-chosen CSV file.
  * Clear (truncate) the master log when the user clears the logs.

The CSV is written with a UTF-8 BOM ("utf-8-sig") so it opens cleanly in
Microsoft Excel with correct accented characters.

Thread-safety: appends are guarded by a lock because the GUI may finalize
e-mail results from short-lived worker threads.
"""

import os
import csv
import threading

import config


class SecurityLogger:
    def __init__(self, reports_dir=None, master_log_file=None, columns=None):
        self.reports_dir = reports_dir or config.REPORTS_DIR
        self.master_log_file = master_log_file or config.MASTER_LOG_FILE
        self.columns = columns or config.LOG_COLUMNS
        self._lock = threading.Lock()
        self._ensure_storage()

    # ------------------------------------------------------------------ #
    # Storage setup
    # ------------------------------------------------------------------ #
    def _ensure_storage(self):
        """Create the reports folder and a header-only master log if missing."""
        os.makedirs(self.reports_dir, exist_ok=True)
        if not os.path.exists(self.master_log_file):
            with self._lock:
                with open(self.master_log_file, "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(self.columns)

    # ------------------------------------------------------------------ #
    # Writing events
    # ------------------------------------------------------------------ #
    def log_event(self, timestamp, camera_id, status, action):
        """Append one finalized event row to the permanent master log."""
        row = [timestamp, camera_id, status, action]
        try:
            with self._lock:
                with open(self.master_log_file, "a", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(row)
            return True
        except Exception as exc:
            print(f"[LOGGER] Could not write to master log: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Exporting / reading / clearing
    # ------------------------------------------------------------------ #
    def export_rows(self, rows, path):
        """
        Write the given rows (list of lists) plus the column header to `path`.
        Used by the dashboard's "Export Report" button to save exactly what is
        shown in the on-screen table. Returns True on success.
        """
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self.columns)
                writer.writerows(rows)
            return True
        except Exception as exc:
            print(f"[LOGGER] Export failed: {exc}")
            raise

    def read_all(self):
        """Return all logged rows (excluding the header) from the master log."""
        if not os.path.exists(self.master_log_file):
            return []
        try:
            with self._lock:
                with open(self.master_log_file, "r", newline="", encoding="utf-8-sig") as f:
                    reader = list(csv.reader(f))
            return reader[1:] if len(reader) > 1 else []
        except Exception as exc:
            print(f"[LOGGER] Could not read master log: {exc}")
            return []

    def clear(self):
        """Truncate the master log back to a header-only file."""
        try:
            with self._lock:
                with open(self.master_log_file, "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(self.columns)
            return True
        except Exception as exc:
            print(f"[LOGGER] Could not clear master log: {exc}")
            return False

    def default_export_path(self, timestamp_str):
        """Build a timestamped default export filename inside the reports folder."""
        safe = timestamp_str.replace(":", "-").replace(" ", "_").replace("/", "-")
        return os.path.join(self.reports_dir, f"Security_Report_{safe}.csv")
