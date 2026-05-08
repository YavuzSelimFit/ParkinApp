# pi/ble_server.py — BLE GATT Server for receiving park commands from mobile app.
#
# Mobile app sends: "PARK:<id>"  (e.g. "PARK:2")
# This server parses the ID and calls the registered callback.
#
# Usage:
#   ble = BLEServer(on_park_command=lambda target_id: fsm.set_target(target_id) or fsm.start())
#   ble.start()   # non-blocking — runs in background thread
#   ble.stop()

import threading
import logging

log = logging.getLogger(__name__)

# BLE UUIDs — must match Flutter HardwareCommunicationService
SERVICE_UUID  = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID     = "0000ffe1-0000-1000-8000-00805f9b34fb"


class BLEServer:
    """
    Wraps a BlueZ/dbus GATT peripheral so the mobile app can write
    "PARK:<marker_id>" to trigger autonomous parking.

    Falls back to a simple RFCOMM socket approach if bluezero is not
    available, keeping the same string protocol.
    """

    def __init__(self, on_park_command=None, on_stop_command=None):
        """
        Parameters
        ----------
        on_park_command : callable(int) or None
            Called with the parsed integer marker ID when "PARK:<id>" arrives.
        on_stop_command : callable() or None
            Called when "STOP" arrives.
        """
        self._on_park  = on_park_command
        self._on_stop  = on_stop_command
        self._thread   = None
        self._running  = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start BLE server in a background daemon thread."""
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[BLE] Server starting in background…")

    def stop(self):
        """Signal the BLE server to stop."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal — command dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, raw: str):
        """Parse and dispatch an incoming command string."""
        raw = raw.strip()
        print(f"[BLE] Received: '{raw}'")

        if raw.startswith("PARK:"):
            try:
                target_id = int(raw.split(":", 1)[1])
                print(f"[BLE] Park command → target_id={target_id}")
                if self._on_park:
                    self._on_park(target_id)
            except ValueError:
                print(f"[BLE] Bad PARK payload: '{raw}'")

        elif raw == "STOP":
            print("[BLE] Stop command received.")
            if self._on_stop:
                self._on_stop()

        else:
            print(f"[BLE] Unknown command: '{raw}'")

    # ------------------------------------------------------------------
    # Internal — backend selection
    # ------------------------------------------------------------------

    def _run(self):
        """Try bluezero first, fall back to RFCOMM socket."""
        try:
            self._run_bluezero()
        except ImportError:
            print("[BLE] bluezero not found — falling back to RFCOMM socket.")
            try:
                self._run_rfcomm()
            except Exception as e:
                print(f"[BLE] RFCOMM server error: {e}")
                print("[BLE] Install bluezero:  sudo pip install bluezero")
        except Exception as e:
            print(f"[BLE] bluezero error: {e}")

    # ------------------------------------------------------------------
    # Backend A: bluezero GATT peripheral
    # ------------------------------------------------------------------

    def _run_bluezero(self):
        """GATT peripheral using bluezero. Requires: sudo pip install bluezero"""
        from bluezero import peripheral

        p = peripheral.Peripheral(
            adapter_address=None,   # use default adapter
            local_name="wattsnext",
        )

        p.add_service(srv_id=1, uuid=SERVICE_UUID, primary=True)

        p.add_characteristic(
            srv_id=1,
            chr_id=1,
            uuid=CHAR_UUID,
            value=[],
            notifying=False,
            flags=["write", "write-without-response", "notify"],
            read_callback=None,
            write_callback=self._on_write_bluezero,
            notify_callback=None,
        )

        p.add_descriptor(
            srv_id=1, chr_id=1, dsc_id=1,
            uuid="2902",
            value=[0x00, 0x00],
            flags=["read", "write"],
        )

        print("[BLE] GATT peripheral ready — waiting for mobile app…")
        p.publish()     # blocks until stop() or Ctrl+C

    def _on_write_bluezero(self, value, options):
        """Called by bluezero when the characteristic is written."""
        text = bytes(value).decode("utf-8", errors="ignore")
        self._dispatch(text)

    # ------------------------------------------------------------------
    # Backend B: RFCOMM socket (fallback, no BLE but simpler to set up)
    # ------------------------------------------------------------------

    def _run_rfcomm(self):
        """
        Classic Bluetooth SPP / RFCOMM socket server (fallback).
        Works with apps that use a serial Bluetooth plugin.
        NOT used if bluezero is available.
        """
        import bluetooth  # PyBluez

        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_sock.bind(("", bluetooth.PORT_ANY))
        server_sock.listen(1)

        port = server_sock.getsockname()[1]
        bluetooth.advertise_service(
            server_sock, "ParkingApp",
            service_id="94f39d29-7d6d-437d-973b-fba39e49d4ee",
            service_classes=["94f39d29-7d6d-437d-973b-fba39e49d4ee",
                             bluetooth.SERIAL_PORT_CLASS],
            profiles=[bluetooth.SERIAL_PORT_PROFILE],
        )

        print(f"[BLE] RFCOMM server listening on port {port}…")

        while self._running:
            try:
                server_sock.settimeout(1.0)
                client_sock, client_info = server_sock.accept()
                print(f"[BLE] RFCOMM client connected: {client_info}")
                self._handle_rfcomm_client(client_sock)
            except bluetooth.BluetoothError:
                continue

        server_sock.close()

    def _handle_rfcomm_client(self, sock):
        buf = ""
        while self._running:
            try:
                data = sock.recv(64)
                if not data:
                    break
                buf += data.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    self._dispatch(line)
            except Exception:
                break
        sock.close()
        print("[BLE] RFCOMM client disconnected.")
