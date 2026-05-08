# pi/main.py — BLE entegreli otonom ve RC sürüş kontrol merkezi
#
# OTONOM MOD:
#   Flutter uygulaması "PARK:2" formatında bir mesaj gönderir.
#   → FSM hedef ArUco ID'sini 2 olarak ayarlar ve SEARCHING durumuna geçer.
#   → Araç markeri bulur, parkeder ve "STATUS:ARRIVED" bilgisini BLE ile geri gönderir.
#
# RC (UZAKTAN KUMANDA) MODu:
#   Flutter joystick'i "RC:X:Y" formatında sürekli mesaj gönderir.
#   X ve Y, -100 ile +100 arasında normalize edilmiş joystick değerleridir.
#   → FSM IDLE'a alınır (otonom sürüş iptal edilir).
#   → X/100.0 ve Y/100.0 değerleri uart.send_stream() ile Pico'ya aktarılır.
#   → Kullanıcı joystick'i bırakınca (RC:0:0) araç durur.
#
# ACİL DURDURMA:
#   Flutter "STOP" mesajı gönderir.
#   → FSM IDLE'a alınır, motorlar durdurulur.
#
# BLE Protokol Özeti (Flutter ↔ Pi):
#   Uygulama → Pi : "PARK:<id>"   Otonom park başlat (örn: "PARK:2")
#   Uygulama → Pi : "RC:<x>:<y>"  Joystick komutu   (örn: "RC:50:-30")
#   Uygulama → Pi : "STOP"        Acil durdur
#   Pi → Uygulama : "STATUS:ARRIVED"   Park tamamlandı bildirimi
#
# Bağımlılıklar (Raspberry Pi):
#   pip install bless

import sys
import time
import traceback
import math

from aruco import ArucoDetector
from uart  import UARTController
from fsm   import FSM, IDLE, SEARCHING, APPROACHING, BYPASSING, ARRIVED
from ble_server import BLEServer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UART_PORT  = '/dev/ttyAMA0'
UART_BAUD  = 115200

# RC mod sabit hızı (0.0 – 1.0 arası).
# Joystick'in ne kadar itildiğine göre oranlanır.
RC_MAX_SPEED = 0.40

# RC deadzone — bu değerin altındaki joystick girdileri yok sayılır.
RC_DEADZONE  = 10   # (−100..100 skalasında)

# ---------------------------------------------------------------------------
# RC komut işleyici
# ---------------------------------------------------------------------------

def _parse_rc(cmd: str):
    """
    "RC:X:Y" formatındaki string'i parse eder.
    Döner: (uart_x, uart_z, speed) veya None (geçersiz format).

    Joystick eksenleri:
        X  (−100..100): negatif = sola,  pozitif = sağa
        Y  (−100..100): negatif = geri,  pozitif = ileri

    UART send_stream parametreleri:
        x     (−1.0..1.0): yanal sapma (sağ pozitif)
        z     (−1.0..1.0): ileri/geri  (ileri pozitif)
        speed (0.0..1.0 ): normalize hız

    Hız hesabı:
        Joystick'in ne kadar itildiğini (magnitude) kullan,
        ama yönü x/z bileşenlerinde tut.
        Bu sayede tam itişte RC_MAX_SPEED, hafif itişte daha yavaş gider.
    """
    parts = cmd.split(":")
    if len(parts) != 3:
        return None
    try:
        jx = float(parts[1])   # sağ pozitif
        jy = float(parts[2])   # ileri pozitif
    except ValueError:
        return None

    # Deadzone uygula
    if abs(jx) < RC_DEADZONE:
        jx = 0.0
    if abs(jy) < RC_DEADZONE:
        jy = 0.0

    if jx == 0.0 and jy == 0.0:
        return (0.0, 0.0, 0.0)   # dur komutu

    # -100..100 → -1.0..1.0 normalize et
    nx = max(-1.0, min(1.0, jx / 100.0))
    ny = max(-1.0, min(1.0, jy / 100.0))

    # Joystick'in toplam itiş büyüklüğünü hız olarak kullan.
    magnitude = math.sqrt(nx * nx + ny * ny) / math.sqrt(2)  # normalise to 0-1
    speed = max(0.0, min(1.0, magnitude * RC_MAX_SPEED))

    # Yön bileşenlerini normalize et (birim vektör × hız yerine saf yön).
    # send_stream x ve z'yi yön olarak kullanır; hız ayrı parametre.
    return (nx, ny, speed)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

print("[MAIN] Başlatılıyor...")

detector = ArucoDetector()
uart     = UARTController(port=UART_PORT, baud=UART_BAUD)

print("[MAIN] Pico bağlantısı kontrol ediliyor...")
if not uart.heartbeat():
    print("[MAIN] HATA: Pico'dan heartbeat yok — bağlantıyı kontrol edin.")
    detector.stop()
    sys.exit(1)
print("[MAIN] Pico hazır.\n")

# BLE sunucusu
ble = BLEServer(device_name="ParkingCar_V1")
ble.start()

# FSM — park tamamlanınca BLE'ye bildir
def _on_arrived():
    print("[MAIN] Park tamamlandı — uygulama bilgilendiriliyor.")
    ble.send_notification("STATUS:ARRIVED")

fsm = FSM(detector, uart, on_arrived_callback=_on_arrived)

# ---------------------------------------------------------------------------
# Mod takibi
# ---------------------------------------------------------------------------

RC_MODE   = "RC"
AUTO_MODE = "AUTO"
current_mode = AUTO_MODE   # Başlangıçta otonom mod (IDLE'da bekler)

print("[MAIN] BLE üzerinden komut bekleniyor...")
print("       PARK:<id>    → Otonom park başlat")
print("       RC:<x>:<y>   → RC modu (joystick)")
print("       STOP         → Acil durdur\n")

# ---------------------------------------------------------------------------
# Ana döngü
# ---------------------------------------------------------------------------

try:
    while True:
        # ── BLE kuyruğunu kontrol et ────────────────────────────────────────
        cmd = ble.get_command()

        if cmd is not None:
            cmd_upper = cmd.strip().upper()

            # --- Acil Durdurma ---
            if cmd_upper == "STOP":
                print("[MAIN] STOP komutu alındı.")
                current_mode = AUTO_MODE
                fsm.force_state(IDLE)   # send_stop() zaten _on_enter(IDLE) içinde çağrılıyor

            # --- RC Modu (joystick) ---
            elif cmd_upper.startswith("RC:"):
                if current_mode != RC_MODE:
                    print("[MAIN] RC moduna geçildi — otonom sürüş duraklatıldı.")
                    current_mode = RC_MODE
                    fsm.force_state(IDLE)   # FSM'i dondur, motorları durdur

                parsed = _parse_rc(cmd_upper)
                if parsed is not None:
                    ux, uz, spd = parsed
                    if spd == 0.0:
                        uart.send_stop()
                    else:
                        uart.send_stream(ux, uz, spd)

            # --- Otonom Park Komutu ---
            elif cmd_upper.strip().isdigit():
                target_id = int(cmd_upper.strip())
                print(f"[MAIN] Otonom park komutu: ArUco ID={target_id}")
                current_mode = AUTO_MODE
                fsm.force_state(IDLE)   # Temiz başlangıç
                fsm.set_target(target_id)
                fsm.start()             # IDLE → SEARCHING

            elif cmd_upper.startswith("PARK:"):
                parts = cmd_upper.split(":")
                if len(parts) == 2 and parts[1].isdigit():
                    target_id = int(parts[1])
                    print(f"[MAIN] Otonom park komutu: ArUco ID={target_id}")
                    current_mode = AUTO_MODE
                    fsm.force_state(IDLE)   # Temiz başlangıç
                    fsm.set_target(target_id)
                    fsm.start()             # IDLE → SEARCHING
                else:
                    print(f"[MAIN] Geçersiz PARK komutu: '{cmd}'")

            else:
                print(f"[MAIN] Bilinmeyen komut: '{cmd}'")

        # ── FSM tick (sadece otonom modda) ─────────────────────────────────
        if current_mode == AUTO_MODE:
            try:
                fsm.tick()
            except Exception as e:
                print(f"[MAIN] FSM tick hatası — {e}")
                traceback.print_exc()

        # ── Döngü hızı ─────────────────────────────────────────────────────
        # RC modunda çok sık komutu işleme gerek yok;
        # FSM zaten her frame kamera okuyacak (doğal throttle).
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n[MAIN] Ctrl+C — durduruluyor.")

finally:
    print("[MAIN] Temizleniyor...")
    fsm.stop()
    detector.stop()
    ble.shutdown()
    print("[MAIN] Çıkış.")
