"""Flipper Zero BadUSB (HID injection) support.

The Flipper Zero supports DuckyScript payloads via its BadUSB app.
Payloads are .txt files stored in /badusb/ on the SD card.

This uses the same DuckyScript format as the USB Rubber Ducky.
"""

from pistudio.hardware.hak5.compiler_ducky import type_text
from pistudio.hardware.payloads import Payload


def compile_payload(
    payload: Payload,
    *,
    start_delay: int = 1000,
    preamble: str = "",
) -> str:
    """Compile a single payload to DuckyScript for Flipper Zero BadUSB.

    Args:
        payload: The payload to compile.
        start_delay: Milliseconds to wait before first keystroke.
        preamble: Optional DuckyScript lines to prepend (e.g. ``GUI r``).
    """
    lines: list[str] = []
    lines.append(f"REM Prompt Injection Studio — Flipper Zero BadUSB payload: {payload.name}")
    if payload.description:
        lines.append(f"REM {payload.description}")
    lines.append("")

    if preamble:
        lines.append(preamble.rstrip())
        lines.append("")

    lines.append(f"DELAY {start_delay}")

    lines.extend(type_text(payload.text))

    return "\n".join(lines) + "\n"
