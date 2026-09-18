"""Reactive BLE trigger -- sniff for targets, auto-broadcast on match."""

import logging
import re
import threading
import time

logger = logging.getLogger(__name__)


class ReactiveTrigger:
    """Monitor BLE traffic and broadcast PI when target detected.

    Runs a background thread that:
    1. Sniffs BLE advertisements for a short window
    2. Checks if any discovered device matches the watch criteria
    3. Broadcasts the PI payload via the system BLE adapter on match
    4. Enforces a cooldown between triggers
    """

    def __init__(
        self,
        watch_pattern: str | None = None,
        watch_oui: str | None = None,
        payload_adv_data: bytes = b"",
        payload_scan_rsp: bytes = b"",
        cooldown_secs: int = 30,
    ):
        try:
            self.watch_pattern = re.compile(watch_pattern) if watch_pattern else None
        except re.error as e:
            raise ValueError(f"Invalid watch pattern: {e}") from e
        self.watch_oui = watch_oui.upper() if watch_oui else None
        self.payload_adv = payload_adv_data
        self.payload_rsp = payload_scan_rsp
        self.cooldown_secs = cooldown_secs
        self._running = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_trigger: float = 0

    def matches(self, device: dict) -> bool:
        """Check if a discovered device matches the watch criteria."""
        if self.watch_oui and device.get("addr", "").upper().startswith(self.watch_oui):
            return True
        return bool(self.watch_pattern and self.watch_pattern.search(device.get("name", "")))

    def start(self) -> None:
        """Start the reactive trigger loop in a background thread."""
        with self._lock:
            self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Reactive trigger started")

    def stop(self) -> None:
        """Stop the reactive trigger loop."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Reactive trigger stopped")

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def _loop(self) -> None:
        """Main sniff-match-broadcast loop.

        Uses ubertooth-btle WITHOUT the -r flag so output goes to stdout
        (not a PCAP file), which we can parse for AdvA addresses.
        """
        from pistudio.hardware.ubertooth.ble_advertise import advertise_hci
        from pistudio.hardware.ubertooth.ble_sniff import parse_sniff_output

        while self.running:
            # Sniff for 5 seconds using stdout mode (no -r flag)
            proc = None
            try:
                import subprocess

                proc = subprocess.Popen(
                    ["ubertooth-btle", "-f"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = proc.communicate(timeout=10)
            except FileNotFoundError:
                logger.warning("ubertooth-btle not found, stopping trigger")
                with self._lock:
                    self._running = False
                return
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                    stdout, _ = proc.communicate()
                else:
                    continue
            except Exception:
                if proc:
                    proc.kill()
                continue

            devices = parse_sniff_output(stdout.decode("utf-8", errors="replace"))
            for dev in devices:
                if not self.matches(dev):
                    continue
                now = time.monotonic()
                if now - self._last_trigger < self.cooldown_secs:
                    continue
                self._last_trigger = now
                logger.info(
                    "Target matched: %s (%s) -- broadcasting PI",
                    dev.get("addr"),
                    dev.get("name", ""),
                )
                try:
                    advertise_hci(self.payload_adv, self.payload_rsp, duration_secs=10)
                except Exception:
                    logger.warning("Broadcast failed", exc_info=True)

            time.sleep(1)
