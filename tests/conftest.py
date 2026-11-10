"""
Test setup.

The dashboard tests run without a camera, an Arduino or the face_recognition
library: those are replaced by small stand-ins here. This checks the software
logic only - it is not a hardware test.
"""
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stand-in for the face_recognition library (needs dlib, not installed in CI).
if "face_recognition" not in sys.modules:
    fake_face = types.ModuleType("face_recognition")
    fake_face.load_image_file = lambda path: None
    fake_face.face_encodings = lambda image, locations=None: []
    fake_face.face_locations = lambda image: []
    sys.modules["face_recognition"] = fake_face

# Stand-in for pyserial.
if "serial" not in sys.modules:
    fake_serial = types.ModuleType("serial")

    class _NoSerial:
        def __init__(self, *args, **kwargs):
            raise OSError("no serial port in tests")

    fake_serial.Serial = _NoSerial
    sys.modules["serial"] = fake_serial
