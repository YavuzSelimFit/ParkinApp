import serial
import struct
import time
import math

# --- PROTOCOL CONSTANTS ---
MSG_MARKER      = bytes([0xAA, 0xFF])

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
MSG_DONE        = 0x0B
MSG_STREAM      = 0x0C

HEARTBEAT_INTERVAL = 1.0    # seconds
TIMEOUT            = 0.5    # seconds to wait for a short response
MOVE_TIMEOUT       = 60.0   # seconds to wait for a single segment to complete

# --- SEGMENT CONVERSION CONSTANTS ---
# These must match pico/mcu.py STEERING_GAIN
STEERING_GAIN  = 2.0
MAX_SPEED_MM_S = 300.0      # speed_mm_s value that maps to speed=1.0

# --- SENSOR ID MAPPING (Pico→Pi) ---
SENSOR_ID_TO_NAME = {
    0: "FC",
    1: "FL",
    2: "FR",
    3: "RR",
    4: "SL",
    5: "SR",
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


def _parse_response(data: bytes):
    """
    Parse an incoming packet. Returns (msg_type, payload) or (None, None) on failure.
    Expects: AA FF [type] [payload...] [checksum]
    """
    if len(data) < 4:
        return None, None
    if data[0:2] != MSG_MARKER:
        return None, None

    msg_type = data[2]
    payload  = data[3:-1]
    checksum = data[-1]

    if _checksum(payload) != checksum:
        return None, None

    return msg_type, payload


def _segment_to_pose(seg):
    """
    Convert a Segment (distance_mm, angle_deg, speed_mm_s) to
    (x, z, speed) for the Pico mcu.move() interface.

    The Segment.angle_deg is the intended servo deflection in degrees.
    mcu.py computes: steering_deg = atan2(x, z) * STEERING_GAIN
    Inverting:       x = z * tan(angle_deg / STEERING_GAIN)
    """
    z     = seg.distance_mm / 1000.0
    x     = z * math.tan(math.radians(seg.angle_deg / STEERING_GAIN))
    speed = max(0.1, min(1.0, seg.speed_mm_s / MAX_SPEED_MM_S))
    return x, z, speed


# --- UART CONTROLLER (Pi side) ---
class UARTController:
    def __init__(self, port='/dev/ttyAMA0', baud=115200):
        self.ser = serial.Serial(port, baud, timeout=TIMEOUT)
        self._last_heartbeat = 0.0
        self._last_event     = None   # stores latest DONE or OBS event from send_path
        self._latest_sensors = None  # last received sensor data from Pico
        time.sleep(1)
        self.ser.flush()

    # ------------------------------------------------------------------
    # Low-level send / receive
    # ------------------------------------------------------------------
    def _send(self, msg_type: int, payload: bytes = b'') -> bool:
        """Send a packet. Returns True on success."""
        try:
            self.ser.write(_build_packet(msg_type, payload))
            return True
        except Exception as e:
            print(f"[UART] Send error: {e}")
            return False

    def _read_packet(self, deadline: float):
        """
        Scan byte by byte for the marker, then read the full packet.
        Returns (msg_type, payload) or (None, None) on timeout or failure.
        Works for any message type — shared by all receive paths.
        """
        PAYLOAD_LENGTHS = {
            MSG_HEARTBEAT   : 0,
            MSG_POSE        : 12,
            MSG_MARKER_LOST : 0,
            MSG_ACK         : 0,
            MSG_NACK        : 0,
            MSG_ID          : 1,
            MSG_SENSOR_DATA : 24,
            MSG_OBSTACLE    : 5,    # 1B sensor_id + 2B range_mm + 2B completed_mm
            MSG_QUERY       : 0,
            MSG_STOP        : 0,
            MSG_DONE        : 0,
            MSG_STREAM      : 12,   # 3 × float32 (x, z, speed)
        }

        while time.time() < deadline:
            b = self.ser.read(1)
            if not b or b != b'\xAA':
                continue
            b2 = self.ser.read(1)
            if not b2 or b2 != b'\xFF':
                continue

            # Marker found — read type byte
            type_byte = self.ser.read(1)
            if not type_byte:
                continue

            msg_type    = type_byte[0]
            payload_len = PAYLOAD_LENGTHS.get(msg_type)
            if payload_len is None:
                continue                # Unknown type — keep scanning

            # Read payload + checksum
            rest = self.ser.read(payload_len + 1)
            if not rest or len(rest) < payload_len + 1:
                continue

            packet             = MSG_MARKER + type_byte + rest
            msg_type, payload  = _parse_response(packet)
            if msg_type is None:
                continue                # Checksum failed — keep scanning

            return msg_type, payload

        return None, None

    def _send_and_wait(self, msg_type: int, payload: bytes = b'', expect: int = MSG_ACK):
        """
        Send a packet and wait for the expected response type.
        Discards any other packets (e.g. unsolicited sensor data) until
        the expected type arrives or timeout expires.
        """
        self.ser.reset_input_buffer()
        self._send(msg_type, payload)
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            resp_type, resp_payload = self._read_packet(deadline)
            if resp_type == expect:
                return True, resp_payload
        return False, None

    # ------------------------------------------------------------------
    # Standard API
    # ------------------------------------------------------------------
    def heartbeat(self) -> bool:
        """Send heartbeat and expect one back. Returns True if alive."""
        success, _ = self._send_and_wait(MSG_HEARTBEAT, expect=MSG_HEARTBEAT)
        self._last_heartbeat = time.time()
        return success

    def send_marker_lost(self) -> bool:
        """Notify Pico that the marker is no longer in view."""
        success, _ = self._send_and_wait(MSG_MARKER_LOST, expect=MSG_ACK)
        return success

    def send_id(self, spot_id: int) -> bool:
        """Send requested parking spot ID (1 byte). Returns True on ACK."""
        payload = bytes([spot_id])
        success, _ = self._send_and_wait(MSG_ID, payload, expect=MSG_ACK)
        return success

    def tick(self):
        """Call this in the main loop to send periodic heartbeats."""
        if time.time() - self._last_heartbeat >= HEARTBEAT_INTERVAL:
            alive = self.heartbeat()
            if not alive:
                print("[UART] Heartbeat failed — check connection.")

    def receive_sensor_data(self):
        """
        Read an incoming sensor data packet sent by the Pico (fire-and-forget).
        Returns a dict with keys: front, front_left, front_right, rear, left, right.
        Values are in cm, or None if out of range.
        Returns None if no valid packet is available.
        """
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            msg_type, payload = self._read_packet(deadline)
            if msg_type == MSG_SENSOR_DATA and payload and len(payload) == 24:
                values = struct.unpack('6f', payload)
                keys   = ["front", "front_left", "front_right", "rear", "left", "right"]
                return {k: (round(v, 1) if v >= 0 else None) for k, v in zip(keys, values)}
        return None

    # ------------------------------------------------------------------
    # FSM interface
    # ------------------------------------------------------------------
    def send_path(self, segments) -> bool:
        """
        Send a full path (list of Segments) to the Pico sequentially.
        Waits for each segment to complete (ACK) before sending the next.
        If the Pico reports an obstacle (MSG_OBSTACLE), stops and stores
        the event so receive() can return it.

        Returns True if the path was accepted (even if interrupted).
        Returns False on communication error.
        """
        self._last_event = None

        for i, seg in enumerate(segments, 1):
            x, z, speed = _segment_to_pose(seg)
            payload = struct.pack('fff', x, z, speed)

            self.ser.reset_input_buffer()
            self._send(MSG_POSE, payload)

            # Phase 1 — wait for ACK (transmission confirmed)
            deadline = time.time() + TIMEOUT
            resp_type, _ = self._read_packet(deadline)
            if resp_type != MSG_ACK:
                print(f"[UART] send_path: no ACK on segment {i}")
                return False

            # Phase 2 — wait for DONE or OBSTACLE (move complete)
            deadline = time.time() + MOVE_TIMEOUT
            resp_type, resp_payload = self._read_packet(deadline)

            if resp_type == MSG_DONE:
                # Segment completed — send next
                continue

            elif resp_type == MSG_OBSTACLE:
                if resp_payload and len(resp_payload) == 5:
                    sensor_id, range_mm, completed_mm = struct.unpack('BHH', resp_payload)
                    self._last_event = {
                        "type"        : "OBS",
                        "sensor"      : SENSOR_ID_TO_NAME.get(sensor_id, "FC"),
                        "range_mm"    : int(range_mm),
                        "segment"     : i,
                        "completed_mm": int(completed_mm),
                    }
                else:
                    self._last_event = {
                        "type": "OBS", "sensor": "FC",
                        "range_mm": 0, "segment": i, "completed_mm": 0,
                    }
                return True

            else:
                print(f"[UART] send_path: unexpected response "
                      f"type=0x{resp_type:02X} on segment {i}")
                return False

        # All segments completed
        self._last_event = {"type": "DONE", "status": "OK"}
        return True

    def receive(self, timeout: float = 30.0):
        """
        Return the last event produced by send_path.
        Expected format:
            {"type": "DONE", "status": "OK"}
            {"type": "OBS", "sensor": "FC", "range_mm": 120,
             "segment": 2, "completed_mm": 65}
        Returns None if no event is available.
        """
        return self._last_event

    def poll_sensors(self):
        """
        Non-blocking check for incoming MSG_SENSOR_DATA packets.
        Call this after send_stream() each frame to consume any sensor
        data pushed by the Pico. Updates internal latest_sensors cache.
        Does not block — returns immediately if nothing is waiting.
        """
        SENSOR_KEYS = ["front", "front_left", "front_right", "rear", "left", "right"]
        while self.ser.in_waiting >= 4:
            b = self.ser.read(1)
            if b != b'\xAA':
                continue
            b2 = self.ser.read(1)
            if b2 != b'\xFF':
                continue
            type_byte = self.ser.read(1)
            if not type_byte or type_byte[0] != MSG_SENSOR_DATA:
                continue
            rest = self.ser.read(25)            # 24 payload + 1 checksum
            if len(rest) < 25:
                break
            packet   = MSG_MARKER + type_byte + rest
            msg_type, payload = _parse_response(packet)
            if msg_type == MSG_SENSOR_DATA and payload and len(payload) == 24:
                values = struct.unpack('6f', payload)
                self._latest_sensors = {
                    k: (round(v / 100.0, 3) if v >= 0 else None)   # cm → metres
                    for k, v in zip(SENSOR_KEYS, values)
                }

    def latest_sensors(self):
        """Return the last received sensor data dict, or None if not yet received."""
        return self._latest_sensors

    def send_stream(self, x: float, z: float, speed: float):
        """
        Fire-and-forget streaming pose update.
        No ACK expected — call this every camera frame.
        x, z   : lateral and forward in metres
        speed  : normalised 0.0–1.0
        """
        payload = struct.pack('fff', x, z, speed)
        self._send(MSG_STREAM, payload)

    def send_stop(self) -> bool:
        """Send emergency stop to Pico. Returns True on ACK."""
        success, _ = self._send_and_wait(MSG_STOP, expect=MSG_ACK)
        return success

    def send_query(self):
        """
        Request current sensor readings from Pico.
        Returns a dict with keys: fc_mm, fl_mm, fr_mm, rr_mm, sl_mm, sr_mm.
        Values are in mm, or None if out of range.
        Returns None on timeout.
        """
        success, payload = self._send_and_wait(MSG_QUERY, expect=MSG_SENSOR_DATA)
        if not success or not payload or len(payload) != 24:
            return None

        values   = struct.unpack('6f', payload)
        fsm_keys = ["fc_mm", "fl_mm", "fr_mm", "rr_mm", "sl_mm", "sr_mm"]
        return {
            k: (int(v * 10) if v >= 0 else None)
            for k, v in zip(fsm_keys, values)
        }

    def send_move(self, x: float, z: float, speed: float) -> bool:
        """
        Send a single move command directly in Pico coordinates.

        Two-phase response:
          1. ACK   — Pico received the packet (fast, within TIMEOUT)
          2. DONE  — Pico finished the move   (slow, within MOVE_TIMEOUT)

        Returns True on DONE, False on timeout or error.
        MSG_OBSTACLE during the move is printed and treated as completion.
        """
        payload = struct.pack('fff', x, z, speed)
        self.ser.reset_input_buffer()
        self._send(MSG_POSE, payload)

        # Phase 1 — wait for ACK (transmission confirmed), discard everything else
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            resp_type, _ = self._read_packet(deadline)
            if resp_type == MSG_ACK:
                break
        else:
            print(f"[UART] send_move: no ACK within timeout")
            return False

        # Phase 2 — wait for DONE or OBSTACLE (move complete), discard everything else
        deadline = time.time() + MOVE_TIMEOUT
        while time.time() < deadline:
            resp_type, resp_payload = self._read_packet(deadline)
            if resp_type == MSG_DONE:
                return True
            if resp_type == MSG_OBSTACLE:
                if resp_payload and len(resp_payload) == 5:
                    sensor_id, range_mm, completed_mm = struct.unpack('BHH', resp_payload)
                    print(f"[UART] Obstacle: sensor={SENSOR_ID_TO_NAME.get(sensor_id, '?')} "
                          f"range={range_mm}mm completed={completed_mm}mm")
                return True     # treat obstacle as completion — FSM handles recovery later

        print(f"[UART] send_move: no DONE within timeout")
        return False

    # ------------------------------------------------------------------
    # Extensibility hook
    # ------------------------------------------------------------------
    def send_custom(self, msg_type: int, payload: bytes = b'', expect: int = MSG_ACK):
        """
        Send any custom message type.
        Add new MSG_* constants at the top and call this with the new type.
        """
        return self._send_and_wait(msg_type, payload, expect=expect)
