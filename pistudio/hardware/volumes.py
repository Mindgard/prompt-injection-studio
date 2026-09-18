"""Shared volume scanning for hardware device detection.

Provides platform-aware volume listing used by all device modules
(Bash Bunny, USB Rubber Ducky, Flipper Zero).
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _get_volume_dirs() -> list[str]:
    """Return candidate volume mount directories for the current platform."""
    if sys.platform == "darwin":
        return ["/Volumes"]
    if sys.platform == "win32":
        # Windows: check all drive letters except C:
        drives = []
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                drives.append(drive)
        return drives
    # Linux / BSD / WSL: check common mount points
    dirs = []
    for candidate in ["/media", "/run/media", "/mnt"]:
        if os.path.isdir(candidate):
            dirs.append(candidate)
    return dirs


def scan_volumes() -> list[str]:
    """Return a list of mounted volume paths.

    On macOS, lists subdirectories of ``/Volumes``.
    On Windows, lists non-C drive letters that exist.
    On Linux/BSD/WSL, lists subdirectories of ``/media``,
    ``/run/media``, and ``/mnt``.
    """
    results: list[str] = []
    volume_dirs = _get_volume_dirs()

    if sys.platform == "win32":
        # On Windows, drive letters are already the volumes
        return volume_dirs

    for base_dir in volume_dirs:
        try:
            for name in os.listdir(base_dir):
                full = os.path.join(base_dir, name)
                if os.path.isdir(full):
                    results.append(full)
                    # /run/media has a $USER subdirectory; scan one level deeper
                    if base_dir == "/run/media":
                        try:
                            for sub in os.listdir(full):
                                sub_full = os.path.join(full, sub)
                                if os.path.isdir(sub_full):
                                    results.append(sub_full)
                        except OSError:
                            logger.debug("Cannot list %s", full, exc_info=True)
        except OSError:
            logger.debug("Cannot list %s", base_dir, exc_info=True)

    return results
