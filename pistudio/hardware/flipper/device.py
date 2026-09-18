"""Flipper Zero device detection and deployment.

Scans mounted volumes for Flipper Zero SD cards and deploys payloads
to the appropriate directories for each protocol.
"""

import logging
import os

from pistudio.hardware.flipper.nfc import NFCPayload, compile_ndef_payload
from pistudio.hardware.flipper.validate import safe_join
from pistudio.hardware.volumes import scan_volumes as _scan_volumes

logger = logging.getLogger(__name__)

# Flipper Zero directory structure
_FLIPPER_DIRS = {
    "badusb": "badusb",
    "nfc": "nfc",
}

# Volume markers to identify Flipper SD cards
_FLIPPER_VOLUME_MARKERS = ("flipper", "flpr", "f0")


class PartialDeployError(Exception):
    """One protocol failed after another had already written a file.

    Carries the paths that *did* land so the caller can tell the operator
    what the Flipper is holding rather than implying nothing was written.
    """

    def __init__(self, cause: Exception, deployed: dict[str, str]):
        super().__init__(str(cause))
        self.cause = cause
        self.deployed = deployed


def find_flipper_volumes() -> list[str]:
    """Find mounted Flipper Zero SD cards.

    Looks for volumes with 'flipper' in the name or containing
    the standard Flipper directory structure.
    """
    results: list[str] = []
    for vol in _scan_volumes():
        name = os.path.basename(vol).lower()

        # Check name markers
        if any(marker in name for marker in _FLIPPER_VOLUME_MARKERS):
            results.append(vol)
            continue

        # Check for Flipper directory structure
        if os.path.isdir(os.path.join(vol, "badusb")) and os.path.isdir(os.path.join(vol, "nfc")):
            results.append(vol)
            continue

        # Check for any of the standard Flipper directories
        flipper_dirs_found = sum(1 for d in _FLIPPER_DIRS.values() if os.path.isdir(os.path.join(vol, d)))
        if flipper_dirs_found >= 2:
            results.append(vol)

    return results


# ── Deploy functions ─────────────────────────────────────────────


def deploy_badusb(
    script: str,
    name: str,
    path: str | None = None,
) -> str:
    """Write a DuckyScript payload to Flipper Zero SD card.

    Args:
        script: The compiled DuckyScript text.
        name: Payload filename (without .txt extension).
        path: Explicit SD card path. Auto-detects if None.

    Returns:
        Path to the deployed payload.

    Raises:
        FileNotFoundError: If no Flipper volume found and no path given.
        ValueError: If *name* is not usable as a filename on the SD card.
    """
    if path is None:
        volumes = find_flipper_volumes()
        if not volumes:
            raise FileNotFoundError("No Flipper Zero SD card found. Connect via USB (Mass Storage mode) or use --path.")
        path = volumes[0]

    badusb_dir = os.path.join(path, _FLIPPER_DIRS["badusb"])
    os.makedirs(badusb_dir, exist_ok=True)

    # Ensure .txt extension
    if not name.endswith(".txt"):
        name = f"{name}.txt"

    payload_path = safe_join(badusb_dir, name)
    with open(payload_path, "w", encoding="utf-8") as f:
        f.write(script)

    logger.info("Deployed BadUSB payload to %s", payload_path)
    return payload_path


def deploy_nfc(
    payload: NFCPayload,
    path: str | None = None,
) -> str:
    """Write an NFC payload to Flipper Zero SD card.

    Args:
        payload: The NFCPayload to deploy.
        path: Explicit SD card path. Auto-detects if None.

    Returns:
        Path to the deployed .nfc file.

    Raises:
        FileNotFoundError: If no Flipper volume found and no path given.
        ValueError: If the payload name is not usable as a filename.
    """
    if path is None:
        volumes = find_flipper_volumes()
        if not volumes:
            raise FileNotFoundError("No Flipper Zero SD card found. Connect via USB (Mass Storage mode) or use --path.")
        path = volumes[0]

    nfc_dir = os.path.join(path, _FLIPPER_DIRS["nfc"])
    os.makedirs(nfc_dir, exist_ok=True)

    # Compile to Flipper format
    nfc_content = compile_ndef_payload(payload)

    # Ensure .nfc extension
    name = payload.name
    if not name.endswith(".nfc"):
        name = f"{name}.nfc"

    nfc_path = safe_join(nfc_dir, name)
    with open(nfc_path, "w", encoding="utf-8") as f:
        f.write(nfc_content)

    logger.info("Deployed NFC payload to %s", nfc_path)
    return nfc_path


def deploy_all(
    name: str,
    payload_text: str,
    path: str | None = None,
    card_type: str = "NTAG216",
) -> dict[str, str]:
    """Deploy a payload to every Flipper protocol at once.

    This creates:
    - BadUSB payload (.txt)
    - NFC payload (.nfc)

    Bluetooth configuration is returned as a string (not a file).

    Args:
        name: Base name for the payloads.
        payload_text: The prompt injection text.
        path: Explicit SD card path. Auto-detects if None.
        card_type: NFC card type (default NTAG216).

    Returns:
        Dict mapping protocol names to deployed file paths.

    Raises:
        FileNotFoundError: If no Flipper volume found and no path given.
        PartialDeployError: If one protocol fails after another has already
            written a file.  Its ``deployed`` attribute names what landed.
    """
    if path is None:
        volumes = find_flipper_volumes()
        if not volumes:
            raise FileNotFoundError("No Flipper Zero SD card found. Connect via USB (Mass Storage mode) or use --path.")
        path = volumes[0]

    from pistudio.hardware.flipper.badusb import compile_payload as compile_badusb
    from pistudio.hardware.flipper.bluetooth import compile_bt_name_payload
    from pistudio.hardware.payloads import Payload

    results: dict[str, str] = {}
    try:
        payload_obj = Payload(name=name, text=payload_text)
        results["badusb"] = deploy_badusb(compile_badusb(payload_obj), name, path)

        nfc_payload = NFCPayload(name=name, payload_text=payload_text, card_type=card_type)
        results["nfc"] = deploy_nfc(nfc_payload, path)

        # Bluetooth is a name the operator sets by hand, not a file on the card.
        results["bluetooth"] = f"BT Name: {compile_bt_name_payload(payload_text)}"
    except (OSError, ValueError) as exc:
        if results:
            raise PartialDeployError(exc, results) from exc
        raise

    logger.info("Deployed to all Flipper protocols at %s", path)
    return results
