# pi/main.py — Entry point for the autonomous summoning vehicle.
#
# Initialises all components and waits for a "PARK:<id>" command
# from the mobile app over Bluetooth before starting the FSM.
#
# Keys (always active):
#   m — toggle manual / auto mode
#   q — quit
#
# Keys (manual mode only):
#   i — force IDLE
#   s — force SEARCHING
#   a — force APPROACHING
#   r — force ARRIVED
#
# Press Ctrl+C to stop cleanly.

import sys
import tty
import termios
import select
import traceback

from aruco import ArucoDetector
from uart import UARTController
from fsm import FSM, IDLE, SEARCHING, APPROACHING, BYPASSING, ARRIVED
from ble_server import BLEServer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UART_PORT = '/dev/ttyAMA0'
UART_BAUD = 115200

# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

def _setup_terminal():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)           # immediate input, Ctrl+C still works
    return old

def _restore_terminal(old):
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)

def _read_key():
    """Return pressed key or None if nothing waiting."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

print("Initialising...")
detector = ArucoDetector()
uart     = UARTController(port=UART_PORT, baud=UART_BAUD)

print("Checking Pico connection...")
if not uart.heartbeat():
    print("[ERROR] No heartbeat from Pico — check wiring.")
    detector.stop()
    exit()

print("Pico alive.\n")

fsm = FSM(detector, uart)
# FSM starts in IDLE — it will wait for BLE command before moving.

# ---------------------------------------------------------------------------
# BLE callbacks
# ---------------------------------------------------------------------------

def _on_park_command(target_id: int):
    """Called from BLE thread when mobile app sends PARK:<id>."""
    print(f"\n[MAIN] BLE → park command received: target_id={target_id}")
    if fsm.state() != IDLE:
        print("[MAIN] FSM busy — stopping current run before starting new one.")
        fsm.stop()
    fsm.set_target(target_id)
    fsm.start()
    print(f"[MAIN] FSM started → target marker {target_id}")

def _on_stop_command():
    """Called from BLE thread when mobile app sends STOP."""
    print("\n[MAIN] BLE → emergency stop received.")
    fsm.stop()

# ---------------------------------------------------------------------------
# Start BLE server (non-blocking background thread)
# ---------------------------------------------------------------------------

ble = BLEServer(on_park_command=_on_park_command, on_stop_command=_on_stop_command)
ble.start()

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

manual_mode = False

print("Waiting for PARK command from mobile app over Bluetooth…")
print("Keys: [m] toggle manual/auto  [i] IDLE  [s] SEARCHING  "
      "[a] APPROACHING  [r] ARRIVED  [q] quit\n")

old_term = _setup_terminal()

try:
    while True:
        key = _read_key()

        if key == 'm':
            manual_mode = not manual_mode
            print(f"\n[MAIN] Mode: {'MANUAL' if manual_mode else 'AUTO'}")

        elif key == 'q':
            break

        elif manual_mode:
            if key == 'i':
                fsm.force_state(IDLE)
            elif key == 's':
                fsm.force_state(SEARCHING)
            elif key == 'a':
                fsm.force_state(APPROACHING)
            elif key == 'r':
                fsm.force_state(ARRIVED)

        try:
            fsm.tick()
        except Exception as e:
            print(f"\n[MAIN] tick error — {e}")
            traceback.print_exc()
            # Don't exit — keep the loop alive so ARRIVED state persists

except KeyboardInterrupt:
    pass
finally:
    _restore_terminal(old_term)
    print("\nStopping.")
    ble.stop()
    fsm.stop()
    detector.stop()
