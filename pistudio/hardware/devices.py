"""The hardware the studio can deliver through, named once.

Every device's display name, emoji and one-line description lived as literals
scattered across ~20 call sites: the scan tables in ``hw/command.py``, the
``subcommands`` dict, the alias tuples in its dispatch, and each device's own
handler.  They had already drifted -- the ``hw`` help listing showed no emoji
at all, and one device's was written without the ``U+FE0F`` variation
selector, so it rendered as monochrome text rather than the colour glyph on
most terminals.

Declaring each device once means the emoji appears everywhere the device does,
and adding hardware is one entry rather than an archaeology exercise.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEVICES", "Device", "device_by_name", "emoji_for", "label_for"]


@dataclass(frozen=True, slots=True)
class Device:
    """One piece of red-team hardware.

    Attributes:
        name: The ``hw`` subcommand, e.g. ``"flipper"``.
        label: Human name, e.g. ``"Flipper Zero"``.
        emoji: Shown wherever the device is named.  Emoji with a text
            presentation default carry ``U+FE0F`` explicitly, so terminals
            render the colour glyph rather than a monochrome symbol.
        help: One line, for the ``hw`` subcommand listing.
        aliases: Alternative subcommand spellings, including the emoji itself.
    """

    name: str
    label: str
    emoji: str
    help: str
    aliases: tuple[str, ...] = ()

    @property
    def titled(self) -> str:
        """``"🐬 Flipper Zero"`` -- the label as it should always be shown."""
        return f"{self.emoji} {self.label}"


#: Declared in the order the ``hw`` help lists them.
DEVICES: tuple[Device, ...] = (
    Device(
        name="bunny",
        label="Bash Bunny",
        emoji="🐰",
        help="Bash Bunny — USB HID + mass storage",
        aliases=("🐰",),
    ),
    Device(
        name="ducky",
        label="Rubber Ducky",
        emoji="🦆",
        help="USB Rubber Ducky — USB HID",
        aliases=("🦆",),
    ),
    Device(
        name="flipper",
        label="Flipper Zero",
        emoji="🐬",
        help="Flipper Zero — BadUSB, NFC, BLE",
        aliases=("🐬",),
    ),
    Device(
        name="ubertooth",
        label="Ubertooth One",
        emoji="📡",
        help="Ubertooth One — BLE sniffing and advertising",
        aliases=("ut", "📡"),
    ),
    # The one entry that is not a named product.  A USB-TTL cable is whatever
    # bridge chip happens to be in it, and the interesting part is the target
    # on the far end, which the studio knows nothing about.
    Device(
        name="uart",
        label="USB-TTL serial",
        emoji="🔌",
        help="Serial console — deliver a payload over TX/RX",
        aliases=("serial", "tty", "🔌"),
    ),
)

_BY_ANY = {alias: d for d in DEVICES for alias in (d.name, *d.aliases)}


def device_by_name(name: str) -> Device | None:
    """Resolve a device by its subcommand name, alias, or emoji."""
    return _BY_ANY.get(name.lower() if name.isascii() else name)


def emoji_for(name: str) -> str:
    """The emoji for *name*, or an empty string when it is not a device.

    Never raises: this is called from display code, where an unknown name
    should degrade to no emoji rather than break the line being printed.
    """
    device = device_by_name(name)
    return device.emoji if device else ""


def label_for(name: str) -> str:
    """``"🐬 Flipper Zero"`` for a device, or *name* unchanged."""
    device = device_by_name(name)
    return device.titled if device else name
