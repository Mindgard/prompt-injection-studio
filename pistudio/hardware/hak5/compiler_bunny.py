"""Bash Bunny payload compiler — converts payloads to Bunny Script.

Output is a Bash script using Bunny Script extensions (``Q STRING``,
``Q ENTER``, ``Q DELAY``, ``ATTACKMODE HID``, ``LED`` states).
Written to ``/payloads/switch1/payload.txt`` (or switch2) on the device.

File references
~~~~~~~~~~~~~~~
Payload text may contain ``{{file:name}}`` placeholders.  When files are
present the compiler switches to ``ATTACKMODE HID STORAGE`` and expands
the placeholders to OS-specific paths on the target machine.
"""

import re
import sys
from typing import TYPE_CHECKING

from pistudio.hardware.payloads import Payload as Hak5Payload

if TYPE_CHECKING:
    from pistudio.hardware.hak5.bunny_files import BunnyFile

# Regex matching {{file:some-name}} placeholders
_FILE_REF_RE = re.compile(r"\{\{file:([A-Za-z0-9_.-]+)\}\}")

# OS-specific path templates for the Bunny's USB storage as seen by the target.
# The Bunny mounts as a removable drive; the label is typically the volume name.
_OS_PATH_TEMPLATES: dict[str, str] = {
    # Windows: the drive letter is unpredictable, so the preamble resolves it
    # by volume label into $BunnyDrive within the PowerShell session it opens.
    "windows": "$BunnyDrive\\payloads\\switch{switch}\\files\\{filename}",
    "linux": "/media/usb0/payloads/switch{switch}/files/{filename}",
    "mac": "/Volumes/BashBunny/payloads/switch{switch}/files/{filename}",
}


def detect_os() -> str:
    """Auto-detect the host OS and return our target name (windows|linux|mac)."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _default_delay_lines(default_delay: int) -> list[str]:
    """Return the ``Q DEFAULTDELAY`` preamble, or nothing when unset.

    Paces every subsequent ``Q`` command, which keeps browser chat UIs from
    dropping keystrokes typed faster than they re-render.

    Args:
        default_delay: Milliseconds between commands. 0 disables the directive.
    """
    if default_delay <= 0:
        return []
    return [
        "# Pace every keystroke; slow UIs drop input typed at full speed.",
        f"Q DEFAULTDELAY {default_delay}",
        "",
    ]


def _type_text(text: str) -> list[str]:
    """Return Bunny Script lines that type *text* verbatim, newlines included.

    ``Q STRING`` does not emit a newline, so each line is followed by its own
    ``Q ENTER``.  Emitting one ``Q STRING`` per line with a single trailing
    ``Q ENTER`` would type the lines concatenated into one.
    """
    lines: list[str] = []
    for text_line in text.split("\n"):
        if text_line:
            lines.append(f"Q STRING {text_line}")
        lines.append("Q ENTER")
    return lines


# ── File reference helpers ───────────────────────────────────────


def extract_file_references(text: str) -> list[str]:
    """Return a list of file names referenced via ``{{file:name}}`` in *text*."""
    return _FILE_REF_RE.findall(text)


def _file_path_snippet(
    filename: str,
    os_target: str,
    switch: int = 1,
) -> str:
    """Return the OS-specific path string for a deployed file."""
    template = _OS_PATH_TEMPLATES.get(os_target)
    if template is None:
        raise ValueError(f"Unsupported OS target: '{os_target}'. Use: windows, linux, mac")
    return template.format(
        switch=switch,
        filename=filename,
    )


def _expand_file_refs(
    text: str,
    file_map: dict[str, "BunnyFile"],
    os_target: str,
    switch: int = 1,
) -> str:
    """Replace all ``{{file:name}}`` placeholders with OS-specific paths."""

    def _replacer(m: re.Match) -> str:
        name = m.group(1)
        bf = file_map.get(name)
        if bf is None:
            return m.group(0)  # leave unresolved refs as-is
        return _file_path_snippet(bf.filename, os_target, switch)

    return _FILE_REF_RE.sub(_replacer, text)


def _windows_drive_preamble() -> str:
    """Bunny Script snippet that opens a PowerShell session on the target.

    The drive letter assigned to the Bunny's storage volume is unpredictable,
    so it is resolved on the target by volume label and held in a PowerShell
    variable.  Everything that follows is typed into that same session, which
    is what makes ``$BunnyDrive`` resolvable: an earlier version set a
    *process*-scoped environment variable inside a PowerShell process that then
    exited, so the variable was always empty by the time paths were typed.
    """
    return (
        "# Open a PowerShell session and resolve the Bunny's drive letter by label.\n"
        "# Subsequent lines are typed into this session so $BunnyDrive resolves.\n"
        "Q GUI r\n"
        "Q DELAY 500\n"
        "Q STRING powershell\n"
        "Q ENTER\n"
        "Q DELAY 2000\n"
        "Q STRING $BunnyDrive=(Get-Volume | "
        "Where-Object {$_.FileSystemLabel -match 'BashBunny'} | "
        "Select-Object -First 1).DriveLetter + ':'\n"
        "Q ENTER\n"
        "Q DELAY 500"
    )


def compile_payload(
    payload: Hak5Payload,
    *,
    start_delay: int = 1000,
    default_delay: int = 0,
    preamble: str = "",
) -> str:
    """Compile a single payload to Bunny Script.

    Args:
        payload: The payload to compile.
        start_delay: Milliseconds to wait before first keystroke.
        default_delay: Milliseconds between every command. 0 leaves the
            device's own default in place.
        preamble: Optional Bunny Script lines to insert after ATTACKMODE.
    """
    lines: list[str] = []
    lines.append("#!/bin/bash")
    lines.append(f"# Prompt Injection Studio — prompt injection payload: {payload.name}")
    if payload.description:
        lines.append(f"# {payload.description}")
    lines.append("")
    lines.append("ATTACKMODE HID")
    lines.append("LED ATTACK")
    lines.append("")
    lines.extend(_default_delay_lines(default_delay))

    if preamble:
        lines.append(preamble.rstrip())
        lines.append("")

    lines.append(f"Q DELAY {start_delay}")

    lines.extend(_type_text(payload.text))
    lines.append("")
    lines.append("LED FINISH")

    return "\n".join(lines) + "\n"


def compile_payload_with_files(
    payload: Hak5Payload,
    files: list["BunnyFile"],
    *,
    os_target: str,
    switch: int = 1,
    start_delay: int = 1000,
    default_delay: int = 0,
    preamble: str = "",
) -> str:
    """Compile a payload with file references to Bunny Script.

    Switches to ``ATTACKMODE HID STORAGE`` and expands ``{{file:name}}``
    placeholders to OS-specific paths.

    Args:
        payload: The payload to compile.
        files: List of BunnyFile objects referenced by the payload.
        os_target: Target OS — ``"windows"``, ``"linux"``, or ``"mac"``.
            Required (no default).
        switch: Switch position (1 or 2).
        start_delay: Milliseconds to wait before first keystroke.
        default_delay: Milliseconds between every command. 0 leaves the
            device's own default in place.
        preamble: Optional Bunny Script lines to insert after ATTACKMODE.
    """
    if os_target not in _OS_PATH_TEMPLATES:
        raise ValueError("--os is required. Choose: windows, linux, mac")

    file_map = {bf.name: bf for bf in files}
    expanded_text = _expand_file_refs(payload.text, file_map, os_target, switch)

    lines: list[str] = []
    lines.append("#!/bin/bash")
    lines.append(f"# Prompt Injection Studio — prompt injection payload: {payload.name}")
    if payload.description:
        lines.append(f"# {payload.description}")
    lines.append(f"# Files: {', '.join(bf.name for bf in files)}")
    lines.append(f"# Target OS: {os_target}")
    lines.append("")
    lines.append("ATTACKMODE HID STORAGE")
    lines.append("LED ATTACK")
    lines.append("")
    lines.extend(_default_delay_lines(default_delay))

    if os_target == "windows":
        lines.append(_windows_drive_preamble())
        lines.append("")

    if preamble:
        lines.append(preamble.rstrip())
        lines.append("")

    lines.append(f"Q DELAY {start_delay}")

    lines.extend(_type_text(expanded_text))
    lines.append("")
    lines.append("LED FINISH")

    return "\n".join(lines) + "\n"
