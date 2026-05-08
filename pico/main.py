import _thread
import time
import sensors
import uart

SENSOR_SEND_INTERVAL_MS = 200   # how often to send sensor data to Pi

def sensor_loop():
    """Runs on Core 1 — starts sensors and sends readings to Pi periodically."""
    sensors.start()
    time.sleep_ms(500)          # allow first readings to populate

    last_send = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_send) >= SENSOR_SEND_INTERVAL_MS:
            uart.send_sensor_data()
            last_send = now
        time.sleep_ms(10)

# --- START ---
_thread.start_new_thread(sensor_loop, ())  # Core 1: sensors + sending
uart.run()                                  # Core 0: incoming UART + move