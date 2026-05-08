import math
from machine import Pin, PWM
import time

# --- CALIBRATION ---
PULSES_PER_CM   = 154.56
SERVO_OFFSET    = 7          # physical alignment offset in degrees
SYNC_GAIN       = 0.4        # encoder sync correction gain (straight driving)
STEERING_GAIN   = 2.0        # amplifies computed steering angle (tune as needed)
SERVO_MIN       = 45         # minimum servo angle (degrees)
SERVO_MAX       = 135        # maximum servo angle (degrees)

# --- VEHICLE DIMENSIONS ---
WHEELBASE       = 15.0       # cm, front-to-rear axle distance
TRACK_WIDTH     = 17.0       # cm, rear axle width

# --- PIN DEFINITIONS ---
stby            = Pin(5,  Pin.OUT)
stby.value(1)

in1_left        = Pin(3,  Pin.OUT)
in2_left        = Pin(4,  Pin.OUT)
pwm_left        = PWM(Pin(2))
pwm_left.freq(1000)

in1_right       = Pin(6,  Pin.OUT)
in2_right       = Pin(7,  Pin.OUT)
pwm_right       = PWM(Pin(8))
pwm_right.freq(1000)

enc_left_a      = Pin(9,  Pin.IN, Pin.PULL_UP)
enc_left_b      = Pin(10, Pin.IN, Pin.PULL_UP)
enc_right_a     = Pin(11, Pin.IN, Pin.PULL_UP)
enc_right_b     = Pin(12, Pin.IN, Pin.PULL_UP)

servo_pin       = PWM(Pin(13))
servo_pin.freq(50)

# --- ENCODER COUNTERS ---
left_pulses  = 0
right_pulses = 0


# --- INTERNAL: ENCODER INTERRUPTS ---
def _left_encoder_irq(pin):
    global left_pulses
    if enc_left_a.value() == 1:
        left_pulses += 1
    else:
        left_pulses -= 1

def _right_encoder_irq(pin):
    global right_pulses
    if enc_right_a.value() == 1:
        right_pulses -= 1
    else:
        right_pulses += 1

enc_left_b.irq(trigger=Pin.IRQ_RISING,  handler=_left_encoder_irq)
enc_right_b.irq(trigger=Pin.IRQ_RISING, handler=_right_encoder_irq)


# --- INTERNAL: SERVO ---
def _set_servo(angle_deg):
    """Set servo to angle_deg (0–180). Centre = 90 + SERVO_OFFSET."""
    min_duty = 1638
    max_duty = 8192
    duty = int(min_duty + (angle_deg / 180.0) * (max_duty - min_duty))
    servo_pin.duty_u16(duty)


# --- INTERNAL: MOTOR DRIVE ---
def _drive(left_speed, right_speed):
    """
    Drive both motors.
    left_speed / right_speed: signed int, range –255 to 255.
    Positive = forward.
    """
    # Left motor (inverted)
    if left_speed >= 0:
        in1_left.value(0); in2_left.value(1)
    else:
        in1_left.value(1); in2_left.value(0)
    pwm_left.duty_u16(max(0, min(65535, int((abs(left_speed) / 255.0) * 65535))))

    # Right motor
    if right_speed >= 0:
        in1_right.value(0); in2_right.value(1)
    else:
        in1_right.value(1); in2_right.value(0)
    pwm_right.duty_u16(max(0, min(65535, int((abs(right_speed) / 255.0) * 65535))))


def _stop():
    pwm_left.duty_u16(0)
    pwm_right.duty_u16(0)


# --- INTERNAL: STEERING CALCULATION ---
def _calc_steering(x, z_abs):
    """
    Hesaplar ve uygulanabilir aralığa kırpar.
    x     : yanal sapma (-1.0..1.0)
    z_abs : normalleştirilmiş ileri mesafe (her zaman pozitif)
    Döner : steering_deg (kırpılmış)
    """
    if z_abs < 1e-4:
        z_abs = 1e-4  # sıfıra bölmeyi önle
    steering_deg = math.degrees(math.atan2(x, z_abs)) * STEERING_GAIN
    max_s = SERVO_MAX - 90 - SERVO_OFFSET
    min_s = SERVO_MIN - 90 - SERVO_OFFSET
    return max(min_s, min(max_s, steering_deg))


def _ackermann_pwm(base_pwm, steering_deg):
    """
    Ackermann diferansiyeli için iç/dış tekerlek PWM'ini hesaplar.
    Döner: (left_pwm, right_pwm) — unsigned (0..255 arası).
    İşaret bilgisi _drive() tarafından yönetilir.
    """
    if abs(steering_deg) < 0.5:
        # Düz — encoder sync uygula
        return base_pwm, base_pwm

    angle_rad   = math.radians(abs(steering_deg))
    R           = WHEELBASE / math.tan(angle_rad)
    ratio_inner = (R - TRACK_WIDTH / 2) / R
    ratio_outer = (R + TRACK_WIDTH / 2) / R

    if steering_deg > 0:   # sağa dön: sağ tekerlek iç
        return int(base_pwm * ratio_outer), int(base_pwm * ratio_inner)
    else:                  # sola dön: sol tekerlek iç
        return int(base_pwm * ratio_inner), int(base_pwm * ratio_outer)


# --- PUBLIC: STOP ---
def stop():
    """Immediately stop both motors."""
    _stop()
    _set_servo(90 + SERVO_OFFSET)


# --- PUBLIC: STREAM (non-blocking, RC ve otonom streaming için) ---
def stream(x, z, speed):
    """
    Sürekli akış modunda motoru ve servoyu ayarlar.  BLOKLAMA YAPMAZ.

    Pi her kamera karesinde (otonom mod) veya joystick güncellemesinde (RC mod)
    bu komutu gönderir. Pico aldığında hemen uygular ve geri döner.

    Parametreler
    ------------
    x     : float  Yanal sapma −1.0..+1.0   (+ = sağ, − = sol)
    z     : float  İleri/geri yön −1.0..+1.0 (+ = ileri, − = geri)
    speed : float  Normalize hız 0.0..1.0

    z = 0 veya speed = 0 ise motorlar durdurulur, servo merkeze gelir.
    """
    if speed <= 0.0 or (abs(x) < 0.01 and abs(z) < 0.01):
        _stop()
        _set_servo(90 + SERVO_OFFSET)
        return

    base_pwm     = int(max(0.0, min(1.0, speed)) * 255)
    steering_deg = _calc_steering(x, abs(z))

    # Servo pozisyonu — geri gidişte direksiyon yönü aynı
    servo_angle = 90 + SERVO_OFFSET + steering_deg
    servo_angle = max(SERVO_MIN, min(SERVO_MAX, servo_angle))
    _set_servo(servo_angle)

    left_pwm, right_pwm = _ackermann_pwm(base_pwm, steering_deg)

    # Encoder sync (düz sürüşte)
    if abs(steering_deg) < 0.5:
        error      = abs(left_pulses) - abs(right_pulses)
        correction = int(error * SYNC_GAIN)
        left_pwm   = max(0, min(255, left_pwm  - correction))
        right_pwm  = max(0, min(255, right_pwm + correction))

    # Yön: z işareti ileri/geri belirler
    direction = 1 if z >= 0 else -1
    _drive(left_pwm * direction, right_pwm * direction)


# --- PUBLIC: MOVE (blocking, enkoder tabanlı, belirli mesafe için) ---
def move(x, z, speed, obstacle_check=None):
    """
    Drive the vehicle toward the target point (x, z).

    Parameters
    ----------
    x              : float  Lateral offset in metres  (+ = right, – = left)
    z              : float  Forward/reverse distance in metres
                            Positive = forward, Negative = reverse.
    speed          : float  Normalised speed 0.0–1.0
    obstacle_check : callable or None
        Called every loop iteration with (completed_cm: float).
        Should return (sensor_id: int, range_mm: int, completed_mm: int)
        if an obstacle is detected, or None to continue.

    Returns
    -------
    None if completed normally.
    (sensor_id, range_mm, completed_mm) tuple if interrupted by obstacle.
    """
    global left_pulses, right_pulses

    if z == 0:
        return None                          # refuse zero target

    # Direction: +1 = forward, -1 = reverse
    direction = 1 if z > 0 else -1
    z_abs     = abs(z)

    steering_deg  = _calc_steering(x, z_abs)

    # Target distance (always positive)
    target_cm     = z_abs * 100.0
    target_pulses = int(target_cm * PULSES_PER_CM)

    # Base PWM (0–255)
    base_pwm = int(max(0.0, min(1.0, speed)) * 255)

    # --- Servo ---
    # Geri vites sırasında servo yönü tersine çevrilir
    effective_steering = steering_deg * direction
    servo_angle = 90 + SERVO_OFFSET + effective_steering
    servo_angle = max(SERVO_MIN, min(SERVO_MAX, servo_angle))
    _set_servo(servo_angle)
    time.sleep(0.4)                          # allow servo to reach position

    # --- Reset encoders ---
    left_pulses  = 0
    right_pulses = 0

    # --- Drive loop ---
    while True:
        abs_left  = abs(left_pulses)
        abs_right = abs(right_pulses)

        # --- Obstacle check ---
        if obstacle_check is not None:
            avg_pulses   = (abs_left + abs_right) / 2
            completed_cm = avg_pulses / PULSES_PER_CM
            obs = obstacle_check(completed_cm)
            if obs is not None:
                _stop()
                _set_servo(90 + SERVO_OFFSET)
                return obs                   # (sensor_id, range_mm, completed_mm)

        left_pwm, right_pwm = _ackermann_pwm(base_pwm, steering_deg)

        if abs(steering_deg) < 0.5:
            # Düz: encoder sync
            error      = abs_left - abs_right
            correction = int(error * SYNC_GAIN)
            left_pwm   = max(0, min(255, left_pwm  - correction))
            right_pwm  = max(0, min(255, right_pwm + correction))

        # direction ile çarp: geri viteste motorlar ters döner
        _drive(left_pwm * direction, right_pwm * direction)

        # Exit when average pulse count reaches target
        if (abs_left + abs_right) / 2 >= target_pulses:
            _stop()
            break

        time.sleep(0.01)

    # Return servo to centre
    _set_servo(90 + SERVO_OFFSET)
    return None                              # completed normally
