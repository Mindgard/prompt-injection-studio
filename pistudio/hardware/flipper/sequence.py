"""Attack sequence builder and deployment for Flipper Zero.

Sequences are multi-step, multi-protocol attack plans that the Flipper
can execute autonomously.  They are stored as JSON files in
``~/.pistudio/hardware/sequences/`` (global) or
``<session_dir>/hardware/sequences/`` (session).

Sequence JSON format (matches the FAP's ``MindgardSequence`` struct)::

    {
        "name": "office-sweep",
        "description": "Multi-vector office assessment",
        "steps": [
            {"protocol": "badusb", "payload": "indirect-injection",
             "delay_after_ms": 5000},
            {"protocol": "nfc", "payload": "badge-clone",
             "delay_after_ms": 10000}
        ]
    }
"""

import json
import logging
import os
import re

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_STUDIO_DIR = os.path.join(os.path.expanduser("~"), ".pistudio")
_GLOBAL_SEQ_DIR = os.path.join(_STUDIO_DIR, "hardware", "sequences")

VALID_PROTOCOLS = ("badusb", "nfc", "ble")


# ── Models ───────────────────────────────────────────────────────


class SequenceStep(BaseModel):
    """A single step in an attack sequence."""

    model_config = {"extra": "ignore"}

    protocol: str = "badusb"
    payload: str = ""
    delay_after_ms: int = 0


class AttackSequence(BaseModel):
    """A named multi-step attack sequence."""

    model_config = {"extra": "ignore"}

    name: str
    description: str = ""
    steps: list[SequenceStep] = []


# ── Storage helpers ──────────────────────────────────────────────


def _session_seq_dir(session_dir: str) -> str:
    return os.path.join(session_dir, "hardware", "sequences")


def _seq_path(name: str, base_dir: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return os.path.join(base_dir, f"{safe}.json")


def _load_seq(path: str) -> AttackSequence | None:
    try:
        with open(path) as f:
            data = json.load(f)
        return AttackSequence(**data)
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _save_seq(seq: AttackSequence, base_dir: str) -> str:
    os.makedirs(base_dir, mode=0o700, exist_ok=True)
    path = _seq_path(seq.name, base_dir)
    with open(path, "w") as f:
        json.dump(seq.model_dump(), f, indent=2)
    return path


# ── CRUD ─────────────────────────────────────────────────────────


def list_sequences(session_dir: str) -> list[tuple[AttackSequence, str]]:
    """Return ``(sequence, scope)`` tuples for all sequences."""
    results: list[tuple[AttackSequence, str]] = []
    seen: set[str] = set()

    # Session sequences
    sdir = _session_seq_dir(session_dir)
    if os.path.isdir(sdir):
        for fname in sorted(os.listdir(sdir)):
            if fname.endswith(".json"):
                seq = _load_seq(os.path.join(sdir, fname))
                if seq and seq.name not in seen:
                    results.append((seq, "session"))
                    seen.add(seq.name)

    # Global sequences
    if os.path.isdir(_GLOBAL_SEQ_DIR):
        for fname in sorted(os.listdir(_GLOBAL_SEQ_DIR)):
            if fname.endswith(".json"):
                seq = _load_seq(os.path.join(_GLOBAL_SEQ_DIR, fname))
                if seq and seq.name not in seen:
                    results.append((seq, "global"))
                    seen.add(seq.name)

    return results


def get_sequence(name: str, session_dir: str) -> tuple[AttackSequence, str] | None:
    """Look up a sequence by name."""
    for seq, scope in list_sequences(session_dir):
        if seq.name == name:
            return seq, scope
    return None


def create_sequence(
    name: str,
    session_dir: str,
    description: str = "",
    global_scope: bool = False,
) -> AttackSequence:
    """Create a new empty sequence."""
    seq = AttackSequence(name=name, description=description)
    base_dir = _GLOBAL_SEQ_DIR if global_scope else _session_seq_dir(session_dir)
    _save_seq(seq, base_dir)
    logger.info("Created sequence '%s'", name)
    return seq


def add_step(
    name: str,
    protocol: str,
    payload: str,
    session_dir: str,
    delay_after_ms: int = 0,
    global_scope: bool = False,
) -> AttackSequence:
    """Add a step to an existing sequence."""
    result = get_sequence(name, session_dir)
    if result is None:
        raise ValueError(f"Sequence '{name}' not found")

    seq, scope = result
    if len(seq.steps) >= 8:
        raise ValueError("Maximum 8 steps per sequence")

    protocol = protocol.lower()
    if protocol not in VALID_PROTOCOLS:
        raise ValueError(f"Invalid protocol: {protocol}. Use: {', '.join(VALID_PROTOCOLS)}")

    step = SequenceStep(
        protocol=protocol,
        payload=payload,
        delay_after_ms=delay_after_ms,
    )
    seq.steps.append(step)

    base_dir = _GLOBAL_SEQ_DIR if global_scope else _session_seq_dir(session_dir)
    _save_seq(seq, base_dir)
    return seq


def remove_sequence(
    name: str,
    session_dir: str,
    global_scope: bool = False,
) -> None:
    """Remove a sequence by name."""
    base_dir = _GLOBAL_SEQ_DIR if global_scope else _session_seq_dir(session_dir)
    path = _seq_path(name, base_dir)
    if not os.path.isfile(path):
        raise ValueError(f"Sequence '{name}' not found in {'global' if global_scope else 'session'} scope")
    os.unlink(path)


def sequence_names(session_dir: str) -> list[str]:
    """Return sorted list of all sequence names."""
    return sorted(s.name for s, _ in list_sequences(session_dir))


# ── Deploy to Flipper SD card ────────────────────────────────────


def deploy_sequence(
    name: str,
    session_dir: str,
    path: str | None = None,
) -> str:
    """Deploy a sequence to the Flipper SD card.

    Writes the sequence JSON to ``/ext/apps_data/mindgard/sequences/<name>.json``.

    Returns the deployed file path.
    """
    result = get_sequence(name, session_dir)
    if result is None:
        raise ValueError(f"Sequence '{name}' not found")

    seq, _ = result

    if path is None:
        from pistudio.hardware.flipper.device import find_flipper_volumes

        volumes = find_flipper_volumes()
        if not volumes:
            raise FileNotFoundError("No Flipper Zero SD card found. Use --path to specify.")
        path = volumes[0]

    from pistudio.hardware.flipper.validate import safe_join

    dest_dir = os.path.join(path, "apps_data", "mindgard", "sequences")
    os.makedirs(dest_dir, exist_ok=True)

    # Write in the format the FAP expects
    data = {
        "name": seq.name,
        "description": seq.description,
        "steps": [
            {
                "protocol": step.protocol,
                "payload_name": step.payload,
                "delay_after_ms": step.delay_after_ms,
            }
            for step in seq.steps
        ],
    }

    dest_file = safe_join(dest_dir, f"{re.sub(r'[^a-zA-Z0-9_-]', '_', name)}.json")
    with open(dest_file, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Deployed sequence '%s' to %s", name, dest_file)
    return dest_file


__all__ = [
    "AttackSequence",
    "SequenceStep",
    "list_sequences",
    "get_sequence",
    "create_sequence",
    "add_step",
    "remove_sequence",
    "sequence_names",
    "deploy_sequence",
]
