"""FileFormat descriptor dataclass used by the format registry."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileFormat:
    """Describes a supported output file format."""

    name: str  # e.g. "pdf"
    extension: str  # e.g. ".pdf"
    description: str  # e.g. "PDF document"
    requires: str  # pip package name or "" for stdlib
    writer: Callable[[str, str], None]  # (prompt_text, output_path) -> None
    human_readable: bool  # True for txt, md, csv, html
    supports_metadata: bool  # True for png, jpg
    group: str = ""  # pip extra group, e.g. "embed-audio"
    category: str = ""  # for grouped display in `file list`
    threat_level: str = ""  # "documented" or "exploratory"
    # Routed to `inject audio` rather than `inject file`.  Declared per format
    # rather than inferred from `category`, because category drives display
    # grouping: adversarial-audio shows under "Adversarial" beside the image
    # attack anamorph, but is still an audio payload.
    audio: bool = False
