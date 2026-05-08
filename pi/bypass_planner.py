# pi/bypass_planner.py — FOV-Aware Obstacle Bypass Planner for Ackermann Steering

import time

# --- Tunable Constants ---
TARGET_WALL_DIST_M = 0.30   
WALL_FOLLOW_KP     = 1.5    
BYPASS_SPEED       = 0.25   
CLEARANCE_TIME_SEC = 2.0    

TURN_OUT_STEER_X   = 0.50   
RE_ACQUIRE_STEER_X = 0.35   

# Acil Durum Geri Vites Sabitleri
CRITICAL_FRONT_M   = 0.15   # Çarpmaya ramak kaldığını belirten eşik (15 cm)
BACKOFF_TARGET_M   = 0.35   # Geri çıkarak açmak istediğimiz güvenli mesafe (35 cm)

_TURN_OUT    = "TURN_OUT"
_WALL_FOLLOW = "WALL_FOLLOW"
_CLEARANCE   = "CLEARANCE"
_RE_ACQUIRE  = "RE_ACQUIRE"
_BACKOFF     = "BACKOFF"

class BypassPlanner:
    def __init__(self):
        self._state = _TURN_OUT
        self.dir = 1 
        self._clearance_start_time = 0.0 

    def reset(self, direction=1):
        self._state = _TURN_OUT
        self.dir = direction
        self._clearance_start_time = 0.0
        dir_str = "RIGHT" if direction == 1 else "LEFT"
        print(f"[BYPASS] Reset to TURN_OUT. Bypassing from the {dir_str}.")

    def tick(self, sensors, pose):
        # --- GLOBAL GÜVENLİK KONTROLÜ (Acil Geri Vites Tetikleyici) ---
        if sensors and self._state not in (_BACKOFF, _CLEARANCE): 
            front = sensors.get('front')
            if front is not None and front < CRITICAL_FRONT_M:
                print(f"[BYPASS] IMMINENT COLLISION ({front:.2f}m)! Triggering BACKOFF.")
                self._state = _BACKOFF

        if self._state == _TURN_OUT:
            return self._tick_turn_out(sensors)
        elif self._state == _WALL_FOLLOW:
            return self._tick_wall_follow(sensors)
        elif self._state == _CLEARANCE:
            return self._tick_clearance()
        elif self._state == _RE_ACQUIRE:
            return self._tick_re_acquire(pose)
        elif self._state == _BACKOFF:
            return self._tick_backoff(sensors)

        return ('stream', 0.0, 1.0, 0.0)

    def _tick_turn_out(self, sensors):
        steer_cmd = TURN_OUT_STEER_X * self.dir
        if not sensors:
            return ('stream', steer_cmd, 1.0, BYPASS_SPEED)
            
        front = sensors.get('front')
        front_clear = (front is None or front > 0.35)

        if self.dir == 1: 
            f_diag = sensors.get('front_left')
            side   = sensors.get('left')
        else:             
            f_diag = sensors.get('front_right')
            side   = sensors.get('right')

        f_diag_clear = (f_diag is None or f_diag > 0.35)
        side_caught  = (side is not None and side < 0.40)

        if front_clear and f_diag_clear and side_caught:
            print("[BYPASS] Sensor handoff complete -> WALL_FOLLOW")
            self._state = _WALL_FOLLOW
        
        return ('stream', steer_cmd, 1.0, BYPASS_SPEED)

    def _tick_wall_follow(self, sensors):
        if not sensors:
            return ('stream', 0.0, 1.0, BYPASS_SPEED)

        side_dist = sensors.get('left') if self.dir == 1 else sensors.get('right')

        if side_dist is None or side_dist > 0.60:
            print("[BYPASS] Wall ended -> CLEARANCE")
            self._state = _CLEARANCE
            self._clearance_start_time = time.time() 
            return ('stream', 0.0, 1.0, BYPASS_SPEED)

        error = side_dist - TARGET_WALL_DIST_M
        
        if self.dir == 1:
            x_cmd = -error * WALL_FOLLOW_KP 
        else:
            x_cmd = error * WALL_FOLLOW_KP  
            
        x_cmd = max(-0.35, min(0.35, x_cmd)) 
        return ('stream', x_cmd, 1.0, BYPASS_SPEED)

    def _tick_clearance(self):
        elapsed = time.time() - self._clearance_start_time
        if elapsed < CLEARANCE_TIME_SEC:
            return ('stream', 0.0, 1.0, BYPASS_SPEED)
        else:
            print("[BYPASS] Clearance complete -> RE_ACQUIRE")
            self._state = _RE_ACQUIRE
            return ('stream', 0.0, 1.0, BYPASS_SPEED) 

    def _tick_re_acquire(self, pose):
        if pose is not None:
            print("[BYPASS] Target re-acquired! Maneuver complete.")
            return ('done',)
            
        steer_cmd = -RE_ACQUIRE_STEER_X * self.dir
        return ('stream', steer_cmd, 1.0, BYPASS_SPEED)

    def _tick_backoff(self, sensors):
        if not sensors:
            return ('stream', 0.0, -1.0, BYPASS_SPEED)
            
        front = sensors.get('front')
        rear  = sensors.get('rear')
        
        # Geri çıkarken arkaya çarpmamak için ekstra koruma
        if rear is not None and rear < 0.10:
            print("[BYPASS] Rear blocked during backoff! Forcing TURN_OUT.")
            self._state = _TURN_OUT
            return ('stream', 0.0, 1.0, 0.0)

        # Ön taraf yeterince açılana kadar geri git
        if front is None or front > BACKOFF_TARGET_M:
            print(f"[BYPASS] Backoff complete (Front clear). Resuming TURN_OUT.")
            self._state = _TURN_OUT
            return ('stream', 0.0, 1.0, 0.0)
            
        # Burnun yönünü dışarı atmak için direksiyonu kaçış yönünün TERSİNE kırarak geri çık
        steer_cmd = -TURN_OUT_STEER_X * self.dir
        return ('stream', steer_cmd, -1.0, BYPASS_SPEED)  # z = -1.0 ile geri vites
