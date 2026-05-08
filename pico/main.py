import time
import sensors
import uart

# --- BAŞLANGIÇ GECİKMESİ ---
# Thonny / mpremote'un bağlanıp Ctrl+C gönderebilmesi için
time.sleep(3)

print("[MAIN] Sensörler başlatılıyor...")
sensors.start()
time.sleep_ms(500)  # İlk okumaların dolması için bekle

print("[MAIN] UART sistemi başlatılıyor...")
uart.run()
