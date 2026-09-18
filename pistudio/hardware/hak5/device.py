"""Hak5 device detection and payload deployment.

Scans mounted volumes for Rubber Ducky and Bash Bunny devices,
and writes compiled payloads after user confirmation.
"""

import logging
import os
import shutil
import stat
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pistudio.hardware.hak5.bunny_files import BunnyFile

from pistudio.hardware.volumes import scan_volumes as _scan_volumes

logger = logging.getLogger(__name__)


def find_ducky_volumes() -> list[str]:
    """Find mounted Rubber Ducky volumes.

    Looks for volumes named ``DUCKY`` or containing ``inject.bin``.
    """
    results: list[str] = []
    for vol in _scan_volumes():
        name = os.path.basename(vol).upper()
        if name == "DUCKY":
            results.append(vol)
            continue
        if os.path.isfile(os.path.join(vol, "inject.bin")):
            results.append(vol)
    return results


def find_bunny_volumes() -> list[str]:
    """Find mounted Bash Bunny volumes.

    Looks for volumes named ``BashBunny`` or containing a
    ``/payloads/`` directory structure.
    """
    results: list[str] = []
    for vol in _scan_volumes():
        name = os.path.basename(vol)
        if name.upper() in ("BASHBUNNY", "YOURNAME"):
            results.append(vol)
            continue
        if os.path.isdir(os.path.join(vol, "payloads")):
            results.append(vol)
    return results


# ── Deploy ───────────────────────────────────────────────────────


def deploy_ducky(
    script: str,
    path: str | None = None,
    *,
    layout: str = "us",
) -> str:
    """Arm a Rubber Ducky: encode the payload and write it to the device.

    The Ducky runs ``inject.bin``, so that is what arms it — this compiles the
    DuckyScript here rather than sending the operator to a web IDE.  The
    human-readable ``payload.txt`` is written alongside it, matching what
    Hak5 PayloadStudio produces, so the source stays on the device for
    reference.

    Args:
        script: The compiled DuckyScript source text.
        path: Explicit path to write to. If None, auto-detects.
        layout: Keyboard layout the target uses, for encoding.

    Returns:
        The path ``inject.bin`` was written to.

    Raises:
        FileNotFoundError: If no device found and no path given.
        ValueError: If the payload cannot be encoded for the layout.
        OSError: If writing fails.
    """
    from pistudio.hardware.hak5.encoder import encode

    # Encode before touching the device: a payload with an untypeable
    # character should fail without leaving a half-armed Ducky.
    binary = encode(script, layout=layout)

    if path is None:
        volumes = find_ducky_volumes()
        if not volumes:
            raise FileNotFoundError(
                "No Rubber Ducky volume found. Insert the device or use --path to specify the mount point."
            )
        path = volumes[0]

    inject_path = os.path.join(path, "inject.bin")
    with open(inject_path, "wb") as f:
        f.write(binary)
    # Keep the source beside the binary, as PayloadStudio does.
    with open(os.path.join(path, "payload.txt"), "w", encoding="utf-8") as f:
        f.write(script)
    logger.info("Wrote inject.bin (%d bytes) and payload.txt to %s", len(binary), path)
    return inject_path


def deploy_bunny(
    script: str,
    path: str | None = None,
    switch: int = 1,
) -> str:
    """Write a Bunny Script payload to a Bash Bunny volume.

    Args:
        script: The compiled Bunny Script text.
        path: Explicit path to write to. If None, auto-detects.
        switch: Switch position (1 or 2). Default 1.

    Returns:
        The path the payload was written to.

    Raises:
        FileNotFoundError: If no device found and no path given.
        OSError: If writing fails.
        ValueError: If switch is not 1 or 2.
    """
    if switch not in (1, 2):
        raise ValueError(f"Switch must be 1 or 2, got {switch}")

    if path is None:
        volumes = find_bunny_volumes()
        if not volumes:
            raise FileNotFoundError(
                "No Bash Bunny volume found. "
                "Insert the device (in arming mode) or use --path to specify the mount point."
            )
        path = volumes[0]

    # Write to /payloads/switchN/payload.txt
    switch_dir = os.path.join(path, "payloads", f"switch{switch}")
    os.makedirs(switch_dir, mode=0o755, exist_ok=True)
    payload_path = os.path.join(switch_dir, "payload.txt")
    with open(payload_path, "w", encoding="utf-8") as f:
        f.write(script)
    # Make executable (Unix only — Windows ignores execute bits)
    if sys.platform != "win32":
        os.chmod(payload_path, os.stat(payload_path).st_mode | stat.S_IXUSR | stat.S_IXGRP)
    logger.info("Wrote Bunny Script to %s", payload_path)
    return payload_path


def deploy_bunny_files(
    files: "list[BunnyFile]",
    path: str | None = None,
    switch: int = 1,
) -> list[str]:
    """Copy registered files to a Bash Bunny volume.

    Files are placed in ``/payloads/switchN/files/`` on the device,
    which is accessible from the target when ``ATTACKMODE HID STORAGE``
    is active.

    Args:
        files: List of ``BunnyFile`` objects to deploy.
        path: Explicit device path. If None, auto-detects.
        switch: Switch position (1 or 2). Default 1.

    Returns:
        List of destination paths on the device.

    Raises:
        FileNotFoundError: If no device found and no path given,
            or if a source file no longer exists.
        OSError: If copying fails.
        ValueError: If switch is not 1 or 2.
    """
    if switch not in (1, 2):
        raise ValueError(f"Switch must be 1 or 2, got {switch}")

    if path is None:
        volumes = find_bunny_volumes()
        if not volumes:
            raise FileNotFoundError(
                "No Bash Bunny volume found. "
                "Insert the device (in arming mode) or use --path to specify the mount point."
            )
        path = volumes[0]

    files_dir = os.path.join(path, "payloads", f"switch{switch}", "files")
    os.makedirs(files_dir, mode=0o755, exist_ok=True)

    deployed: list[str] = []
    for bf in files:
        if not os.path.isfile(bf.local_path):
            raise FileNotFoundError(f"Source file no longer exists: {bf.local_path} (registered as '{bf.name}')")
        dest = os.path.join(files_dir, bf.filename)
        shutil.copy2(bf.local_path, dest)
        logger.info("Deployed file '%s' → %s", bf.name, dest)
        deployed.append(dest)

    return deployed
