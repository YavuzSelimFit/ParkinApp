import rp2
from machine import Pin, Timer

# --- PIN DEFINITIONS ---
# Each sensor: (TRIG, ECHO, state_machine_index)
SENSOR_PINS = {
    "front"       : (28, 19, 0),
    "front_left"  : (27, 18, 1),
    "front_right" : (26, 17, 2),
    "rear"        : (20, 14, 3),
    "left"        : (21, 15, 4),
    "right"       : (22, 16, 5),
}

# --- SHARED DISTANCE BUFFER ---
# Updated by IRQ callbacks, read by any code without blocking
distances = {
    "front"       : None,
    "front_left"  : None,
    "front_right" : None,
    "rear"        : None,
    "left"        : None,
    "right"       : None,
}

# --- PIO PROGRAM ---
@rp2.asm_pio(
    set_init=rp2.PIO.OUT_LOW,
    in_shiftdir=rp2.PIO.SHIFT_LEFT
)
def ultrasonic():
    wrap_target()
    pull(block)                     # Wait for trigger
    set(pins, 1)                    # TRIG high
    nop() [9]                       # 10us pulse
    set(pins, 0)                    # TRIG low
    wait(1, pin, 0)                 # Wait for ECHO high
    set(x, 0)
    mov(x, invert(x))               # X = 0xFFFFFFFF
    label("count")
    jmp(x_dec, "check")
    label("check")
    jmp(pin, "count")               # Count while ECHO high
    mov(isr, x)
    push(noblock)
    irq(rel(0))                     # Notify CPU
    wrap()


# --- SETUP ---
_state_machines = {}
_trigger_timers = {}


def _make_irq_callback(name, sm):
    """Returns an IRQ callback bound to a specific sensor name."""
    def _callback(sm):
        if sm.rx_fifo() == 0:
            return
        raw      = sm.get()
        pulse_us = (0xFFFFFFFF - raw) * 2
        dist     = pulse_us / 58.0
        distances[name] = round(dist, 1) if dist <= 400 else None
    return _callback


def _make_trigger_callback(sm):
    """Returns a timer callback that triggers a specific state machine."""
    def _callback(t):
        sm.put(1)
    return _callback


def start():
    """
    Initialize all 6 PIO state machines and start measurement timers.
    Call once at startup, ideally from Core 1.
    """
    global _state_machines, _trigger_timers

    for name, (trig, echo, sm_id) in SENSOR_PINS.items():
        sm = rp2.StateMachine(
            sm_id,
            ultrasonic,
            freq=1_000_000,
            set_base=Pin(trig),
            in_base=Pin(echo),
            jmp_pin=Pin(echo)
        )

        sm.irq(handler=_make_irq_callback(name, sm))
        sm.active(1)

        timer = Timer()
        timer.init(
            period=120,
            mode=Timer.PERIODIC,
            callback=_make_trigger_callback(sm)
        )

        _state_machines[name] = sm
        _trigger_timers[name] = timer


def stop():
    """Deactivate all state machines and timers. Call on shutdown."""
    for timer in _trigger_timers.values():
        timer.deinit()
    for sm in _state_machines.values():
        sm.active(0)


def get_distances():
    """
    Return a copy of the latest distance readings (cm).
    None means out of range or not yet measured.
    """
    return dict(distances)
