"""Classic Bluetooth device discovery via ubertooth-scan and ubertooth-rx."""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)


def scan_discoverable(duration_secs: int = 20, extended: bool = True) -> list[dict]:
    """Scan for discoverable BT devices using ubertooth-scan + BlueZ."""
    cmd = ["ubertooth-scan", "-t", str(duration_secs)]
    if extended:
        cmd.extend(["-s", "-x"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_secs + 10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("ubertooth-scan failed: %s", e)
        return []
    return _parse_scan_output(result.stdout)


def survey_piconets(duration_secs: int = 20) -> list[dict]:
    """Survey for all BT piconets including undiscoverable devices."""
    cmd = ["ubertooth-rx", "-z", "-t", str(duration_secs)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_secs + 10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("ubertooth-rx survey failed: %s", e)
        return []
    return _parse_survey_output(result.stdout)


def _parse_scan_output(output: str) -> list[dict]:
    devices = []
    addr_pattern = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+(.*)")
    for line in output.splitlines():
        match = addr_pattern.match(line.strip())
        if match:
            devices.append({"addr": match.group(1).upper(), "name": match.group(2).strip(), "type": "classic"})
    return devices


def _parse_survey_output(output: str) -> list[dict]:
    piconets = []
    lap_pattern = re.compile(r"LAP:\s*([0-9a-fA-F]+)")
    for line in output.splitlines():
        match = lap_pattern.search(line)
        if match:
            piconets.append({"lap": match.group(1), "type": "classic_piconet"})
    return piconets
