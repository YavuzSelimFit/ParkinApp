from machine import Pin, UART
import struct
import time
import _thread
from mcu import move, stop
from sensors import get_distances

# --- PROTOCOL CONSTANTS ---
MSG_MARKER      = b'\xAA\xFF'

MSG_HEARTBEAT   = 0x01
MSG_POSE        = 0x02
MSG_MARKER_LOST = 0x03
MSG_ACK         = 0x04
MSG_NACK        = 0x05
MSG_ID          = 0x06
MSG_SENSOR_DATA = 0x07
MSG_OBSTACLE    = 0x08
MSG_QUERY       = 0x09
MSG_STOP        = 0x0A

# --- UART SETUP ---
uart      = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))
uart_lock = _thread.allocate_lock()     # prevents concurrent writes from both cores

# --- OBSTACLE DETECTION THRESHOLDS ---
# Values in cm. Trigger if sensor reading is below threshold.
OBSTACLE_THRESHOLDS_CM = {
    "front"       : 20.0,
    "front_left"  : 15.0,
    "front_right" : 15.0,
    "rear"        : 10.0,
    "left"        :  8.0,
    "right"       :  8.0,
}

# Maps sensor key to numeric ID sent over UART
# Pi side maps 0→FC, 1→FL, 2→FR, 3→RR, 4→SL, 5→SR
SENSOR_ID_MAP = {
    "front"       : 0,
    "front_left"  : 1,
    "front_right" : 2,
    "rear"        : 3,
    "left"        : 4,
    "right"       : 5,
}


# --- HELPERS ---
def _checksum(payload: bytes) -> int:
    """XOR of all payload bytes. Returns 0x00 for empty payload."""
    result = 0
    for b in payload:
        result ^= b
    return result


def _build_packet(msg_type: int, payload: bytes = b'') -> bytes:
    """Assemble a full packet: marker + type + payload + checksum."""
    return MSG_MARKER + bytes([msg_type]) + payload + bytes([_checksum(payload)])


def _send(msg_type: int, payload: bytes = b''):
    """Send a packet over UART — protected by lock for cross-core safety."""
    packet = _build_packet(msg_type, payload)
    uart_lock.acquire()
    uart.write(packet)
    uart_lock.release()


def _send_ack():
    _send(MSG_ACK)

def _send_nack():
    _send(MSG_NACK)


def _parse_packet(data: bytes):
    """
    Parse a raw incoming packet.
    Returns (msg_type, payload) or (None, None) on failure.
    """
    if len(data) < 4:
        return None, None
    if data[0:2] != MSG_MARKER:
        return None, None

    msg_type = data[2]
    payload  = data[3:-1]
    checksum = data[-1]

    if _checksum(payload) != checksum:
        _send_nack()
        return None, None

    return msg_type, payload


# --- MESSAGE HANDLERS ---
# To add a new message type:
#   1. Add MSG_* constant at the top
#   2. Define a handler function below
#   3. Register it in HANDLERS dict
#   4. Add payload length to _expected_payload_len

def _handle_heartbeat(payload: bytes):
    _send(MSG_HEARTBEAT)


def _handle_pose(payload: bytes):
    """
    Receive target pose (x, z, speed), execute move(), then ACK.
    If an obstacle is detected during move, send MSG_OBSTACLE instead.
    Payload: 3 × float32 = x (m), z (m), speed (0.0–1.0).
    """
    if len(payload) != 12:
        _send_nack()
        return
    x, z, speed = struct.unpack('fff', payload)
    print(f"[UART] Pose: x={x:.3f} z={z:.3f} speed={speed:.2f}")

    def _obstacle_check(completed_cm: float):
        """Check all sensors against thresholds. Returns obstacle tuple or None."""
        d = get_distances()
        for key, threshold in OBSTACLE_THRESHOLDS_CM.items():
            val = d.get(key)
            if val is not None and val < threshold:
                sensor_id   = SENSOR_ID_MAP[key]
                range_mm    = int(val * 10)
                completed_mm = int(completed_cm * 10)
                return (sensor_id, range_mm, completed_mm)
        return None

    result = move(x=x, z=z, speed=speed, obstacle_check=_obstacle_check)

    if result is None:
        # Completed normally
        _send_ack()
    else:
        # Obstacle detected — report to Pi
        sensor_id, range_mm, completed_mm = result
        obs_payload = struct.pack('BHH', sensor_id, range_mm, completed_mm)
        _send(MSG_OBSTACLE, obs_payload)


def _handle_marker_lost(payload: bytes):
    print("[UART] Marker lost — stopping.")
    stop()
    _send_ack()


def _handle_id(payload: bytes):
    if len(payload) != 1:
        _send_nack()
        return
    spot_id = payload[0]
    print(f"[UART] Requested spot ID: {spot_id}")
    _send_ack()


def _handle_query(payload: bytes):
    """Respond to a sensor query with current sensor data."""
    send_sensor_data()


def _handle_stop(payload: bytes):
    """Emergency stop — halt motors immediately."""
    stop()
    _send_ack()


# Handler registry: msg_type -> function
HANDLERS = {
    MSG_HEARTBEAT   : _handle_heartbeat,
    MSG_POSE        : _handle_pose,
    MSG_MARKER_LOST : _handle_marker_lost,
    MSG_ID          : _handle_id,
    MSG_QUERY       : _handle_query,
    MSG_STOP        : _handle_stop,
}


# --- SENSOR DATA SENDER ---
# Sensor order: front, front_left, front_right, rear, left, right
_SENSOR_ORDER = ["front", "front_left", "front_right", "rear", "left", "right"]

def send_sensor_data():
    """
    Pack latest sensor distances and send to Pi.
    None values are encoded as -1.0 (out of range sentinel).
    Payload: 6 x float32 = 24 bytes.
    """
    d = get_distances()
    values = [d[k] if d[k] is not None else -1.0 for k in _SENSOR_ORDER]
    payload = struct.pack('6f', *values)
    _send(MSG_SENSOR_DATA, payload)


# --- MAIN LOOP ---
def run():
    """Start listening for incoming UART packets. Call this from main.py."""
    print("[UART] Pico UART listener started.")
    buffer = b''

    while True:
        if uart.any():
            buffer += uart.read(uart.any())

            # Find marker and process one packet at a time
            while True:
                idx = buffer.find(MSG_MARKER)
                if idx == -1:
                    buffer = b''
                    break

                # Discard anything before the marker
                buffer = buffer[idx:]

                # Need at least 4 bytes (marker + type + checksum)
                if len(buffer) < 4:
                    break

                msg_type    = buffer[2]
                payload_len = _expected_payload_len(msg_type)

                if payload_len is None:
                    # Unknown type — discard marker and keep scanning
                    buffer = buffer[2:]
                    continue

                packet_len = 2 + 1 + payload_len + 1   # marker + type + payload + checksum
                if len(buffer) < packet_len:
                    break                               # wait for more bytes

                packet = buffer[:packet_len]
                buffer = buffer[packet_len:]

                _, payload = _parse_packet(packet)
                if payload is None:
                    continue                            # NACK already sent by _parse_packet

                handler = HANDLERS.get(msg_type)
                if handler:
                    handler(payload)
                else:
                    _send_nack()

        time.sleep_ms(5)


def _expected_payload_len(msg_type: int):
    """
    Returns the expected payload length for a given message type.
    Add an entry here whenever a new type is defined.
    Returns None for unknown types.
    """
    PAYLOAD_LENGTHS = {
        MSG_HEARTBEAT   : 0,
        MSG_POSE        : 12,   # 3 × float32 (x, z, speed)
        MSG_MARKER_LOST : 0,
        MSG_ACK         : 0,
        MSG_NACK        : 0,
        MSG_ID          : 1,    # 1 byte spot ID
        MSG_SENSOR_DATA : 24,   # 6 × float32
        MSG_OBSTACLE    : 5,    # 1B sensor_id + 2B range_mm + 2B completed_mm
        MSG_QUERY       : 0,
        MSG_STOP        : 0,
    }
    return PAYLOAD_LENGTHS.get(msg_type, None)
