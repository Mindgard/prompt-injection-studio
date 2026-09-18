"""Bunny file registry — manage files for upload to Bash Bunny devices.

Tracks local files that should be deployed alongside Bunny Script payloads.
When a payload uses ``ATTACKMODE HID STORAGE``, these files are copied to
``/payloads/switchN/files/`` on the device and can be referenced from scripts.

Storage:
    ``$PISTUDIO_HOME/hak5/files.json`` — global registry, defaulting to
        ``~/.pistudio/hak5/files.json``
    ``<session_dir>/hak5/files.json`` — session-scoped registry

Lookup order: session → global (same pattern as payloads).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def _global_files_file() -> str:
    """Return the path of the global registry, honouring ``PISTUDIO_HOME``.

    Resolved per call rather than at import: a module constant is bound before
    any configuration or test fixture can take effect, which silently ignored
    ``PISTUDIO_HOME`` and made results depend on the developer's home
    directory.
    """
    from pistudio.core.studio import default_session_dir

    return os.path.join(default_session_dir(), "hak5", "files.json")


# Soft warning threshold for large files (bytes)
_SIZE_WARNING_BYTES = 100 * 1024 * 1024  # 100 MB


# ── Model ────────────────────────────────────────────────────────


class BunnyFile(BaseModel):
    """A registered file for Bash Bunny deployment."""

    model_config = {"extra": "ignore"}

    name: str
    local_path: str  # absolute path on the host machine
    filename: str  # basename for deployment (e.g. "payload.pdf")
    description: str = ""
    category: str = ""
    size_bytes: int = 0
    sha256: str = ""


# ── Name validation ──────────────────────────────────────────────


def _validate_name(name: str) -> str:
    """Validate a file registry name. Raises ValueError if invalid."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", name):
        raise ValueError(f"Invalid file name: '{name}'. Use only letters, digits, underscore, dash, or dot.")
    if ".." in name:
        raise ValueError(f"Invalid file name: '{name}'. Path traversal not allowed.")
    return name


# ── Hashing helper ───────────────────────────────────────────────


def _file_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Persistence helpers ──────────────────────────────────────────


def _session_hak5_dir(session_dir: str) -> str:
    return os.path.join(session_dir, "hak5")


def _load_files(path: str) -> list[BunnyFile]:
    """Load registered files from a JSON file.

    A corrupt or unreadable registry yields an empty list so the tool stays
    usable, but it is reported at warning level: silently returning nothing
    looks identical to "no files registered", and the next ``add`` would
    overwrite whatever was there.
    """
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable file registry at %s: %s", path, exc)
        return []

    if not isinstance(data, list):
        logger.warning("Ignoring malformed file registry at %s: expected a list", path)
        return []

    files: list[BunnyFile] = []
    for item in data:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object entry in %s", path)
            continue
        try:
            files.append(BunnyFile(**item))
        except ValidationError as exc:
            logger.warning("Skipping invalid entry %r in %s: %s", item.get("name", "?"), path, exc)
    return files


def _save_files(path: str, files: list[BunnyFile]) -> None:
    """Save registered files to a JSON file."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    data = [f.model_dump() for f in files]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(path, 0o600)


# ── CRUD ─────────────────────────────────────────────────────────


def list_files(session_dir: str) -> list[tuple[BunnyFile, str]]:
    """Return ``(file, scope)`` tuples for all registered files.

    Scope is ``"session"`` or ``"global"``.  Session shadows global.
    """
    results: list[tuple[BunnyFile, str]] = []
    seen: set[str] = set()

    # Session-scoped
    session_path = os.path.join(_session_hak5_dir(session_dir), "files.json")
    for bf in _load_files(session_path):
        if bf.name not in seen:
            results.append((bf, "session"))
            seen.add(bf.name)

    # Global
    for bf in _load_files(_global_files_file()):
        if bf.name not in seen:
            results.append((bf, "global"))
            seen.add(bf.name)

    return results


def get_file(name: str, session_dir: str) -> tuple[BunnyFile, str] | None:
    """Look up a registered file by name. Returns ``(file, scope)`` or None."""
    for bf, scope in list_files(session_dir):
        if bf.name == name:
            return bf, scope
    return None


def add_file(
    name: str,
    local_path: str,
    session_dir: str,
    *,
    description: str = "",
    category: str = "",
    global_scope: bool = False,
) -> tuple[BunnyFile, bool]:
    """Register a local file for Bunny deployment.

    Args:
        name: Registry name for the file.
        local_path: Absolute path to the local file.
        session_dir: Current session directory.
        description: Optional description.
        category: Optional category tag.
        global_scope: If True, save to global registry.

    Returns:
        Tuple of ``(BunnyFile, size_warning)`` where ``size_warning``
        is True if the file exceeds the 100 MB soft limit.

    Raises:
        ValueError: If name is invalid or already exists.
        FileNotFoundError: If local_path does not exist.
    """
    _validate_name(name)

    local_path = os.path.abspath(local_path)
    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"File not found: {local_path}")

    path = _global_files_file() if global_scope else os.path.join(_session_hak5_dir(session_dir), "files.json")

    existing = _load_files(path)
    if any(f.name == name for f in existing):
        raise ValueError(f"File '{name}' already registered. Use 'file rm' first to replace it.")

    size = os.path.getsize(local_path)
    sha = _file_sha256(local_path)
    filename = os.path.basename(local_path)

    # Check for duplicate filenames (basenames) — two files with the same
    # basename would overwrite each other on the device.
    for f in existing:
        if f.filename == filename:
            raise ValueError(
                f"Another file ('{f.name}') already uses the basename '{filename}'. "
                "Rename or copy the file to a unique name before registering."
            )

    bf = BunnyFile(
        name=name,
        local_path=local_path,
        filename=filename,
        description=description,
        category=category,
        size_bytes=size,
        sha256=sha,
    )
    existing.append(bf)
    _save_files(path, existing)

    size_warning = size > _SIZE_WARNING_BYTES
    return bf, size_warning


def remove_file(name: str, session_dir: str, *, global_scope: bool = False) -> None:
    """Unregister a file. Raises ValueError if not found."""
    _validate_name(name)

    path = _global_files_file() if global_scope else os.path.join(_session_hak5_dir(session_dir), "files.json")

    existing = _load_files(path)
    new_list = [f for f in existing if f.name != name]
    if len(new_list) == len(existing):
        raise ValueError(f"File '{name}' not found in {'global' if global_scope else 'session'} registry.")

    _save_files(path, new_list)


def file_names(session_dir: str) -> list[str]:
    """Return a sorted list of all registered file names."""
    return sorted(bf.name for bf, _ in list_files(session_dir))


def get_files_by_names(names: list[str], session_dir: str) -> list[BunnyFile]:
    """Look up multiple files by name. Raises ValueError if any not found."""
    result: list[BunnyFile] = []
    for name in names:
        entry = get_file(name, session_dir)
        if entry is None:
            raise ValueError(f"File '{name}' not found in registry.")
        result.append(entry[0])
    return result


def _human_size(size_bytes: int | float) -> str:
    """Format a byte count as a human-readable string."""
    value: float = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
