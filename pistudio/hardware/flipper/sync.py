"""Sync the payload library to a Flipper Zero SD card.

Writes ``payloads.json`` to the Flipper's app data directory
(``/ext/apps_data/mindgard/``) so the native Mindgard FAP can load it
on-device.

The JSON format matches what the FAP C code expects::

    payloads.json:
        [{"name": "...", "text": "...", "category": "...", "description": "..."}]
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# The FAP reads from /ext/apps_data/mindgard/ on the Flipper SD card.
# When mounted via Mass Storage, /ext/ is the root of the volume.
_APP_DATA_SUBDIR = os.path.join("apps_data", "mindgard")


def sync_payloads(
    session_dir: str,
    path: str | None = None,
) -> tuple[str, int]:
    """Sync the payload library to the Flipper SD card.

    Args:
        session_dir: Current pistudio session directory.
        path: Explicit SD card mount path.  Auto-detects if *None*.

    Returns:
        ``(deployed_path, count)`` — path to the written file and number
        of payloads synced.

    Raises:
        FileNotFoundError: No Flipper volume found and no *path* given.
    """
    from pistudio.hardware.payloads import list_payloads

    path = _resolve_path(path)
    dest_dir = os.path.join(path, _APP_DATA_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)

    payloads = list_payloads(session_dir)
    data = [
        {
            "name": p.name,
            "text": p.text,
            "category": p.category or "",
            "description": p.description or "",
        }
        for p, _scope in payloads
    ]

    dest_file = os.path.join(dest_dir, "payloads.json")
    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Synced %d payloads to %s", len(data), dest_file)
    return dest_file, len(data)


def sync_all(
    session_dir: str,
    path: str | None = None,
) -> dict[str, tuple[str, int]]:
    """Sync every library the FAP reads to the Flipper SD card.

    Returns:
        Dict keyed by library name, mapping to ``(deployed_path, count)``.
        Kept as a dict rather than a bare tuple so adding a second library
        later does not change the signature again.
    """
    path = _resolve_path(path)
    return {"payloads": sync_payloads(session_dir, path)}


def sync_results(
    results_data: dict,
    path: str | None = None,
) -> str:
    """Sync scan results to the Flipper SD card.

    Args:
        results_data: Scan results dict (test_id, vulnerabilities, summary).
        path: Explicit SD card mount path.

    Returns:
        Path to the written ``results.json``.
    """
    path = _resolve_path(path)
    dest_dir = os.path.join(path, _APP_DATA_SUBDIR)
    os.makedirs(dest_dir, exist_ok=True)

    dest_file = os.path.join(dest_dir, "results.json")
    with open(dest_file, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2)

    logger.info("Synced scan results to %s", dest_file)
    return dest_file


# ── Internal helpers ─────────────────────────────────────────────


def _resolve_path(path: str | None) -> str:
    """Return *path* or auto-detect the first Flipper volume."""
    if path is not None:
        return path

    from pistudio.hardware.flipper.device import find_flipper_volumes

    volumes = find_flipper_volumes()
    if not volumes:
        raise FileNotFoundError("No Flipper Zero SD card found. Connect via USB (Mass Storage mode) or use --path.")
    return volumes[0]
