"""Prompt Injection Studio — create, host, and deliver prompt injection payloads.

Three subsystems, usable as a library or through the ``pistudio`` CLI:

- :mod:`pistudio.serve` — host payloads over HTTP/HTTPS, optionally via ngrok
- :mod:`pistudio.files` — embed payloads in 50+ file formats, barcodes and audio
- :mod:`pistudio.hardware` — deliver via Flipper Zero, Hak5 devices,
  Ubertooth and a USB-TTL serial console

For authorised security testing only.
"""

__version__ = "0.1.0"

__all__ = ["Studio", "TargetContext", "__version__"]


def __getattr__(name: str) -> object:
    """Lazily expose the top-level API without importing Rich at module load."""
    if name in ("Studio", "TargetContext"):
        from pistudio.core import studio

        return getattr(studio, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
