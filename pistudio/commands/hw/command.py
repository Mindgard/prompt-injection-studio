"""HwCommand — unified hardware command for red team hardware integration."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pistudio.core.command import Command
from pistudio.hardware.devices import DEVICES, device_by_name, emoji_for
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)


def _resolve_llm(shell: StudioProtocol):
    """Resolve the LLM for payload generation.

    Returns:
        ``(provider, api_key, base_url)``, or ``None`` when unconfigured.
    """
    from pistudio.core.llm import resolve_model

    return resolve_model()


class HwCommand(Command):
    """Red team hardware integration — USB HID, NFC, Bluetooth, RF injection"""

    name = "hw"
    aliases = ("hardware",)
    help = "Red team hardware — USB HID, NFC, Bluetooth, RF prompt injection"
    file_args = ("--output", "--path")
    namespace = True
    # Derived from the device registry, so a device's emoji, name and one-line
    # help are declared once and appear everywhere it does.
    subcommand_aliases = {
        "file": "files",
        **{alias: d.name for d in DEVICES for alias in d.aliases},
    }
    subcommands = {
        "devices": "Scan for connected and reachable hardware",
        **{d.name: f"{d.emoji}  {d.help}" for d in DEVICES},
        "files": "Register files for Bash Bunny delivery",
    }
    usage = (
        "Usage: hw <subcommand> [args]\n\n"
        "Red team hardware integration for prompt injection delivery via USB HID,\n"
        "NFC/RFID, and Bluetooth.\n\n"
        "Device Commands:\n"
        + "".join(f"  hw {d.name:<11} {d.emoji}  {d.help}\n" for d in DEVICES)
        + "\nShared Resources:\n"
        "  hw devices        Scan for all connected hardware devices\n"
        "  hw files ...      Register files for Bash Bunny delivery\n\n"
        "The payloads these commands deploy are managed by 'payloads' at the\n"
        "top level, not under hw.\n\n"
        "Examples:\n"
        "  hw devices\n"
        "  hw bunny deploy system-prompt-leak --switch 1\n"
        "  hw ducky compile ignore-instructions\n"
        "  hw flipper deploy-all role-override\n"
        "  hw uart send ignore-instructions --port /dev/tty.usbserial-0001\n"
        "  hw ubertooth ble-adv ignore-instructions --dry-run\n\n"
        "Only use this against systems you own or have written permission to test.\n\n"
        "Use 'hw <device> --help' for device-specific commands.\n"
        "See docs/hak5.md and docs/flipper.md for full guides.\n"
    )

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``hw`` command."""
        if not args:
            shell.out.info(self.usage)
            return

        raw = args[0]
        sub = raw.lower() if raw.isascii() else raw
        remaining = args[1:]

        # Resolve aliases and emoji through the registry, so `hw 🐬 devices`
        # and `hw sq status` reach the same handler as their long names.
        device = device_by_name(sub)
        if device is not None:
            self._dispatch_device(device.name, shell, remaining)
            return

        if sub == "devices":
            self._devices(shell)
        elif sub in ("payloads", "payload"):
            shell.out.error(
                f"The library moved out of hw. Use: payloads {' '.join(remaining) or '<subcommand>'}".rstrip()
            )
        elif sub in ("files", "file"):
            from pistudio.commands.hw.files import handle_files

            handle_files(self, shell, remaining)
        else:
            shell.out.error(self.suggest_subcommand(sub, ["devices", "files", *(d.name for d in DEVICES)]))

    def _dispatch_device(self, name: str, shell: StudioProtocol, args: list[str]) -> None:
        """Route to the handler for device *name*, imported lazily."""
        if name in ("bunny", "ducky"):
            from pistudio.commands.hw.hak5 import handle_hak5

            handle_hak5(self, shell, name, args)
        elif name == "flipper":
            from pistudio.commands.hw.flipper import handle_flipper

            handle_flipper(self, shell, args)
        elif name == "ubertooth":
            from pistudio.commands.hw.ubertooth import handle_ubertooth

            handle_ubertooth(self, shell, args)
        elif name == "uart":
            from pistudio.commands.hw.uart import handle_uart

            handle_uart(self, shell, args)

    # ── Device scanning ─────────────────────────────────────────────

    def _devices(self, shell: StudioProtocol) -> None:
        """Scan for all connected hardware devices."""
        devices = self._scan_devices()

        if shell.json_mode:
            shell.print_raw(json.dumps(devices, indent=2))
            return

        t = active_theme()
        for device in devices:
            via = " (serial)" if device["transport"] == "serial" else ""
            detail = f" [{t.accent}]fw:{device['firmware']}[/]" if device.get("firmware") else ""
            shell.console.print(
                f"  [{t.success}]{device['icon']}[/] {device['label']} at [{t.accent}]{device['at']}[/]{via}{detail}"
            )

        if not devices:
            shell.console.print(f"  [{t.muted}]No hardware devices found.[/]")
            shell.console.print(
                f"  [{t.muted}]Connect a device over USB. A Flipper in mass-storage mode "
                f"appears as a volume; plugged in normally it is a serial port.[/]"
            )

    def _scan_devices(self) -> list[dict]:
        """Find every attached device, newest probe last.

        Discovery is kept separate from rendering so the same scan can be
        printed for a human or serialised for ``--json``; the previous version
        printed as it probed, which left no structured result to return.
        """
        from pistudio.hardware.flipper.device import find_flipper_volumes
        from pistudio.hardware.hak5.device import find_bunny_volumes, find_ducky_volumes

        devices: list[dict] = []

        for name, volumes in (
            ("bunny", find_bunny_volumes()),
            ("ducky", find_ducky_volumes()),
            ("flipper", find_flipper_volumes()),
        ):
            device = device_by_name(name)
            assert device is not None  # a name from the registry, by construction
            label, icon = device.label, device.emoji
            for vol in volumes:
                devices.append({"device": label, "label": label, "icon": icon, "at": vol, "transport": "volume"})

        flipper_as_volume = any(d["device"] == "Flipper Zero" for d in devices)
        devices.extend(self._probe_ubertooth())
        # A USB device only appears as a volume in mass-storage mode.  Plugged
        # in normally it presents a serial port, so scan for those too or a
        # connected Flipper looks absent.
        devices.extend(self._scan_serial_devices(skip_flipper=flipper_as_volume))
        # Hardware that attaches over the network rather than as a USB volume
        # needs its own probe; see _NETWORK_PROBES.  Probes are passive TCP
        # checks — no credentials required.
        devices.extend(self._scan_network_devices())
        return devices

    @staticmethod
    def _probe_ubertooth() -> list[dict]:
        """The Ubertooth, if its USB library is installed and a dongle is present."""
        try:
            from pistudio.hardware.ubertooth.device import find_ubertooth

            found = find_ubertooth()
        except Exception:
            logger.debug("Ubertooth probe failed", exc_info=True)
            return []
        if not found:
            return []
        return [
            {
                "device": "Ubertooth One",
                "label": "Ubertooth One",
                "icon": "U",
                "at": "usb",
                "transport": "usb",
                "firmware": found["firmware_version"],
            }
        ]

    @staticmethod
    def _scan_serial_devices(skip_flipper: bool = False) -> list[dict]:
        """USB devices attached as serial ports rather than mass storage.

        Args:
            skip_flipper: Set when a Flipper was already found as a volume, so
                the same device is not reported twice.
        """
        from pistudio.hardware.flipper.serial_console import find_flipper_serial_ports
        from pistudio.hardware.hak5.serial_console import find_bunny_serial_ports

        found: list[dict] = []
        probes = [("Bash Bunny", emoji_for("bunny"), find_bunny_serial_ports)]
        if not skip_flipper:
            probes.insert(0, ("Flipper Zero", emoji_for("flipper"), find_flipper_serial_ports))

        for label, icon, probe in probes:
            try:
                ports = probe()
            except Exception:
                logger.debug("%s serial scan failed", label, exc_info=True)
                continue
            for port in ports:
                found.append({"device": label, "label": label, "icon": icon, "at": port, "transport": "serial"})
        return found

    #: Network-attached devices to probe, as ``(device name, probe, address
    #: attribute)``.  A probe takes no arguments and returns either ``None`` or
    #: an object carrying the device's address on the named attribute.  Every
    #: device the studio currently ships attaches over USB, so this is empty;
    #: it is the registration point for one that does not.
    _NETWORK_PROBES: tuple = ()

    @classmethod
    def _scan_network_devices(cls) -> list[dict]:
        """Network-attached devices, found by a passive TCP probe.

        Kept device-agnostic so a probe that fails -- unreachable host, no
        route, firewall drop -- is logged and skipped rather than failing the
        whole scan.
        """
        found: list[dict] = []
        for name, probe, attr in cls._NETWORK_PROBES:
            device_meta = device_by_name(name)
            label, icon = (device_meta.label, device_meta.emoji) if device_meta else (name, "")
            try:
                device = probe()
            except Exception:
                logger.debug("%s probe failed", label, exc_info=True)
                continue
            if device:
                found.append(
                    {
                        "device": label,
                        "label": label,
                        "icon": icon,
                        "at": getattr(device, attr),
                        "transport": "network",
                    }
                )
        return found

    # ── Tab completion ──────────────────────────────────────────────

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Return tab-completion candidates for ``hw``."""

        top_subs = [
            "devices",
            "files",
            # From the registry, so adding a device does not need this list
            # edited too -- which is how `uart` came to be declared but not
            # completable.
            *(d.name for d in DEVICES),
        ]
        if not tokens:
            return top_subs

        first = tokens[0].lower()

        if len(tokens) == 1:
            return [s for s in top_subs if s.startswith(first)]

        if first in ("files", "file"):
            from pistudio.commands.hw.files import complete_files

            return complete_files(tokens[1:], shell.session_dir)

        if first in ("bunny", "🐰", "ducky", "🦆"):
            from pistudio.commands.hw.hak5 import complete_hak5

            device = "bunny" if first in ("bunny", "🐰") else "ducky"
            return complete_hak5(device, tokens[1:], shell.session_dir)

        if first in ("flipper", "🐬"):
            from pistudio.commands.hw.flipper import complete_flipper

            return complete_flipper(shell, tokens[1:])

        if first in ("ubertooth", "ut"):
            from pistudio.commands.hw.ubertooth import complete_ubertooth

            return complete_ubertooth(shell, tokens[1:])

        if first in ("uart", "serial", "tty"):
            from pistudio.commands.hw.uart import complete_uart

            return complete_uart(shell, tokens[1:])

        return []

    def wants_path_completion(self, tokens: list[str]) -> bool:
        """Return True when the cursor is at a file path position."""
        if not tokens:
            return False

        return tokens[-1] in ("--path", "--output")
