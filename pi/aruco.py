# pi/aruco.py — ArUco marker detection and pose estimation
#
# Outputs (x, z, theta) for a given target marker ID.
#
#   x     : lateral offset in metres   (+ = marker is to the right of centre)
#   z     : forward distance in metres (always positive)
#   theta : heading error in degrees   (+ = vehicle is angled right of marker face)
#
# Usage:
#   detector = ArucoDetector()
#   pose = detector.detect(target_id=1)
#   if pose:
#       x, z, theta = pose
#   detector.stop()

import cv2
import cv2.aruco as aruco
import numpy as np
import time
from picamera2 import Picamera2


# ---------------------------------------------------------------------------
# Camera calibration — from piArucoDetectionV2.py (720x480)
# NOTE: marker_size_m in piArucoDetectionV2.py reads 0.0145 — likely a typo.
#       Spec and piArucoUART.py both say 0.145 m (14.5 cm). Verify against
#       your printed marker and update MARKER_SIZE_M if needed.
# ---------------------------------------------------------------------------

CAMERA_MATRIX = np.array([
    [545.21395204,   0.0,          366.92229201],
    [  0.0,        545.49357025,   233.73940389],
    [  0.0,          0.0,            1.0       ],
], dtype=np.float32)

DIST_COEFFS = np.array(
    [-0.06449152, 0.12849967, 0.00193863, 0.00422528, -0.05891855],
    dtype=np.float32
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MARKER_SIZE_M    = 0.096    # physical side length of printed marker (metres)
THETA_JUMP_LIMIT = 45.0     # degrees — frame rejected if theta jumps more than this


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_angle(angle_deg: float) -> float:
    """Wrap angle to (−180, +180]."""
    angle_deg = angle_deg % 360.0
    if angle_deg >= 180.0:
        angle_deg -= 360.0
    return angle_deg


def _build_obj_points(size_m: float) -> np.ndarray:
    """3D corner coordinates of a flat square marker centred at origin."""
    half = size_m / 2.0
    return np.array([
        [-half,  half, 0],
        [ half,  half, 0],
        [ half, -half, 0],
        [-half, -half, 0],
    ], dtype=np.float32)


# ---------------------------------------------------------------------------
# ArucoDetector
# ---------------------------------------------------------------------------

class ArucoDetector:

    def __init__(self):
        self._obj_points = _build_obj_points(MARKER_SIZE_M)
        self._prev_theta = None     # last accepted theta, for jump detection

        self._init_camera()
        self._init_detector()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_camera(self):
        self._cam = Picamera2()
        cfg = self._cam.create_preview_configuration(
            main={"size": (720, 480), "format": "RGB888"}
        )
        self._cam.configure(cfg)
        self._cam.set_controls({
            "Sharpness": 1.5,
            "AwbEnable": True,
            "Contrast":  1.2,
        })
        self._cam.start()
        time.sleep(2.0)     # allow AE/AWB to settle
        print("[ARUCO] Camera ready")

    def _init_detector(self):
        aruco_dict     = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
        params         = aruco.DetectorParameters()
        self._detector = aruco.ArucoDetector(aruco_dict, params)
        print("[ARUCO] Detector ready")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, target_id: int):
        """
        Capture one frame and estimate pose for target_id.

        Returns (x, z, theta) if the marker is found and passes sanity check.
        Returns None if the marker is absent, occluded, or the theta jump
        exceeds THETA_JUMP_LIMIT.

        x     — lateral offset, metres  (positive = marker is right of centre)
        z     — forward distance, metres (always positive)
        theta — heading error, degrees   (positive = vehicle faces right of marker)
        """
        frame = self._cam.capture_array()
        if frame is None or frame.size == 0:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)

        if ids is None:
            return None

        ids_flat = ids.flatten()
        matches  = [i for i, mid in enumerate(ids_flat) if mid == target_id]
        if not matches:
            return None

        pose = self._estimate_pose(corners[matches[0]])
        if pose is None:
            return None

        x, z, theta = pose

        # Reject implausible theta jump
        if self._prev_theta is not None:
            jump = abs(_normalize_angle(theta - self._prev_theta))
            if jump > THETA_JUMP_LIMIT:
                print(f"[ARUCO] Theta jump rejected: {jump:.1f}° "
                      f"(prev={self._prev_theta:.1f}°  raw={theta:.1f}°)")
                return None

        self._prev_theta = theta
        return x, z, theta

    def detect_any(self) -> list:
        """
        Return all visible marker IDs regardless of value.
        Used by the SEARCHING state to infer direction toward the target wall.
        Returns an empty list if nothing is detected.
        """
        frame = self._cam.capture_array()
        if frame is None or frame.size == 0:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        _, ids, _ = self._detector.detectMarkers(gray)

        if ids is None:
            return []
        return ids.flatten().tolist()

    def reset(self):
        """Clear theta history. Call when switching to a different target ID."""
        self._prev_theta = None
        print("[ARUCO] History reset")

    def stop(self):
        """Release the camera."""
        self._cam.stop()
        print("[ARUCO] Camera stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _estimate_pose(self, corners):
        """
        Run solvePnP on one marker's corner array.
        Returns (x, z, theta) on success, None on failure.
        """
        ret, rvec, tvec = cv2.solvePnP(
            self._obj_points, corners,
            CAMERA_MATRIX, DIST_COEFFS,
            flags=cv2.SOLVEPNP_ITERATIVE
        )
        if not ret:
            return None

        x = float(tvec[0][0])
        z = float(tvec[2][0])

        # Extract pitch (heading error) from rotation matrix
        rot, _ = cv2.Rodrigues(rvec)
        sy     = np.sqrt(rot[0, 0] ** 2 + rot[1, 0] ** 2)
        pitch  = np.arctan2(-rot[2, 0], sy)
        theta  = _normalize_angle(np.degrees(pitch))

        return x, z, theta
