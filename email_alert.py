"""
email_alert.py
==============
SMTP e-mail alert module for the Smart Office Security System.

Sends a security alert e-mail when an unauthorized person is detected. Called
from a background thread (see dashboard.py) so the GUI never freezes during the
network call. All settings come from config.py.

The alert e-mail contains the timestamp, camera ID and detection status, as
required by the project specification.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config


def send_alert_email(camera_id, timestamp, status="Unauthorized Person Detected"):
    """
    Send one security-alert e-mail.

    Args:
        camera_id (str): e.g. "Camera 1"
        timestamp (str): human-readable detection time
        status (str):    detection status text included in the e-mail body

    Returns:
        bool: True if the e-mail was sent successfully, False otherwise.
    """
    if not config.email_is_configured():
        print("[EMAIL] Not configured. Set ALERT_EMAIL_SENDER / "
              "ALERT_EMAIL_PASSWORD / ALERT_EMAIL_RECIPIENT (or edit config.py).")
        return False

    subject = f"SECURITY ALERT - {camera_id}"
    body = (
        "A security event was detected by the Smart Office Security System.\n\n"
        f"  Detection Status : {status}\n"
        f"  Camera ID        : {camera_id}\n"
        f"  Timestamp        : {timestamp}\n\n"
        "Please review the live dashboard and take appropriate action.\n\n"
        "-- Smart Office Security and Reporting System"
    )

    message = MIMEMultipart()
    message["From"] = config.EMAIL_SENDER
    message["To"] = config.EMAIL_RECIPIENT
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.send_message(message)
        print(f"[EMAIL] Alert sent -> {camera_id} @ {timestamp}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[EMAIL] Authentication failed. For Gmail use a 16-character "
              "App Password, not your normal account password.")
        return False
    except Exception as exc:
        print(f"[EMAIL] Failed to send alert: {exc}")
        return False


# Quick standalone test:  python email_alert.py
if __name__ == "__main__":
    from datetime import datetime
    if not config.email_is_configured():
        print("E-mail is not configured. Edit config.py or set the environment "
              "variables, then run this test again.")
        raise SystemExit(1)
    ts = datetime.now().strftime(config.TIMESTAMP_FORMAT)
    ok = send_alert_email("Camera 1", ts, "Unauthorized Person Detected")
    print("Test result:", "SENT" if ok else "NOT SENT")
