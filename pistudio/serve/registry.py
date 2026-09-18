"""Ephemeral in-memory payload registry for the injection server.

Payloads are stored only while the server is running and cleared on stop.
No persistence across shell restarts.
"""

import secrets
import string
import threading
from dataclasses import dataclass, field
from datetime import datetime

# Base62 alphabet for URL-safe slugs
_SLUG_ALPHABET = string.ascii_letters + string.digits


def generate_slug(length: int = 6) -> str:
    """Generate a random URL-safe slug."""
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(length))


@dataclass
class HostedPayload:
    """A payload hosted on the injection server."""

    slug: str
    text: str
    name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    # File hosting support
    content: bytes = field(default=b"")
    content_type: str = "text/plain"
    filename: str = ""

    @property
    def is_file(self) -> bool:
        """Return True if this is a binary file payload."""
        return len(self.content) > 0

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        d = {
            "slug": self.slug,
            "text": self.text,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }
        if self.is_file:
            d["is_file"] = True
            d["content_type"] = self.content_type
            d["filename"] = self.filename
            d["size"] = len(self.content)
        return d


class PayloadRegistry:
    """Thread-safe ephemeral registry for hosted payloads."""

    def __init__(self) -> None:
        self._payloads: dict[str, HostedPayload] = {}
        self._lock = threading.Lock()

    def add(
        self,
        text: str,
        name: str = "",
        slug: str = "",
    ) -> HostedPayload:
        """Add a payload and return the HostedPayload with its slug.

        Args:
            text: The payload text to host.
            name: Optional human-readable name.
            slug: Optional custom slug (auto-generated if empty).

        Returns:
            The created HostedPayload.

        Raises:
            ValueError: If the slug already exists.
        """
        with self._lock:
            if not slug:
                # Generate unique slug
                for _ in range(100):
                    slug = generate_slug()
                    if slug not in self._payloads:
                        break
                else:
                    raise RuntimeError("Failed to generate unique slug")

            if slug in self._payloads:
                raise ValueError(f"Slug '{slug}' already exists")

            payload = HostedPayload(slug=slug, text=text, name=name)
            self._payloads[slug] = payload
            return payload

    def add_file(
        self,
        content: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        name: str = "",
        slug: str = "",
    ) -> HostedPayload:
        """Add a file and return the HostedPayload with its slug.

        Args:
            content: The binary file content.
            filename: Original filename (used for Content-Disposition).
            content_type: MIME type of the file.
            name: Optional human-readable name.
            slug: Optional custom slug (auto-generated if empty).

        Returns:
            The created HostedPayload.

        Raises:
            ValueError: If the slug already exists.
        """
        with self._lock:
            if not slug:
                # Generate unique slug
                for _ in range(100):
                    slug = generate_slug()
                    if slug not in self._payloads:
                        break
                else:
                    raise RuntimeError("Failed to generate unique slug")

            if slug in self._payloads:
                raise ValueError(f"Slug '{slug}' already exists")

            payload = HostedPayload(
                slug=slug,
                text="",  # Empty for file payloads
                name=name or filename,
                content=content,
                content_type=content_type,
                filename=filename,
            )
            self._payloads[slug] = payload
            return payload

    def get(self, slug: str) -> HostedPayload | None:
        """Get a payload by slug, or None if not found."""
        with self._lock:
            return self._payloads.get(slug)

    def remove(self, slug: str) -> bool:
        """Remove a payload by slug. Returns True if removed, False if not found."""
        with self._lock:
            if slug in self._payloads:
                del self._payloads[slug]
                return True
            return False

    def list_all(self) -> list[HostedPayload]:
        """Return a list of all hosted payloads."""
        with self._lock:
            return list(self._payloads.values())

    def clear(self) -> int:
        """Clear all payloads. Returns the count of removed payloads."""
        with self._lock:
            count = len(self._payloads)
            self._payloads.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._payloads)


# ── Module-level singleton ────────────────────────────────────────

_registry: PayloadRegistry | None = None


def get_registry() -> PayloadRegistry:
    """Get or create the global payload registry."""
    global _registry
    if _registry is None:
        _registry = PayloadRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
