# pi/fsm.py — Finite State Machine for autonomous marker approach.
#
# States:
#   IDLE        — waiting for start(), motors off
#   SEARCHING   — rotating in place until target marker is found
#   APPROACHING — marker visible, ParkingPlanner drives approach + alignment
#   BYPASSING   — obstacle detected, executing BypassPlanner maneuver
#   ARRIVED     — parked, motors off
#
# Search strategy:
#   Rotate in a fixed direction (SEARCH_DIRECTION) until the target marker
#   appears, then switch to APPROACHING.
#
# BLE entegrasyonu için değişiklikler:
#   - __init__ artık opsiyonel on_arrived_callback alıyor.
#   - ARRIVED durumuna girildiğinde bu callback tetikleniyor.
#
# Usage:
#   fsm = FSM(detector, uart, on_arrived_callback=my_fn)
#   fsm.start()
#   while True:
#       fsm.tick()

import time
from parking_planner import ParkingPlanner
from bypass_planner import BypassPlanner

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

LOST_FRAME_LIMIT   = 30     

# Search
SEARCH_Z           = 0.10   
SEARCH_SPEED       = 0.45   
SEARCH_X           = 0.45   
SEARCH_DIRECTION   = 1      
SEARCH_FRAME_LIMIT = 4000   

# Dynamic Obstacle Detection
EMERGENCY_BRAKE_CENTER_M  = 0.18 # Sadece ana ön sensör tam bypass tetikler
DYNAMIC_OBSTACLE_MARGIN_M = 0.20 # ArUco ile engel ayrımı (Geometrik tolerans)
ZONE_LOCK_DIST_M          = 0.30 # Sadece son 30 cm'de engelleri yoksay (Eskisi 0.65 idi)

# Nudge (Hafif Sıyrılma) Ayarları
CORNER_NUDGE_DIST_M       = 0.20 # Yan sensör tehlike mesafesi
CORNER_NUDGE_STEER        = 0.15 # Kamerayı çok sarsmaması için itme kuvveti


# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------

IDLE        = "IDLE"
SEARCHING   = "SEARCHING"
APPROACHING = "APPROACHING"
BYPASSING   = "BYPASSING"
ARRIVED     = "ARRIVED"


# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------

class FSM:

    def __init__(self, detector, uart, target_id=None, on_arrived_callback=None):
        self.detector = detector
        self.uart     = uart
        self.parking  = ParkingPlanner(detector, uart, target_id)
        
        self.bypass_planner = BypassPlanner()
        self._next_bypass_dir  = 1
        
        self._last_z              = 9.9  
        self._parking_zone_locked = False 

        self._state            = IDLE
        self._prev_state       = None
        self._lost_frames      = 0
        self._search_frames    = 0
        self._target_marker_id = target_id

        # BLE entegrasyonu: Park tamamlandığında çağrılacak callback.
        # Örn: lambda: ble_server.send_notification("STATUS:ARRIVED")
        self.on_arrived_callback = on_arrived_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_target(self, marker_id: int):
        self._target_marker_id = marker_id
        self.parking.set_target(marker_id)
        print(f"[FSM] Target marker ID set to {marker_id}")

    def start(self):
        if self._state == IDLE:
            self._transition(SEARCHING)

    def stop(self):
        self.uart.send_stop()
        self._transition(IDLE)

    def force_state(self, state: str):
        if state not in (IDLE, SEARCHING, APPROACHING, BYPASSING, ARRIVED):
            print(f"[FSM] Unknown state: {state}")
            return
        self._transition(state)

    def state(self):
        return self._state

    def tick(self):
        next_state = None

        if self._state == IDLE:
            next_state = self._run_idle()
        elif self._state == SEARCHING:
            next_state = self._run_searching()
        elif self._state == APPROACHING:
            next_state = self._run_approaching()
        elif self._state == BYPASSING:
            next_state = self._run_bypassing()
        elif self._state == ARRIVED:
            next_state = self._run_arrived()

        if next_state and next_state != self._state:
            self._transition(next_state)

    # ------------------------------------------------------------------
    # State runners
    # ------------------------------------------------------------------

    def _run_idle(self):
        return None

    def _run_searching(self):
        ids = self.detector.detect_any()

        if ids:
            if self._target_marker_id is None:
                self._target_marker_id = ids[0]
                self.parking.set_target(ids[0])
                print(f"[FSM] No target set — accepting ID {ids[0]}")
                return APPROACHING

            if self._target_marker_id in ids:
                print(f"[FSM] Target marker {self._target_marker_id} found.")
                return APPROACHING

        x_cmd = SEARCH_X * SEARCH_DIRECTION
        self.uart.send_stream(x_cmd, SEARCH_Z, SEARCH_SPEED)
        self.uart.poll_sensors()
        self._search_frames += 1

        print(f"[FSM] Searching — frame {self._search_frames}  "
              f"{'CW' if SEARCH_DIRECTION > 0 else 'CCW'}")

        if self._search_frames >= SEARCH_FRAME_LIMIT:
            print("[FSM] Search timeout — returning to IDLE.")
            return IDLE

        return None

    def _run_approaching(self):
        pose = self.detector.detect(self._target_id())
        sensors = self.uart.latest_sensors()
        
        # --- HAFIZA GÜNCELLEMESİ VE BÖLGE KİLİDİ ---
        if pose is not None:
            self._last_z = pose[1]
            if pose[1] <= ZONE_LOCK_DIST_M:
                self._parking_zone_locked = True

        # =================================================================
        # --- 1. PRE-EMPTIVE DYNAMIC OBSTACLE DETECTION (TAM BYPASS) ---
        # =================================================================
        if sensors and not self._parking_zone_locked:
            front_center = sensors.get('front') or 9.9
            
            if front_center < EMERGENCY_BRAKE_CENTER_M:
                trigger_bypass = False
                
                if pose is not None:
                    if pose[1] > ZONE_LOCK_DIST_M and front_center < (pose[1] - DYNAMIC_OBSTACLE_MARGIN_M):
                        trigger_bypass = True
                else:
                    if self._last_z > ZONE_LOCK_DIST_M and front_center < (self._last_z - DYNAMIC_OBSTACLE_MARGIN_M):
                        print(f"[FSM] Blind Obstacle Pre-empted! Object at {front_center:.2f}m")
                        trigger_bypass = True

                if trigger_bypass:
                    fl = sensors.get('front_left') or 9.9
                    fr = sensors.get('front_right') or 9.9
                    
                    if fl < fr and fl < 0.50:
                        self._next_bypass_dir = 1  # Sol kapalı, SAĞA kaç
                    elif fr < fl and fr < 0.50:
                        self._next_bypass_dir = -1 # Sağ kapalı, SOLA kaç
                    else:
                        target_x = pose[0] if pose is not None else 0.0
                        self._next_bypass_dir = -1 if target_x < 0 else 1
                        
                    dir_str = "LEFT" if self._next_bypass_dir == -1 else "RIGHT"
                    print(f"[FSM] Pre-emptive Bypass Decision: {dir_str}.")
                    return BYPASSING

        # =================================================================
        # --- 2. NORMAL PARK AKIŞI VE ANLIK NUDGE (SIYRILMA) ---
        # =================================================================
        cmd  = self.parking.tick(pose)
        tag = cmd[0]

        if tag == 'stream':
            _, x, z, speed = cmd
            
            if sensors and not self._parking_zone_locked:
                fl = sensors.get('front_left') or 9.9
                fr = sensors.get('front_right') or 9.9
                
                if fl < CORNER_NUDGE_DIST_M:
                    print(f"[FSM] Nudge RIGHT (+{CORNER_NUDGE_STEER}) to avoid left corner.")
                    x += CORNER_NUDGE_STEER
                elif fr < CORNER_NUDGE_DIST_M:
                    print(f"[FSM] Nudge LEFT (-{CORNER_NUDGE_STEER}) to avoid right corner.")
                    x -= CORNER_NUDGE_STEER
                
                x = max(-1.0, min(1.0, x))

            self.uart.send_stream(x, z, speed)
            self.uart.poll_sensors()
            self._lost_frames = 0
            if pose is not None:
                print(f"[FSM] approach  x={pose[0]:+.3f}m  z={pose[1]:.3f}m  "
                      f"theta={pose[2]:+.1f}°  spd={speed:.2f}  locked={self._parking_zone_locked}")
            return None

        elif tag == 'move':
            _, x, z, speed = cmd
            print(f"[FSM] Final park move: x={x:.3f}  z={z:.3f}  speed={speed:.2f}")
            self.uart.send_move(x, z, speed)
            return ARRIVED

        elif tag == 'reset':
            self._lost_frames = 0
            print("[FSM] Maneuver done — re-approaching")
            return None

        elif tag == 'done':
            return ARRIVED

        elif tag == 'lost':
            self._lost_frames += 1
            print(f"[FSM] Marker lost ({self._lost_frames}/{LOST_FRAME_LIMIT})")
            if self._lost_frames >= LOST_FRAME_LIMIT:
                print("[FSM] Too many losses — switching to SEARCHING")
                return SEARCHING
            return None

        return None

    def _run_bypassing(self):
        sensors = self.uart.latest_sensors()
        pose    = self.detector.detect(self._target_id())
        cmd     = self.bypass_planner.tick(sensors, pose)

        tag = cmd[0]

        if tag == 'stream':
            _, x, z, speed = cmd
            self.uart.send_stream(x, z, speed)
            self.uart.poll_sensors()
            return None

        elif tag == 'move':
            _, x, z, speed = cmd
            print(f"[FSM] Bypass clearance move: x={x:.3f} z={z:.3f} speed={speed:.2f}")
            self.uart.send_move(x, z, speed)
            return None

        elif tag == 'done':
            print("[FSM] Bypass complete, returning to APPROACHING")
            return APPROACHING

        return None

    def _run_arrived(self):
        return None

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def _transition(self, new_state):
        print(f"[FSM] {self._state} → {new_state}")
        self._prev_state = self._state
        self._state      = new_state
        self._on_enter(new_state)

    def _on_enter(self, state):
        if state == IDLE:
            self.uart.send_stop()

        elif state == SEARCHING:
            self._search_frames = 0

        elif state == APPROACHING:
            self._lost_frames = 0
            self.parking.reset()
            self.detector.reset()
            self._parking_zone_locked = False 

        elif state == BYPASSING:
            self.bypass_planner.reset(direction=self._next_bypass_dir)
            self.uart.send_stop()  
            time.sleep(0.2)

        elif state == ARRIVED:
            self.uart.send_stop()
            # BLE entegrasyonu: Uygulamaya park bilgisini ilet.
            if self.on_arrived_callback is not None:
                try:
                    self.on_arrived_callback()
                except Exception as e:
                    print(f"[FSM] on_arrived_callback error: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _target_id(self):
        return self._target_marker_id
