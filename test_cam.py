import face_recognition
import cv2
import numpy as np
import os
import smtplib
from email.mime.text import MIMEText
import time
import serial  

print("جاري إعداد النظام وقراءة البيانات...")

# ==========================================
# 1. إعداد الاتصال بالأردوينو
# ==========================================
arduino_port = os.environ.get("ARDUINO_PORT", "")  # e.g. /dev/cu.usbmodemXXXX, COM3, /dev/ttyACM0

try:
    arduino = serial.Serial(arduino_port, 9600, timeout=1)
    time.sleep(2) 
    print("✅ تم الاتصال بالأردوينو بنجاح!")
except Exception as e:
    print("⚠️ تحذير: لم يتم العثور على الأردوينو. تأكد من توصيل الكابل واسم المنفذ.")
    arduino = None

# ==========================================
# 2. إعدادات الإيميل
# ==========================================
SENDER_EMAIL = os.environ.get("ALERT_EMAIL_SENDER", "")
APP_PASSWORD = os.environ.get("ALERT_EMAIL_PASSWORD", "")   # Gmail App Password - never hard-code it
RECEIVER_EMAIL = os.environ.get("ALERT_EMAIL_RECIPIENT", "")
def send_security_alert(person_name):
    try:
        email_body = f"Security Alert from Smart Office System:\nAn unauthorized access attempt was detected: {person_name}\nTime: {time.ctime()}"
        msg = MIMEText(email_body)
        msg['Subject'] = '🚨 Security Alert - Unauthorized Access Detected'
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        print(f"✅ تم إرسال إيميل التحذير بنجاح")
    except Exception as e:
        print(f"❌ فشل إرسال الإيميل: {e}")

# ==========================================
# 3. Reference faces (approved people) - one photo per person in known_faces/
# ==========================================
from authorization import evaluate_frame, load_known_faces

known_face_encodings, known_face_names, face_warnings = load_known_faces("known_faces", face_recognition)
for warning in face_warnings:
    print(f"[FACES] {warning}")
print(f"[FACES] Loaded {len(known_face_names)} approved face(s). "
      "Any other face is treated as UNAUTHORIZED.")

# ==========================================
# 4. تشغيل الكاميرا والمراقبة
# ==========================================
cap = cv2.VideoCapture(0)
last_email_time = 0
EMAIL_COOLDOWN = 60

print("الكاميرا تعمل الآن! النظام الأمني جاهز.")

while True:
    ret, frame = cap.read()
    if not ret: break

    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    current_time = time.time()
    unauthorized_detected = False 

    # Approved face -> AUTHORIZED (green). Any other face -> UNAUTHORIZED (red, alert).
    decision = evaluate_frame(face_encodings, known_face_encodings, known_face_names,
                              located_face_count=len(face_locations))
    unauthorized_detected = decision.unauthorized_present

    if unauthorized_detected and (current_time - last_email_time) > EMAIL_COOLDOWN:
        print("Unauthorized person detected - sending e-mail alert...")
        send_security_alert("an unrecognised person")
        last_email_time = current_time

    for (top, right, bottom, left), face in zip(face_locations, decision.faces):
        name = face.label
        color = (0, 255, 0) if face.is_authorized else (0, 0, 255)

        top *= 4
        right *= 4
        bottom *= 4
        left *= 4
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # إرسال إشارة الأردوينو لتشغيل الإنذار
    if arduino is not None:
        if unauthorized_detected:
            arduino.write(b'1') 
        else:
            arduino.write(b'0') 

    cv2.imshow('Smart Office Security System', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

if arduino is not None:
    arduino.write(b'0')
    arduino.close()

cap.release()
cv2.destroyAllWindows()