# pi/parking_planner.py — Tick-compatible parking planner.
#
# Encapsulates the algorithm from prior/park_controller.py so it works
# inside the FSM tick loop instead of as a standalone script.
#
# Internal states:
#   STREAMING   — streaming approach toward marker
#   EVALUATING  — stable pose acquired, deciding to park or maneuver
#   DONE        — parking complete
#
# Return values from tick():
#   ('stream', x, z, speed)   — call uart.send_stream() this frame
#   ('move',   x, z, speed)   — call uart.send_move() (final park nudge) → ARRIVED
#   ('reset',)                — reverse maneuver done, re-approach (stay APPROACHING)
#   ('lost',)                 — marker lost + recovery attempted → SEARCHING
#   ('done',)                 — already parked (repeated call guard)

import time

# ---------------------------------------------------------------------------
# Tuning constants  (match prior/park_controller.py)
# ---------------------------------------------------------------------------

EVAL_DISTANCE_M     = 0.25    # evaluate alignment when closer than this (m)
MAX_X_ERROR_M       = 0.05    # lateral tolerance (5 cm)
MAX_THETA_ERROR     = 7.0     # angular tolerance (degrees)

REVERSE_DISTANCE_M  = -0.15   # step 1 curved reverse distance
STRAIGHT_REVERSE_M  = -0.15   # step 2 straight reverse distance
REVERSE_KP          = 0.003   # proportional steering gain during reverse
MAX_REVERSE_X       = 0.08    # clamp on reverse steering (safety)
REVERSE_SPEED       = 0.50    # speed for all reverse maneuvers

RECOVERY_DISTANCE_M = -0.10   # straight back-up when marker lost
CAMERA_OFFSET_M     = 0.20    # camera-to-bumper offset for final nudge

MAX_SPEED           = 0.50    # approach speed when far
MIN_SPEED           = 0.35    # approach speed when close / final nudge
RAMP_START_M        = 1.0     # distance at which speed starts ramping down

STABLE_SAMPLES      = 5       # frames averaged for stable pose
RECOVERY_MISS_LIMIT = 5       # consecutive missed frames before recovery triggers

# ---------------------------------------------------------------------------
# Internal state labels
# ---------------------------------------------------------------------------

_STREAMING  = "STREAMING"
_EVALUATING = "EVALUATING"
_DONE       = "DONE"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stable_pose(detector, target_id, samples=STABLE_SAMPLES):
    """Average multiple detections to reduce measurement noise."""
    xs, zs, ths = [], [], []
    for _ in range(samples * 2):
        pose = detector.detect(target_id)
        if pose:
            xs.append(pose[0])
            zs.append(pose[1])
            ths.append(pose[2])
            if len(xs) >= samples:
                break
        time.sleep(0.05)
    if not xs:
        return None
    n = len(xs)
    return sum(xs) / n, sum(zs) / n, sum(ths) / n


# ---------------------------------------------------------------------------
# ParkingPlanner
# ---------------------------------------------------------------------------

class ParkingPlanner:

    def __init__(self, detector, uart, target_id=None):
        self._detector    = detector
        self._uart        = uart
        self._target      = target_id
        self._state       = _STREAMING
        self._miss_count  = 0          # consecutive frames with no detection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_target(self, target_id: int):
        self._target = target_id

    def reset(self):
        """Call when re-entering APPROACHING state."""
        self._state      = _STREAMING
        self._miss_count = 0

    def tick(self, pose):
        """
        Process one frame.

        pose : (x, z, theta) from ArucoDetector.detect(), or None.

        Returns a command tuple — see module docstring.
        """
        if self._state == _STREAMING:
            return self._tick_streaming(pose)

        elif self._state == _EVALUATING:
            return self._tick_evaluating()

        elif self._state == _DONE:
            return ('done',)

        return ('lost',)

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _tick_streaming(self, pose):
        if pose is None:
            self._miss_count += 1
            print(f"[PARK] No detection ({self._miss_count}/{RECOVERY_MISS_LIMIT})")
            if self._miss_count < RECOVERY_MISS_LIMIT:
                self._uart.send_stop()
                return ('lost',)
            # Persistent loss — back up to widen FOV
            self._miss_count = 0
            print("[PARK] Marker lost — recovery reverse")
            self._uart.send_stop()
            time.sleep(0.5)
            while True:
                ok = self._uart.send_move(0.0, RECOVERY_DISTANCE_M, REVERSE_SPEED)
                if ok:
                    break
                print("[PARK] Recovery move failed — retrying")
                time.sleep(1.0)
            self._detector.reset()
            return ('lost',)

        self._miss_count = 0
        x, z, theta = pose

        if z <= EVAL_DISTANCE_M:
            print(f"[PARK] z={z:.3f}m — stopping to evaluate alignment")
            self._uart.send_stop()
            time.sleep(0.5)
            self._state = _EVALUATING
            return self._tick_evaluating()

        speed = self._ramp_speed(z)
        return ('stream', x, z, speed)

    def _tick_evaluating(self):
        stable = _stable_pose(self._detector, self._target)

        if stable is None:
            print("[PARK] Stable pose failed — backing up to recover")
            self._uart.send_move(0.0, RECOVERY_DISTANCE_M, REVERSE_SPEED)
            self._detector.reset()
            self._state = _STREAMING
            return ('lost',)

        x, z, theta = stable
        print(f"[PARK] Stable pose — x={x:+.3f}m  z={z:.3f}m  theta={theta:+.1f}°")

        if abs(x) <= MAX_X_ERROR_M and abs(theta) <= MAX_THETA_ERROR:
            print("[PARK] Aligned! Executing final park nudge.")
            final_z = max(0.01, z - CAMERA_OFFSET_M)
            self._state = _DONE
            return ('move', 0.0, final_z, MIN_SPEED)

        print(f"[PARK] Misaligned — reversing")
        self._do_reverse(theta)
        self._state = _STREAMING
        return ('reset',)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ramp_speed(self, z: float) -> float:
        if z >= RAMP_START_M:
            return MAX_SPEED
        return MIN_SPEED + (z / RAMP_START_M) * (MAX_SPEED - MIN_SPEED)

    def _do_reverse(self, theta: float):
        """
        Two-step blocking maneuver:
          1. Curved reverse — steer proportional to theta to correct heading
          2. Straight reverse — open up distance for a clean re-approach
        Both steps retry on failure.
        """
        steer_x = -theta * REVERSE_KP
        steer_x = max(-MAX_REVERSE_X, min(MAX_REVERSE_X, steer_x))
        print(f"[PARK] Step 1 (curved): x={steer_x:+.3f}  z={REVERSE_DISTANCE_M}")
        while True:
            ok = self._uart.send_move(steer_x, REVERSE_DISTANCE_M, REVERSE_SPEED)
            if ok:
                break
            print("[PARK] Step 1 failed — retrying")
            time.sleep(1.0)

        print(f"[PARK] Step 2 (straight): x=0.000  z={STRAIGHT_REVERSE_M}")
        while True:
            ok = self._uart.send_move(0.0, STRAIGHT_REVERSE_M, REVERSE_SPEED)
            if ok:
                break
            print("[PARK] Step 2 failed — retrying")
            time.sleep(1.0)

        print("[PARK] Reverse maneuver complete — re-approaching")
        self._detector.reset()
