"""
authorization.py
================
Authorization decisions for the Smart Office Security System.

This module contains the security rule and nothing else: it does not import
PyQt5, OpenCV, the camera, the Arduino or the face_recognition library, so it
can be tested on its own (see tests/test_authorization.py).

The rule
--------
  * A face that matches an approved reference photo  -> AUTHORIZED
  * Any other face                                   -> UNAUTHORIZED

"Any other face" deliberately includes every doubtful case, so that nothing can
become AUTHORIZED by accident:
  * the face matches no reference photo (a stranger),
  * no reference photos are loaded at all,
  * the face was located but could not be encoded,
  * the encoding is missing or malformed,
  * the matched name is not in the approved list (when a list is configured).
"""

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np

AUTHORIZED = "AUTHORIZED"
UNAUTHORIZED = "UNAUTHORIZED"
UNKNOWN_NAME = "Unknown"

# Maximum face distance that still counts as the same person. 0.6 is the
# default used by the face_recognition library; lower is stricter.
DEFAULT_TOLERANCE = 0.6

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


@dataclass(frozen=True)
class FaceDecision:
    """The decision for one face."""
    name: str
    status: str

    @property
    def is_authorized(self) -> bool:
        return self.status == AUTHORIZED

    @property
    def label(self) -> str:
        return f"{self.name} - {self.status}"


@dataclass(frozen=True)
class FrameDecision:
    """The decision for one camera frame (zero or more faces)."""
    faces: List[FaceDecision] = field(default_factory=list)

    @property
    def unauthorized_present(self) -> bool:
        return any(not face.is_authorized for face in self.faces)

    @property
    def unauthorized_count(self) -> int:
        return sum(1 for face in self.faces if not face.is_authorized)


def _unknown() -> FaceDecision:
    return FaceDecision(UNKNOWN_NAME, UNAUTHORIZED)


def classify_face(face_encoding,
                  known_encodings: Sequence,
                  known_names: Sequence[str],
                  tolerance: float = DEFAULT_TOLERANCE,
                  approved_names: Optional[Sequence[str]] = None) -> FaceDecision:
    """
    Decide whether one face is authorized.

    Args:
        face_encoding:   128-number encoding of the face seen by the camera.
        known_encodings: encodings of the reference photos.
        known_names:     the name that belongs to each reference encoding.
        tolerance:       maximum distance that counts as a match.
        approved_names:  optional list of names allowed in. None means every
                         person with a reference photo is approved.

    Returns AUTHORIZED only for a clear match with an approved person. Every
    error or doubtful input returns "Unknown - UNAUTHORIZED".
    """
    try:
        if face_encoding is None:
            return _unknown()
        if known_encodings is None or len(known_encodings) == 0:
            return _unknown()
        if len(known_encodings) != len(known_names):
            return _unknown()

        probe = np.asarray(face_encoding, dtype=float)
        known = np.asarray(known_encodings, dtype=float)
        if probe.ndim != 1 or known.ndim != 2 or known.shape[1] != probe.shape[0]:
            return _unknown()
        if not np.all(np.isfinite(probe)):
            return _unknown()

        distances = np.linalg.norm(known - probe, axis=1)
        best = int(np.argmin(distances))
        if not np.isfinite(distances[best]) or distances[best] > tolerance:
            return _unknown()

        name = str(known_names[best])
        if approved_names is not None and name not in approved_names:
            # Recognised, but not on the approved list.
            return FaceDecision(name, UNAUTHORIZED)
        return FaceDecision(name, AUTHORIZED)
    except Exception:
        # Never let a failure here turn into an AUTHORIZED result.
        return _unknown()


def evaluate_frame(face_encodings: Sequence,
                   known_encodings: Sequence,
                   known_names: Sequence[str],
                   tolerance: float = DEFAULT_TOLERANCE,
                   approved_names: Optional[Sequence[str]] = None,
                   located_face_count: Optional[int] = None) -> FrameDecision:
    """
    Decide for every face in a frame.

    located_face_count is the number of faces the detector located. If fewer
    encodings than located faces are supplied (encoding failed for some), the
    missing ones are counted as unknown and therefore UNAUTHORIZED.
    """
    encodings = list(face_encodings) if face_encodings is not None else []
    faces = [classify_face(enc, known_encodings, known_names, tolerance, approved_names)
             for enc in encodings]
    if located_face_count is not None and located_face_count > len(faces):
        faces.extend(_unknown() for _ in range(located_face_count - len(faces)))
    return FrameDecision(faces)


def load_known_faces(folder: str, face_lib):
    """
    Load one reference encoding per image file in `folder`.

    The file name (without extension) is used as the person's name, so no names
    are stored in the source code. `face_lib` is the face_recognition module,
    passed in so this function can be tested without it.

    Returns (encodings, names, warnings). A missing folder, an unreadable image
    or an image with no clear face is skipped with a warning; it never raises.
    """
    encodings, names, warnings = [], [], []
    if not folder or not os.path.isdir(folder):
        warnings.append(f"Reference photo folder not found: {folder}")
        return encodings, names, warnings

    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue
        name = os.path.splitext(filename)[0]
        path = os.path.join(folder, filename)
        try:
            image = face_lib.load_image_file(path)
            found = face_lib.face_encodings(image)
        except Exception as exc:
            warnings.append(f"Could not read {filename}: {exc}")
            continue
        if not found:
            warnings.append(f"No clear face found in {filename}")
            continue
        encodings.append(found[0])
        names.append(name)
    return encodings, names, warnings


class AlertThrottle:
    """
    Limits how often one camera raises an alert, so a person who stays in view
    produces one alert per cooldown period instead of one per frame.
    """

    def __init__(self, cooldown_seconds: float, clock=time.time):
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._last_alert = None

    def should_alert(self) -> bool:
        now = self._clock()
        if self._last_alert is None or now - self._last_alert >= self.cooldown_seconds:
            self._last_alert = now
            return True
        return False
