from machine import Pin, UART
import struct
import time
from mcu import move, stop, stream
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
MSG_DONE        = 0x0B   # Hareket tamamlandı (pi/uart.py send_move/send_path bunu bekler)
MSG_STREAM      = 0x0C   # Non-blocking RC/otonom streaming komutu

# --- UART SETUP (GPIO UART — orijinal bağlantı) ---
# Artık tek çekirdek kullanıyoruz, lock'a gerek yok.
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

# --- OBSTACLE DETECTION THRESHOLDS ---
OBSTACLE_THRESHOLDS_CM = {
    "front"       : 20.0,
    "front_left"  : 15.0,
    "front_right" : 15.0,
    "rear"        : 10.0,
    "left"        :  8.0,
    "right"       :  8.0,
}

SENSOR_ID_MAP = {
    "front"       : 0,
    "front_left"  : 1,
    "front_right" : 2,
    "rear"        : 3,
    "left"        : 4,
    "right"       : 5,
}

# --- STREAMING WATCHDOG ---
# RC veya otonom yaklaşma sırasında Pi'den 500ms veri gelmezse motorları durdur.
_STREAM_WATCHDOG_MS = 500
_last_stream_ms     = time.ticks_ms()
_stream_started     = False   # İlk MSG_STREAM gelince True olur


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
    """Send a packet over UART (single-core, no lock needed)."""
    packet = _build_packet(msg_type, payload)
    uart.write(packet)


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

def _handle_heartbeat(payload: bytes):
    _send(MSG_HEARTBEAT)


def _handle_pose(payload: bytes):
    """
    Blocking move komutu — enkoder ile belirli mesafe kat.
    Payload: 3 × float32 = x (m), z (m), speed (0.0–1.0).
    """
    if len(payload) != 12:
        _send_nack()
        return
    x, z, speed = struct.unpack('fff', payload)
    print(f"[UART] Pose: x={x:.3f} z={z:.3f} speed={speed:.2f}")

    def _obstacle_check(completed_cm: float):
        d = get_distances()
        for key, threshold in OBSTACLE_THRESHOLDS_CM.items():
            val = d.get(key)
            if val is not None and val < threshold:
                sensor_id    = SENSOR_ID_MAP[key]
                range_mm     = int(val * 10)
                completed_mm = int(completed_cm * 10)
                return (sensor_id, range_mm, completed_mm)
        return None

    # Pi send_path/send_move → önce ACK, sonra DONE (veya OBSTACLE) bekler
    _send_ack()

    result = move(x=x, z=z, speed=speed, obstacle_check=_obstacle_check)

    if result is None:
        _send(MSG_DONE)      # pi/uart.py send_move() ve send_path() bunu bekliyor
    else:
        sensor_id, range_mm, completed_mm = result
        obs_payload = struct.pack('BHH', sensor_id, range_mm, completed_mm)
        _send(MSG_OBSTACLE, obs_payload)


def _handle_stream(payload: bytes):
    """
    Non-blocking streaming komutu — RC ve otonom yaklaşma için.
    Pi her kamera karesinde gönderir, ACK beklemez.
    Payload: 3 × float32 = x (m), z (m), speed (0.0–1.0).
    Engel tespiti Pi tarafındaki FSM (poll_sensors) tarafından yapılır.
    """
    global _last_stream_ms, _stream_started
    if len(payload) != 12:
        return
    x, z, speed = struct.unpack('fff', payload)

    # --- YENİ EKLENEN: DONANIMSAL ACİL FREN ---
    # Araç ileri gitmeye çalışıyorsa ve hızı 0'dan büyükse donanım sensörünü direkt kontrol et
    if z > 0 and speed > 0:
        d = get_distances()
        front_dist = d.get("front")
        # Önünde 15 cm'den yakın engel varsa, Pi'den gelen komutu ezip hızı donanımsal olarak sıfırla
        if front_dist is not None and front_dist < 15.0:
            speed = 0.0
            z = 0.0
            print("[UART] HARDWARE AUTO-BRAKE TRIGGERED!")

    _last_stream_ms = time.ticks_ms()
    _stream_started = True
    stream(x, z, speed)


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


# Handler registry: msg_type → function
HANDLERS = {
    MSG_HEARTBEAT   : _handle_heartbeat,
    MSG_POSE        : _handle_pose,
    MSG_MARKER_LOST : _handle_marker_lost,
    MSG_ID          : _handle_id,
    MSG_QUERY       : _handle_query,
    MSG_STOP        : _handle_stop,
    MSG_STREAM      : _handle_stream,
}


# --- SENSOR DATA SENDER ---
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
    global _stream_started
    print("[UART] Pico UART listener started.")
    buffer = b''

    # Sensör gönderim zamanlayıcısı (eski Core 1'in yaptığı iş)
    SENSOR_SEND_INTERVAL_MS = 200
    last_sensor_send = time.ticks_ms()

    while True:
        now = time.ticks_ms()

        # --- SENSÖR VERİSİ GÖNDERİMİ ---
        # Eskiden Core 1'de yapılıyordu — artık tek döngüde, çakışma yok.
        if time.ticks_diff(now, last_sensor_send) >= SENSOR_SEND_INTERVAL_MS:
            send_sensor_data()
            last_sensor_send = now

        # --- WATCHDOG ---
        # Streaming modundayken 500ms veri gelmezse motorları durdur.
        if _stream_started:
            if time.ticks_diff(now, _last_stream_ms) > _STREAM_WATCHDOG_MS:
                stop()
                _stream_started = False

        # --- VERİ OKU VE İŞLE ---
        if uart.any():
            data = uart.read()
            if data:  # Veri gerçekten geldiyse buffer'a ekle
                buffer += data

            # --- PAKET İŞLE ---
            while True:
                idx = buffer.find(MSG_MARKER)
                if idx == -1:
                    # EĞER paketin yarısı geldiyse (Sadece 0xAA varsa) silme, sakla!
                    if buffer.endswith(b'\xAA'):
                        buffer = b'\xAA'
                    else:
                        buffer = b''
                    break

                buffer = buffer[idx:]

                if len(buffer) < 4:
                    break

                msg_type    = buffer[2]
                payload_len = _expected_payload_len(msg_type)

                if payload_len is None:
                    buffer = buffer[2:]
                    continue

                packet_len = 2 + 1 + payload_len + 1
                if len(buffer) < packet_len:
                    break

                packet = buffer[:packet_len]
                buffer = buffer[packet_len:]

                _, payload = _parse_packet(packet)
                if payload is None:
                    continue

                handler = HANDLERS.get(msg_type)
                if handler:
                    handler(payload)
                else:
                    _send_nack()

        # Döngüyü çok az uyutarak CPU'yu rahatlat
        time.sleep_ms(5)


def _expected_payload_len(msg_type: int):
    PAYLOAD_LENGTHS = {
        MSG_HEARTBEAT   : 0,
        MSG_POSE        : 12,
        MSG_MARKER_LOST : 0,
        MSG_ACK         : 0,
        MSG_NACK        : 0,
        MSG_ID          : 1,
        MSG_SENSOR_DATA : 24,
        MSG_OBSTACLE    : 5,
        MSG_QUERY       : 0,
        MSG_STOP        : 0,
        MSG_DONE        : 0,
        MSG_STREAM      : 12,
    }
    return PAYLOAD_LENGTHS.get(msg_type, None)
