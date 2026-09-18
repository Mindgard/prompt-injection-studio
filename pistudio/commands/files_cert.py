"""Certificate generation with explicit options, for ``file cert``.

The registry's ``write_cert`` honours the plain ``(text, path)`` writer
signature and defaults everything, so this is only reached when an override is
given. Mirrors ``files_anamorph`` -- the established home for a format whose
flags do not fit the writer signature.

Offline by construction: the certificate is self-signed, so no CA is contacted
and no socket is opened.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


def _int_option(shell: StudioProtocol, name: str, raw: str | None) -> int | None:
    """Parse an integer option, reporting the problem and returning None."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        shell.out.error(f"{name} needs a whole number, got '{raw}'.")
        return None


def write_cert_with_options(
    shell: StudioProtocol,
    text: str,
    path: str,
    field: str | None,
    common_name: str | None,
    days: str | None,
    key_size: str | None,
) -> None:
    """Write a self-signed certificate carrying *text*, honouring the overrides."""
    from pistudio.carriers.certs import CertError, generate

    t = active_theme()

    days_valid = _int_option(shell, "--days", days)
    if days is not None and days_valid is None:
        return
    bits = _int_option(shell, "--key-size", key_size)
    if key_size is not None and bits is None:
        return

    target = field or "san_dns"
    try:
        written = generate(
            text,
            path,
            target_field=target,
            common_name=common_name or "example.com",
            days_valid=days_valid or 365,
            key_size=bits or 2048,
        )
    except CertError as exc:
        shell.out.error(str(exc))
        return
    except OSError as exc:
        shell.out.error(f"Could not write {path}: {exc}")
        return

    shell.out.success(f"Payload written to: {written}")
    shell.console.print(f"  [{t.muted}]Payload in: {target} ({len(text)} chars)[/]")
    shell.console.print(f"  [{t.muted}]Self-signed and offline; trust nothing with it[/]")
    shell.audit.log("inject_certificate", path=written, field=target)


def cert_field_names() -> list[str]:
    """X.509 fields a payload can be placed in, roomiest first.

    Used for ``--cert-field`` completion, so the SAN -- which has no length
    bound and is the documented finding -- is offered before the capped CN.
    """
    from pistudio.carriers import X509_CARRIER

    return [f.name for f in X509_CARRIER.fields]
