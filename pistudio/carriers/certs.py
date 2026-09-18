"""X.509 certificates as a payload carrier.

A certificate is an unusual injection surface because it is *quoted verbatim
into logs by infrastructure that has no idea it is quoting attacker text*. TLS
terminators, scanners and CI pipelines all write subject and SAN values into
log lines, dashboards and vulnerability reports -- and those reports are
increasingly summarised by an LLM.

The finding this module exists to measure is a capacity asymmetry. X.509 caps
the Common Name at 64 characters (RFC 5280's ub-common-name), which is where
every validator looks. A Subject Alternative Name carries far more, is where
modern TLS actually reads the hostname from, and is routinely logged with no
length check at all. The strictly-validated field is not the field to use.

Strictly offline. This builds and inspects certificates with the
``cryptography`` library and never opens a socket: no fetching a real
certificate, no submitting a CSR to a CA. A generated certificate here is
self-signed test material for a pipeline you own.
"""

from __future__ import annotations

import datetime
import ipaddress
import logging
from dataclasses import dataclass

from pistudio.carriers.types import Carrier, CarrierField

logger = logging.getLogger(__name__)

# RFC 5280 upper bounds. These are the DirectoryString ceilings on the fields
# that make up a subject Distinguished Name.
UB_COMMON_NAME = 64
UB_ORGANIZATION_NAME = 64
UB_ORGANIZATIONAL_UNIT_NAME = 64
UB_LOCALITY_NAME = 128
UB_STATE_NAME = 128
UB_EMAIL_ADDRESS = 255

# A SAN dNSName is an IA5String with no RFC 5280 upper bound; the practical
# ceiling is the certificate size a peer will accept. Treated as unbounded
# because the limit that bites first is never this one.
SAN_PRACTICAL_LIMIT = 0

X509_CARRIER = Carrier(
    name="x509",
    description="X.509 certificate subject and SAN fields",
    sink="TLS logs, scanner reports, CI output",
    threat_level="documented",
    fields=(
        CarrierField(
            "san_dns",
            "SAN dNSName",
            SAN_PRACTICAL_LIMIT,
            notes="No RFC 5280 upper bound. Where modern TLS reads the hostname, and routinely logged unchecked.",
        ),
        CarrierField(
            "common_name",
            "Subject CN",
            UB_COMMON_NAME,
            notes="RFC 5280 ub-common-name. The field every validator checks, so the worst one to use.",
        ),
        CarrierField(
            "organization",
            "Subject O",
            UB_ORGANIZATION_NAME,
            notes="Shown in certificate viewers, so a human may read it.",
        ),
        CarrierField(
            "organizational_unit",
            "Subject OU",
            UB_ORGANIZATIONAL_UNIT_NAME,
            notes="Free text by convention; rarely validated beyond length.",
        ),
        CarrierField("locality", "Subject L", UB_LOCALITY_NAME),
        CarrierField("state", "Subject ST", UB_STATE_NAME),
        CarrierField(
            "email",
            "Subject emailAddress",
            UB_EMAIL_ADDRESS,
            restricted_charset=True,
            notes="Deprecated in the subject DN but still emitted; charset is constrained.",
        ),
    ),
    notes="Self-signed generation only. This module never opens a network connection.",
)


class CertError(ValueError):
    """Raised when a payload cannot be carried, or a certificate cannot be built."""


@dataclass(frozen=True, slots=True)
class FieldFit:
    """Whether one field can carry a payload, and with how much room to spare."""

    field: CarrierField
    fits: bool
    measured: int
    headroom: int

    @property
    def name(self) -> str:
        """The field's name, for terse reporting."""
        return self.field.name


@dataclass(frozen=True, slots=True)
class CapacityReport:
    """Which certificate fields carry a payload, and which truncate it."""

    payload_length: int
    payload_bytes: int
    fits: tuple[FieldFit, ...]
    misses: tuple[FieldFit, ...]

    @property
    def any_fit(self) -> bool:
        """Whether at least one field can carry the payload whole."""
        return bool(self.fits)

    @property
    def best(self) -> FieldFit | None:
        """The roomiest field that fits, or None when nothing does."""
        return self.fits[0] if self.fits else None

    @property
    def cn_fits(self) -> bool:
        """Whether the strictly-validated Common Name carries it.

        Called out on its own because the CN-versus-SAN gap is the point: a
        payload that misses here but fits a SAN is the documented finding.
        """
        return any(f.name == "common_name" for f in self.fits)


def analyse(payload: str, carrier: Carrier = X509_CARRIER) -> CapacityReport:
    """Report which of *carrier*'s fields can carry *payload*.

    No certificate is built and nothing is written. This is the question to
    ask before spending a real test on a payload that could never have fitted.

    Args:
        payload: The text to carry.
        carrier: The carrier to measure against, defaulting to X.509.

    Returns:
        The fields that fit, roomiest first, and those that do not.

    Raises:
        CertError: If *payload* is empty.
    """
    if not payload:
        raise CertError("Payload is empty; there is nothing to measure.")

    fits: list[FieldFit] = []
    misses: list[FieldFit] = []
    for f in carrier.fields:
        entry = FieldFit(f, f.fits(payload), f.measure(payload), f.headroom(payload))
        (fits if entry.fits else misses).append(entry)

    # Roomiest first: unbounded fields, then by remaining headroom.
    fits.sort(key=lambda e: (not e.field.unbounded, -e.headroom))
    # Closest miss first, so the report leads with the near-miss worth trimming for.
    misses.sort(key=lambda e: -e.headroom)
    return CapacityReport(len(payload), len(payload.encode("utf-8")), tuple(fits), tuple(misses))


def _require_cryptography():
    """Import the cryptography x509 modules, or explain what to install."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover - cryptography is a base dep
        raise CertError("The cryptography package is required: pip install 'cryptography>=42,<47'") from exc
    return x509, hashes, serialization, rsa, NameOID


def _san_value(payload: str, x509_mod):
    """Build a SAN entry for *payload*.

    A dNSName is the interesting case, but the payload is rarely a legal
    hostname. Certificates in the wild carry illegal dNSNames all the time and
    loggers print them regardless, which is precisely the point -- so this does
    not sanitise the payload into legality.
    """
    try:
        ipaddress.ip_address(payload)
    except ValueError:
        return x509_mod.DNSName(payload)
    # A bare IP belongs in an iPAddress SAN; a dNSName holding one is rejected
    # by strict parsers, which would waste the test.
    return x509_mod.IPAddress(ipaddress.ip_address(payload))


def _build_subject(payload: str, target_field: str, common_name: str, x509_mod, name_oid):
    """Assemble the subject DN, placing *payload* in *target_field*.

    Every field except the target gets ordinary-looking filler so the
    certificate does not read as obviously synthetic.
    """
    oids = {
        "common_name": name_oid.COMMON_NAME,
        "organization": name_oid.ORGANIZATION_NAME,
        "organizational_unit": name_oid.ORGANIZATIONAL_UNIT_NAME,
        "locality": name_oid.LOCALITY_NAME,
        "state": name_oid.STATE_OR_PROVINCE_NAME,
        "email": name_oid.EMAIL_ADDRESS,
    }
    cn_value = payload if target_field == "common_name" else common_name
    attributes = [x509_mod.NameAttribute(name_oid.COMMON_NAME, cn_value)]
    if target_field in oids and target_field != "common_name":
        attributes.append(x509_mod.NameAttribute(oids[target_field], payload))
    return x509_mod.Name(attributes)


def generate(
    payload: str,
    path: str,
    *,
    target_field: str = "san_dns",
    common_name: str = "example.com",
    days_valid: int = 365,
    key_size: int = 2048,
) -> str:
    """Write a self-signed certificate carrying *payload*, and return its path.

    Offline by construction: the certificate is self-signed, so no CA is
    contacted and no socket is opened. It is test material for a pipeline you
    control, not a credential anything should trust.

    Args:
        payload: The text to carry.
        path: Where to write the PEM certificate.
        target_field: Which carrier field carries the payload. Defaults to
            ``san_dns``, the roomiest and least-validated.
        common_name: CN used when the payload goes somewhere else, so the
            certificate still looks routine.
        days_valid: Validity window in days.
        key_size: RSA key size in bits.

    Returns:
        The path written.

    Raises:
        CertError: If the payload does not fit the chosen field, the field is
            unknown, or the parameters are unusable.
    """
    if not payload:
        raise CertError("Payload is empty; there is nothing to carry.")

    spec = X509_CARRIER.get_field(target_field)
    if spec is None:
        known = ", ".join(f.name for f in X509_CARRIER.fields)
        raise CertError(f"Unknown certificate field '{target_field}'. Known: {known}")

    if not spec.fits(payload):
        # Names the field, not a CLI flag: this is library code, and the flag
        # that reaches it has already been renamed once.
        raise CertError(
            f"Payload is {spec.measure(payload)} {spec.unit} but {spec.label} holds {spec.max_length}. "
            f"Use the san_dns field, which has no upper bound."
        )

    if days_valid < 1:
        raise CertError(f"days_valid must be at least 1, got {days_valid}.")
    # Below 2048 the library refuses outright on modern versions; check here so
    # the error names the parameter rather than surfacing a backend exception.
    if key_size < 1024:
        raise CertError(f"key_size must be at least 1024, got {key_size}.")

    x509_mod, hashes, serialization, rsa, name_oid = _require_cryptography()

    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    subject = _build_subject(payload, target_field, common_name, x509_mod, name_oid)

    # Fixed clock reference: the certificate is deterministic test material and
    # a UTC-aware window keeps it valid regardless of the host's timezone.
    now = datetime.datetime.now(datetime.UTC)

    builder = (
        x509_mod.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509_mod.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=days_valid))
    )

    san_entries = [_san_value(payload, x509_mod)] if target_field == "san_dns" else [x509_mod.DNSName(common_name)]
    builder = builder.add_extension(x509_mod.SubjectAlternativeName(san_entries), critical=False)

    certificate = builder.sign(key, hashes.SHA256())

    pem = certificate.public_bytes(serialization.Encoding.PEM)
    with open(path, "wb") as handle:
        handle.write(pem)

    logger.debug("wrote self-signed certificate carrying payload in %s to %s", target_field, path)
    return path


def read_payload(path: str, target_field: str = "san_dns") -> str:
    """Recover the payload from a certificate written by :func:`generate`.

    The survival oracle's sink-side read: what a parser actually recovers,
    which is not always what was written.

    Args:
        path: PEM certificate to read.
        target_field: Field the payload was placed in.

    Returns:
        The recovered value, or "" when the field is absent.

    Raises:
        CertError: If the file cannot be parsed as a certificate.
    """
    x509_mod, _, _, _, name_oid = _require_cryptography()

    try:
        with open(path, "rb") as handle:
            certificate = x509_mod.load_pem_x509_certificate(handle.read())
    except (ValueError, OSError) as exc:
        raise CertError(f"Could not read a certificate from {path}: {exc}") from exc

    if target_field == "san_dns":
        try:
            san = certificate.extensions.get_extension_for_class(x509_mod.SubjectAlternativeName)
        except x509_mod.ExtensionNotFound:
            return ""
        names = san.value.get_values_for_type(x509_mod.DNSName)
        if names:
            return names[0]
        addresses = san.value.get_values_for_type(x509_mod.IPAddress)
        return str(addresses[0]) if addresses else ""

    oids = {
        "common_name": name_oid.COMMON_NAME,
        "organization": name_oid.ORGANIZATION_NAME,
        "organizational_unit": name_oid.ORGANIZATIONAL_UNIT_NAME,
        "locality": name_oid.LOCALITY_NAME,
        "state": name_oid.STATE_OR_PROVINCE_NAME,
        "email": name_oid.EMAIL_ADDRESS,
    }
    oid = oids.get(target_field)
    if oid is None:
        known = ", ".join(f.name for f in X509_CARRIER.fields)
        raise CertError(f"Unknown certificate field '{target_field}'. Known: {known}")

    attributes = certificate.subject.get_attributes_for_oid(oid)
    return str(attributes[0].value) if attributes else ""
