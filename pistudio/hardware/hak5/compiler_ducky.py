"""DuckyScript v3 compiler — converts payloads to Rubber Ducky format.

Output is plain-text DuckyScript source (``STRING``, ``STRINGLN``, ``DELAY``,
etc.).  The user can flash it to a Rubber Ducky via the Hak5 encoder or paste
into the Hak5 web IDE.

Multi-line text uses ``STRINGLN`` per line, which types the line and presses
Enter.  ``STRING`` alone does not emit a newline, so emitting one ``STRING``
per line and a single trailing ``ENTER`` would type the lines concatenated.
"""

from pistudio.hardware.payloads import Payload as Hak5Payload


def type_text(text: str) -> list[str]:
    """Return DuckyScript lines that type *text* verbatim, newlines included.

    The final line is typed with ``STRINGLN`` too, so the payload ends with
    Enter — submitting it to whatever prompt has focus.
    """
    lines: list[str] = []
    for text_line in text.split("\n"):
        # STRINGLN with no argument emits an empty line, preserving blank
        # lines inside a payload.
        lines.append(f"STRINGLN {text_line}" if text_line else "STRINGLN")
    return lines


def _default_delay_lines(default_delay: int) -> list[str]:
    """Return the ``DEFAULTDELAY`` preamble, or nothing when unset.

    ``DEFAULTDELAY`` pauses between *every* subsequent command, which paces the
    typing itself.  That matters for browser chat UIs that drop keystrokes
    arriving faster than they re-render.

    Args:
        default_delay: Milliseconds between commands. 0 disables the directive.
    """
    if default_delay <= 0:
        return []
    return [
        "REM Pace every keystroke; slow UIs drop input typed at full speed.",
        f"DEFAULTDELAY {default_delay}",
        "",
    ]


def compile_payload(
    payload: Hak5Payload,
    *,
    start_delay: int = 1000,
    default_delay: int = 0,
    preamble: str = "",
) -> str:
    """Compile a single payload to DuckyScript.

    Args:
        payload: The payload to compile.
        start_delay: Milliseconds to wait before first keystroke.
        default_delay: Milliseconds between every command. 0 leaves the
            device's own default in place.
        preamble: Optional DuckyScript lines to prepend (e.g. ``GUI r``).
    """
    lines: list[str] = []
    lines.append(f"REM Prompt Injection Studio — prompt injection payload: {payload.name}")
    if payload.description:
        lines.append(f"REM {payload.description}")
    lines.append("")
    lines.extend(_default_delay_lines(default_delay))

    if preamble:
        lines.append(preamble.rstrip())
        lines.append("")

    lines.append(f"DELAY {start_delay}")
    lines.extend(type_text(payload.text))

    return "\n".join(lines) + "\n"
