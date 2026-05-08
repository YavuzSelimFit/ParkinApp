# pi/ble_server.py — BLE GATT sunucusu
#
# Flutter uygulamasının bağlandığı UUID'lerle eşleşen bir GATT sunucusu sağlar.
# Gelen komutları bir Queue'ya ekler; main.py bu kuyruğu okur.
# Uygulamaya bildirim göndermek için send_notification() kullanılır.
#
# Kurulum (Raspberry Pi):
#   pip install bless
#
# UUID'ler Flutter koduyla (hardware_communication_service.dart) birebir eşleşiyor:
#   Service  : 0000ffe0-0000-1000-8000-00805f9b34fb
#   Char     : 0000ffe1-0000-1000-8000-00805f9b34fb

import asyncio
import threading
import queue
import logging
from typing import Any, Union

from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions,
)

logger = logging.getLogger(__name__)

SERVICE_UUID  = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID     = "0000ffe1-0000-1000-8000-00805f9b34fb"

# ─── BLEServer ──────────────────────────────────────────────────────────────

class BLEServer:
    """
    Arka planda asyncio döngüsü üzerinde çalışan BLE GATT sunucusu.
    Ana iş parçacığından şu metodlarla kullanılır:
        get_command() → str | None   (gelen komutu döner, yoksa None)
        send_notification(text: str) → None  (uygulamaya bildirim gönderir)
        shutdown() → None
    """

    def __init__(self, device_name: str = "ParkingCar_V1"):
        self._device_name   = device_name
        self._cmd_queue: queue.Queue[str] = queue.Queue()
        self._server: BlessServer | None  = None
        self._char:   BlessGATTCharacteristic | None = None
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready   = threading.Event()

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self):
        """BLE sunucusunu bir arka plan thread'inde başlatır."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=15):
            raise RuntimeError("[BLE] Sunucu 15 saniye içinde başlatılamadı.")
        print(f"[BLE] '{self._device_name}' olarak yayın yapılıyor.")

    def get_command(self) -> str | None:
        """
        Kuyruktan bir komutu çeker ve döndürür.
        Kuyruk boşsa None döner (non-blocking).
        """
        try:
            return self._cmd_queue.get_nowait()
        except queue.Empty:
            return None

    def send_notification(self, text: str):
        """
        Bağlı Flutter uygulamasına UTF-8 metin bildirimi gönderir.
        Bağlı istemci yoksa sessizce yok sayılır.
        """
        if self._server is None or self._char is None:
            return
        data = text.encode("utf-8")
        # Karakteristiğin değerini güncelle ve bildirim gönder
        asyncio.run_coroutine_threadsafe(
            self._notify(data), self._loop
        )

    def shutdown(self):
        """BLE sunucusunu durdurur."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        print("[BLE] Sunucu durduruldu.")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_main())

    async def _async_main(self):
        trigger = asyncio.Event()

        self._server = BlessServer(
            name=self._device_name,
            loop=self._loop,
        )
        self._server.read_request_func  = self._on_read
        self._server.write_request_func = self._on_write

        # Servis ve karakteristik tanımla
        await self._server.add_new_service(SERVICE_UUID)
        await self._server.add_new_characteristic(
            SERVICE_UUID,
            CHAR_UUID,
            GATTCharacteristicProperties.read
            | GATTCharacteristicProperties.write
            | GATTCharacteristicProperties.notify,
            None,
            GATTAttributePermissions.readable | GATTAttributePermissions.writeable,
        )
        self._char = self._server.get_characteristic(CHAR_UUID)

        await self._server.start()
        self._ready.set()

        # Sunucu döngüsünü sonsuza kadar çalıştır
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass

        await self._server.stop()

    def _on_read(
        self,
        characteristic: BlessGATTCharacteristic,
        **kwargs: Any,
    ) -> bytearray:
        """Uygulama karakteristiği okuduğunda çağrılır (opsiyonel)."""
        return characteristic.value or bytearray()

    def _on_write(
        self,
        characteristic: BlessGATTCharacteristic,
        value: Any,
        **kwargs: Any,
    ):
        """Uygulama karakteristiğe yazdığında çağrılır."""
        text = bytes(value).decode("utf-8", errors="ignore").strip()
        if text:
            print(f"[BLE] Gelen komut: '{text}'")
            self._cmd_queue.put(text)

    async def _notify(self, data: bytes):
        """Characteristic değerini günceller ve NOTIFY gönderir."""
        if self._char is None or self._server is None:
            return
        self._char.value = bytearray(data)
        await self._server.update_value(SERVICE_UUID, CHAR_UUID)
