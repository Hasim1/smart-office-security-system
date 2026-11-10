"""
detector.py (Updated with Facial Recognition)
YOLOv8 person-detection + Face Recognition for the Smart Office Security System.
"""
import os
import time
import shutil
import threading
import cv2
import face_recognition

try:
    from ultralytics import YOLO
    ULTRALYTICS_IMPORT_ERROR = None
except Exception as exc: 
    YOLO = None
    ULTRALYTICS_IMPORT_ERROR = exc

PERSON_CLASS_ID = 0
_MODEL_LOAD_LOCK = threading.Lock()

def resolve_model_path(model_path):
    if model_path and os.path.exists(model_path):
        return model_path
    base = os.path.basename(model_path) if model_path else "yolov8n.pt"
    return base or "yolov8n.pt"

class PersonDetector:
    def __init__(self, model_path="models/yolov8n.pt", conf_threshold=0.50, image_size=416):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.image_size = image_size
        self.prev_time = time.time()
        self.model = None
        self.model_loaded = False
        self.load_error = None
        
        
        self.known_face_encodings = []
        self.known_face_names = []
        self.load_known_faces()

        self.load_model()

    def load_known_faces(self):
        faces_dir = "known_faces"
        if not os.path.exists(faces_dir):
            os.makedirs(faces_dir)
            print("[FACE REC] Folder 'known_faces' created. Add photos there.")
            return
            
        for filename in os.listdir(faces_dir):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                filepath = os.path.join(faces_dir, filename)
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    self.known_face_encodings.append(encodings[0])
                    self.known_face_names.append(os.path.splitext(filename)[0])
        print(f"[FACE REC] Loaded {len(self.known_face_names)} known faces.")

    def load_model(self):
        if YOLO is None:
            self.load_error = (
                "The 'ultralytics' package is not installed "
                f"({ULTRALYTICS_IMPORT_ERROR}). Run: pip install -r requirements.txt"
            )
            print(f"[DETECTOR] {self.load_error}")
            return
            
        resolved = resolve_model_path(self.model_path)
        try:
            with _MODEL_LOAD_LOCK:
                self.model = YOLO(resolved)
                
                if (resolved != self.model_path and self.model_path
                    and os.path.exists(resolved)
                    and not os.path.exists(self.model_path)):
                    try:
                        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
                        shutil.move(resolved, self.model_path)
                        print(f"[DETECTOR] Saved downloaded weights to {self.model_path}")
                    except Exception as move_exc: 
                        print(f"[DETECTOR] Could not move weights into {self.model_path}: {move_exc}")
                        
            self.model_loaded = True
            print(f"[DETECTOR] Model loaded: {resolved}")
            
        except Exception as exc:
            self.load_error = f"Could not load YOLO model '{resolved}': {exc}"
            self.model_loaded = False
            print(f"[DETECTOR] {self.load_error}")

    def process_frame(self, frame):
        now = time.time()
        elapsed = now - self.prev_time
        fps = (1.0 / elapsed) if elapsed > 0 else 0.0
        self.prev_time = now
        
        detection_data = {
            "person_detected": False,
            "person_count": 0,
            "boxes": [],
            "fps": fps,
            "error": None,
        }
        
        if not self.model_loaded or self.model is None:
            detection_data["error"] = "Model not loaded"
            self._draw_status(frame, fps, "MODEL NOT LOADED", color=(0, 0, 255))
            return frame, detection_data
            
        try:
            results = self.model.predict(
                source=frame,
                conf=self.conf_threshold,
                classes=[PERSON_CLASS_ID], 
                imgsz=self.image_size,
                verbose=False,
            )
            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    confidence = float(box.conf[0])
                    detection_data["person_detected"] = True
                    detection_data["person_count"] += 1
                    detection_data["boxes"].append({
                        "x": int(x1), "y": int(y1),
                        "w": int(x2 - x1), "h": int(y2 - y1),
                        "confidence": confidence,
                    })
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Person {confidence:.2f}"
                    cv2.putText(frame, label, (x1, max(y1 - 10, 20)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                                
        except Exception as exc:
            detection_data["error"] = str(exc)
            print(f"[DETECTOR] Detection failed: {exc}")
            self._draw_status(frame, fps, "DETECTION ERROR", color=(0, 0, 255))
            return frame, detection_data

        
        if detection_data["person_detected"]:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            
            is_unknown = False
            detected_names = []
            
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.5)
                name = "Unknown"
                
                if True in matches:
                    first_match_index = matches.index(True)
                    name = self.known_face_names[first_match_index]
                else:
                    is_unknown = True
                    
                detected_names.append(name)
                
               
                box_color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
                cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, box_color, 2)

            if face_locations:
                if not is_unknown:
                   
                    detection_data["person_detected"] = False 
                    status = f"AUTHORIZED: {', '.join(detected_names)}"
                    color = (0, 255, 0)
                else:
                   
                    status = "UNAUTHORIZED PERSON"
                    color = (0, 0, 255)
            else:
               
                status = "PERSON (NO FACE VISIBLE)"
                color = (0, 165, 255)
                
            self._draw_status(frame, fps, status, color=color)
            return frame, detection_data
            
        else:
            status = "NO PERSON"
            color = (0, 255, 255)
            self._draw_status(frame, fps, status, color=color)
            return frame, detection_data

    @staticmethod
    def _draw_status(frame, fps, status, color=(0, 255, 255)):
        cv2.putText(frame, f"Detect FPS: {fps:.1f} | {status}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

if __name__ == "__main__":
    import config
    det = PersonDetector(config.MODEL_PATH, config.CONF_THRESHOLD, config.IMAGE_SIZE)
    if not det.model_loaded:
        print("Model failed to load:", det.load_error)
        raise SystemExit(1)
        
    cap = cv2.VideoCapture(0)
    print("Press 'q' to quit.")
    while True:
        ok, frm = cap.read()
        if not ok:
            print("No camera frame.")
            break
            
        frm = cv2.resize(frm, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
        out, data = det.process_frame(frm)
        cv2.imshow("PersonDetector test", out)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()