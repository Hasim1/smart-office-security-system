"""Tests for the authorization rule (no GUI, camera or hardware needed)."""
import numpy as np
import pytest

from authorization import (AUTHORIZED, UNAUTHORIZED, UNKNOWN_NAME, AlertThrottle,
                           classify_face, evaluate_frame, load_known_faces)


def encoding(seed):
    """A repeatable 128-number face encoding."""
    return np.random.default_rng(seed).normal(0, 0.1, 128)


ALEX, SAM, STRANGER = encoding(1), encoding(2), encoding(99)
KNOWN = [ALEX, SAM]
NAMES = ["Alex", "Sam"]


# ---- known and approved faces -> AUTHORIZED --------------------------------
def test_known_face_is_authorized():
    decision = classify_face(ALEX, KNOWN, NAMES)
    assert (decision.name, decision.status) == ("Alex", AUTHORIZED)
    assert decision.is_authorized


def test_known_face_with_small_variation_is_authorized():
    slightly_different = ALEX + 0.01
    assert classify_face(slightly_different, KNOWN, NAMES).name == "Alex"


def test_best_match_is_chosen_not_first_match():
    decision = classify_face(SAM, KNOWN, NAMES, tolerance=10.0)
    assert decision.name == "Sam"


# ---- unknown faces -> UNAUTHORIZED -----------------------------------------
def test_unknown_face_is_unauthorized():
    decision = classify_face(STRANGER, KNOWN, NAMES)
    assert (decision.name, decision.status) == (UNKNOWN_NAME, UNAUTHORIZED)
    assert not decision.is_authorized


def test_face_just_outside_tolerance_is_unauthorized():
    far = ALEX.copy()
    far[0] += 0.61
    assert not classify_face(far, KNOWN, NAMES, tolerance=0.6).is_authorized


def test_no_reference_photos_means_everyone_is_unauthorized():
    assert not classify_face(ALEX, [], []).is_authorized


# ---- approved list ---------------------------------------------------------
def test_recognised_person_not_on_approved_list_is_unauthorized():
    decision = classify_face(SAM, KNOWN, NAMES, approved_names=["Alex"])
    assert (decision.name, decision.status) == ("Sam", UNAUTHORIZED)


def test_person_on_approved_list_is_authorized():
    assert classify_face(ALEX, KNOWN, NAMES, approved_names=["Alex"]).is_authorized


# ---- failures can never produce AUTHORIZED ---------------------------------
@pytest.mark.parametrize("bad_encoding", [
    None,
    [],
    np.zeros(64),                 # wrong length
    np.full(128, np.nan),         # not a number
    "not an encoding",
    np.zeros((2, 128)),           # wrong shape
])
def test_bad_encoding_is_unauthorized(bad_encoding):
    decision = classify_face(bad_encoding, KNOWN, NAMES)
    assert decision.status == UNAUTHORIZED


def test_mismatched_reference_data_is_unauthorized():
    assert not classify_face(ALEX, KNOWN, ["Alex"]).is_authorized      # 2 encodings, 1 name
    assert not classify_face(ALEX, None, NAMES).is_authorized


# ---- whole frame -----------------------------------------------------------
def test_empty_frame_has_no_alert():
    frame = evaluate_frame([], KNOWN, NAMES)
    assert frame.faces == [] and not frame.unauthorized_present


def test_frame_with_only_approved_faces_has_no_alert():
    frame = evaluate_frame([ALEX, SAM], KNOWN, NAMES)
    assert not frame.unauthorized_present


def test_one_stranger_among_approved_faces_raises_alert():
    frame = evaluate_frame([ALEX, STRANGER], KNOWN, NAMES)
    assert frame.unauthorized_present and frame.unauthorized_count == 1


def test_located_face_without_encoding_is_unauthorized():
    # The detector located 2 faces but only 1 could be encoded.
    frame = evaluate_frame([ALEX], KNOWN, NAMES, located_face_count=2)
    assert len(frame.faces) == 2 and frame.unauthorized_present


def test_none_encodings_with_located_face_is_unauthorized():
    frame = evaluate_frame(None, KNOWN, NAMES, located_face_count=1)
    assert frame.unauthorized_present


# ---- loading reference photos ----------------------------------------------
class FakeFaceLib:
    def __init__(self, results):
        self.results = results

    def load_image_file(self, path):
        if "broken" in path:
            raise OSError("cannot read file")
        return path

    def face_encodings(self, image):
        for key, value in self.results.items():
            if key in image:
                return value
        return []


def test_load_known_faces_uses_file_names(tmp_path):
    for name in ("Alex.jpg", "Sam.PNG", "noface.jpg", "broken.jpg", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    lib = FakeFaceLib({"Alex": [ALEX], "Sam": [SAM], "noface": []})
    encodings, names, warnings = load_known_faces(str(tmp_path), lib)
    assert names == ["Alex", "Sam"] and len(encodings) == 2
    assert len(warnings) == 2          # the photo with no face and the broken file


def test_load_known_faces_missing_folder_does_not_crash(tmp_path):
    encodings, names, warnings = load_known_faces(str(tmp_path / "missing"), FakeFaceLib({}))
    assert encodings == [] and names == [] and warnings


# ---- repeated detections ---------------------------------------------------
def test_throttle_allows_one_alert_per_cooldown():
    now = [1000.0]
    throttle = AlertThrottle(30, clock=lambda: now[0])
    assert throttle.should_alert()            # first sighting alerts
    now[0] += 5
    assert not throttle.should_alert()        # still in view: no duplicate
    now[0] += 24.9
    assert not throttle.should_alert()
    now[0] += 0.2
    assert throttle.should_alert()            # cooldown passed
