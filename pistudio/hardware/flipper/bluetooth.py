"""Flipper Zero Bluetooth prompt injection support.

Configure Flipper's Bluetooth device name or use BLE spam
to broadcast prompt injection payloads as device names.

Attack Vectors:
1. Static device name: Change Flipper's BT name to a payload
2. BLE spam: Broadcast many fake devices with payload names
3. BLE advertising: Custom advertising data

Attack Scenario:
Bluetooth device names are displayed by device managers, IoT dashboards,
and scanning tools. If an LLM processes a list of nearby devices, the
device name IS the injection.
"""

# Bluetooth name limits
BT_NAME_MAX_LENGTH = 248  # Bluetooth spec maximum
BT_NAME_TYPICAL_MAX = 30  # Common practical display limit


def compile_bt_name_payload(payload_text: str) -> str:
    """Compile payload for Bluetooth device name.

    If the payload fits within typical display limits, returns as-is.
    If too long, truncates with a note.

    Args:
        payload_text: The prompt injection text.

    Returns:
        The device name string (possibly truncated).
    """
    if len(payload_text) <= BT_NAME_TYPICAL_MAX:
        return payload_text

    # Truncate to typical max, leaving room for ellipsis indicator
    return payload_text[: BT_NAME_TYPICAL_MAX - 3] + "..."


def compile_ble_spam_config(payload_text: str, num_devices: int = 0) -> list[str]:
    """Split a payload across BLE device names that appear in Bluetooth scans.

    Each name is prefixed ``[N/M]`` so the pieces can be reassembled in order.

    Args:
        payload_text: The full prompt injection text.
        num_devices: How many device names to produce. 0 auto-calculates the
            number needed to carry the whole payload.

    Returns:
        The device name strings.

    Raises:
        ValueError: If *num_devices* is too small to carry *payload_text*.
            Truncating would drop the tail while still labelling the last
            chunk ``[M/M]``, so a receiver could not tell it was incomplete.
    """
    chunk_size = BT_NAME_TYPICAL_MAX - 6  # Leave room for "[N/M] "
    needed = (len(payload_text) + chunk_size - 1) // chunk_size

    if num_devices <= 0:
        num_devices = needed
    elif num_devices < needed:
        raise ValueError(
            f"{num_devices} device name(s) cannot carry {len(payload_text)} characters; "
            f"{needed} are needed at {chunk_size} characters each."
        )

    chunks: list[str] = []
    for i in range(num_devices):
        chunk = payload_text[i * chunk_size : (i + 1) * chunk_size]
        if chunk:
            chunks.append(f"[{i + 1}/{num_devices}] {chunk}")

    return chunks
