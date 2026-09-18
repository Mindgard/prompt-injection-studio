"""BLE sniffing and device identification via Ubertooth One.

Wraps ubertooth-btle for passive BLE monitoring, parses advertising
addresses from stdout, and identifies AI-enabled devices by name
patterns and OUI prefixes.
"""

import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

# Regex for extracting advertiser addresses from ubertooth-btle output
_ADVA_RE = re.compile(r"AdvA:\s+([0-9a-fA-F:]{17})")

# Known AI device name patterns: (regex, ai_type label)
_AI_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Echo\b|Alexa", re.IGNORECASE), "Amazon Alexa"),
    (re.compile(r"Google Home|Nest\b|Chromecast", re.IGNORECASE), "Google Home"),
    (re.compile(r"HomePod", re.IGNORECASE), "Apple HomePod"),
    (re.compile(r"Cortana", re.IGNORECASE), "Microsoft Cortana"),
    (re.compile(r"Sonos", re.IGNORECASE), "Sonos"),
    (re.compile(r"Copilot", re.IGNORECASE), "Microsoft Copilot"),
]

# OUI prefixes mapped to AI device type
_AI_OUI_PREFIXES: dict[str, str] = {
    "44:07:0B": "Amazon Alexa",
    "68:54:FD": "Amazon Alexa",
    "F0:F0:A4": "Google Home",
    "30:FD:38": "Google Home",
    "48:D6:D5": "Apple HomePod",
    "7C:D1:C3": "Apple HomePod",
}


def sniff_follow(
    output_pcap: str,
    duration_secs: int = 30,
    target_addr: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start ubertooth-btle in follow mode, writing to a PCAP file.

    Args:
        output_pcap: Path for the output PCAP file.
        duration_secs: Capture duration in seconds.
        target_addr: Optional target BLE address to follow.

    Returns:
        The running subprocess handle.
    """
    cmd = ["ubertooth-btle", "-f", "-r", output_pcap]
    if target_addr:
        cmd.extend(["-t", target_addr])
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def sniff_promiscuous(output_pcap: str) -> subprocess.Popen[bytes]:
    """Start ubertooth-btle in promiscuous mode, writing to a PCAP file.

    Args:
        output_pcap: Path for the output PCAP file.

    Returns:
        The running subprocess handle.
    """
    return subprocess.Popen(
        ["ubertooth-btle", "-p", "-r", output_pcap],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_sniff_output(raw_output: str) -> list[dict]:
    """Parse AdvA addresses from ubertooth-btle stdout.

    Deduplicates by address and counts how many times each was seen.

    Args:
        raw_output: Raw text output from ubertooth-btle.

    Returns:
        List of dicts with keys: addr, addr_type, seen_count.
    """
    if not raw_output.strip():
        return []

    addr_counts: Counter[str] = Counter()
    addr_types: dict[str, str] = {}

    for line in raw_output.splitlines():
        match = _ADVA_RE.search(line)
        if not match:
            continue
        addr = match.group(1).upper()
        addr_counts[addr] += 1
        # Extract address type if present (e.g., "(public)" or "(random)")
        type_match = re.search(r"\((public|random)\)", line, re.IGNORECASE)
        if type_match:
            addr_types[addr] = type_match.group(1).lower()

    devices: list[dict] = []
    for addr, count in addr_counts.items():
        devices.append(
            {
                "addr": addr,
                "addr_type": addr_types.get(addr, "unknown"),
                "seen_count": count,
            }
        )
    return devices


def identify_ai_devices(devices: list[dict]) -> list[dict]:
    """Identify AI-enabled devices from a list of discovered BLE devices.

    Matches against known device name patterns and OUI prefixes.

    Args:
        devices: List of device dicts, each with at least "addr" and "name" keys.

    Returns:
        List of matching device dicts, each augmented with "ai_type".
    """
    results: list[dict] = []
    for device in devices:
        name = device.get("name", "")
        addr = device.get("addr", "").upper()
        oui = addr[:8]

        # Check name patterns
        for pattern, ai_type in _AI_NAME_PATTERNS:
            if pattern.search(name):
                results.append({**device, "ai_type": ai_type})
                break
        else:
            # Check OUI prefix
            if oui in _AI_OUI_PREFIXES:
                results.append({**device, "ai_type": _AI_OUI_PREFIXES[oui]})

    return results


def pull_and_parse_pcap(pcap_path: str, session_dir: str) -> Path:
    """Copy PCAP to session directory and run tshark for enriched parsing.

    Copies the capture file, runs tshark to extract BLE fields, and
    saves results as ble_inventory.json in the session directory.

    Args:
        pcap_path: Path to the source PCAP file.
        session_dir: Path to the session directory.

    Returns:
        Path to the generated ble_inventory.json file.
    """
    session = Path(session_dir)
    session.mkdir(parents=True, exist_ok=True)

    dest_pcap = session / Path(pcap_path).name
    shutil.copy2(pcap_path, dest_pcap)

    inventory_path = session / "ble_inventory.json"

    try:
        result = subprocess.run(
            [
                "tshark",
                "-r",
                str(dest_pcap),
                "-T",
                "json",
                "-Y",
                "btle",
                "-e",
                "btle.advertising_address",
                "-e",
                "btle.data_header",
                "-e",
                "btcommon.eir_ad.entry.device_name",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        parsed = json.loads(result.stdout) if result.stdout.strip() else []
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        parsed = []

    inventory_path.write_text(json.dumps(parsed, indent=2))
    return inventory_path
