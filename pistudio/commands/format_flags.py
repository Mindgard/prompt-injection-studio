"""The flags ``file`` and ``audio`` accept, and which formats each reaches.

``generate_file`` parses every specialised flag for every format, so before
this table ``file pdf --voice en-US-GuyNeural`` was accepted and the voice
silently discarded.  Each entry names the formats a flag actually reaches;
anything scoped :data:`~pistudio.core.flags.ALL_SCOPES` is general.

This is now a :class:`~pistudio.core.flags.Flag` spec rather than a bare
scope table, so one declaration also supplies the completion description and
the usage ``Options:`` block.  Nine flags here -- ``--encode``, ``--voice``,
``--carrier``, ``--encrypt``, ``--engine``, ``--freq``, ``--model``, ``--rate``
and ``--volume`` -- were parsed by ``file`` while appearing in neither its
usage nor its completion, so they were working features nobody could find.
``FLAG_SCOPES`` is derived from the spec for the callers that still want the
old shape.
"""

from __future__ import annotations

from pistudio.core.flags import ALL_SCOPES, Flag

__all__ = [
    "ALL_FORMATS",
    "AUDIO_FLAGS",
    "FILE_FLAGS",
    "FLAG_SCOPES",
    "SHARED_FLAGS",
    "explain_unsupported",
    "unsupported_flags",
]

_TTS = ("tts-wav", "tts-whisper", "tts-concat")
_MIXED = ("tts-whisper", "ultrasonic", "audio-stego", "adversarial-audio")
_VOLUME = ("tts-whisper", "ultrasonic", "audio-stego")

# Kept as the historic name for the sentinel; ``ALL_SCOPES`` is the same value.
ALL_FORMATS = ALL_SCOPES

#: Payload sourcing and destination, accepted by every format in both commands.
SHARED_FLAGS: tuple[Flag, ...] = (
    Flag("--payload", value="name", help="Use a named payload from the library", completes="payload"),
    Flag("--edit", help="Compose the prompt in $EDITOR"),
    Flag("--generate", value="desc", help="LLM-generate the prompt from a description"),
    Flag("--output", short="-o", value="path", help="Write to this path instead of the default", completes="path"),
    Flag("--url", help="Also host the result on the payload server"),
    Flag("--encode", value="chain", help="Apply an encoding chain before the carrier"),
)

#: Audio-format flags.  Shared, because ``file`` still routes audio formats
#: through the same writer even though ``audio`` is where they are documented.
_AUDIO_SPECIALISED: tuple[Flag, ...] = (
    # Text-to-speech synthesis.
    Flag(
        "--engine",
        value="name",
        help="TTS engine: edge, gtts, pyttsx3, openai",
        scope=_TTS,
        scope_label="the TTS formats",
    ),
    Flag("--voice", value="name", help="Voice name, engine-specific", scope=_TTS, scope_label="the TTS formats"),
    Flag("--rate", value="+/-N%", help="Speech rate adjustment", scope=_TTS, scope_label="the TTS formats"),
    # Mixing a payload into an existing recording.
    Flag(
        "--carrier",
        value="path",
        help="Recording to hide the payload inside",
        scope=_MIXED,
        scope_label="the formats that mix into a carrier recording",
        completes="path",
    ),
    Flag(
        "--volume",
        value="float",
        help="Injection level, 0.0-1.0 (default 0.05 for whisper)",
        scope=_VOLUME,
        scope_label="the carrier-mixing formats",
    ),
    # Ultrasonic FSK.
    Flag(
        "--freq", value="Hz", help="Carrier frequency (default 18500)", scope=("ultrasonic",), scope_label="ultrasonic"
    ),
    Flag("--encrypt", help="AES-256 encrypt the payload", scope=("ultrasonic",), scope_label="ultrasonic"),
    Flag(
        "--key",
        value="string",
        help="Encryption key (generated if omitted)",
        scope=("ultrasonic",),
        scope_label="ultrasonic",
    ),
    # Adversarial ASR perturbation.
    Flag(
        "--model",
        value="name",
        help="Target ASR: whisper (default), deepspeech",
        scope=("adversarial-audio",),
        scope_label="adversarial-audio",
    ),
)

#: Flags for the non-audio carriers, which only ``file`` can produce.
_FILE_SPECIALISED: tuple[Flag, ...] = (
    # Adversarial image scaling.
    Flag("--decoy", value="image", help="Cover image", scope=("anamorph",), scope_label="anamorph", completes="path"),
    Flag(
        "--algorithm",
        value="alg",
        help="Downscaling algorithm: nearest, bicubic, bilinear",
        scope=("anamorph",),
        scope_label="anamorph",
    ),
    Flag(
        "--lambda",
        value="float",
        help="Mean-preservation weight (default 0.25)",
        scope=("anamorph",),
        scope_label="anamorph",
    ),
    Flag(
        "--target-size",
        value="WxH",
        help="Hidden payload resolution (default 256x256)",
        scope=("anamorph",),
        scope_label="anamorph",
    ),
    # X.509 certificate placement.
    Flag(
        "--cert-field",
        value="name",
        help="Field carrying the payload (default san_dns)",
        scope=("cert",),
        scope_label="cert",
    ),
    Flag(
        "--cn", value="name", help="Common Name when the payload rides elsewhere", scope=("cert",), scope_label="cert"
    ),
    Flag("--days", value="n", help="Validity window in days (default 365)", scope=("cert",), scope_label="cert"),
    Flag("--key-size", value="bits", help="RSA key size (default 2048)", scope=("cert",), scope_label="cert"),
)

#: Printing, available wherever a file is produced.
_PRINTING: tuple[Flag, ...] = (
    Flag("--print", help="Send the generated file to the default printer"),
    Flag("--printer", value="name", help="Print to a named printer"),
    Flag("--copies", value="n", help="Number of copies"),
    Flag("--media", value="size", help="Page or label size, e.g. A4 or Custom.62x100mm"),
)

#: Everything ``file`` accepts.
FILE_FLAGS: tuple[Flag, ...] = (
    *SHARED_FLAGS,
    Flag("--output-dir", value="dir", help="For 'all': directory to write the batch into", completes="path"),
    Flag("--metadata", help="For images: embed in metadata instead of rendered text"),
    Flag("--documented-only", help="For 'all': only generate documented attack vectors"),
    *_AUDIO_SPECIALISED,
    *_FILE_SPECIALISED,
    *_PRINTING,
)

#: Everything ``audio`` accepts, including the ``live`` and ``verify`` verbs.
AUDIO_FLAGS: tuple[Flag, ...] = (
    *SHARED_FLAGS,
    *_AUDIO_SPECIALISED,
    Flag("--device", value="n", help="Output device index (live)"),
    Flag("--keep", value="path", help="Keep the generated WAV (live)", completes="path"),
    Flag("--minutes", value="n", help="Meeting length (live plan, default 30)"),
    Flag("--split", value="n", help="Split the payload across n windows (live plan)"),
)

# flag -> (formats it applies to, human-readable description of that set).
# Derived so the two cannot drift; several call sites still read this shape.
FLAG_SCOPES: dict[str, tuple[tuple[str, ...], str]] = {
    f.name: (f.scope, f.scope_label or ", ".join(f.scope))
    for f in (*_AUDIO_SPECIALISED, *_FILE_SPECIALISED, *SHARED_FLAGS)
    if f.scope_label or f.scope != ALL_SCOPES
}
FLAG_SCOPES["--encode"] = (ALL_FORMATS, "every format")


def unsupported_flags(format_name: str, args: list[str]) -> list[str]:
    """Return the flags in *args* that do not apply to *format_name*.

    Args:
        format_name: The format the user asked for, e.g. ``"pdf"``.
        args: The raw argument list, before any flag stripping.

    Returns:
        The offending flag names, in the order they appear in *args*, with
        duplicates removed.
    """
    seen: list[str] = []
    for arg in args:
        if arg not in FLAG_SCOPES or arg in seen:
            continue
        scope = FLAG_SCOPES[arg][0]
        if scope == ALL_FORMATS:
            continue
        if format_name not in scope:
            seen.append(arg)
    return seen


def explain_unsupported(format_name: str, flags: list[str]) -> str:
    """Build the error message for flags that do not apply to *format_name*."""
    if len(flags) == 1:
        flag = flags[0]
        _, applies_to = FLAG_SCOPES[flag]
        return f"{flag} does not apply to '{format_name}'; it is for {applies_to}."

    parts = [f"{f} (for {FLAG_SCOPES[f][1]})" for f in flags]
    return f"These flags do not apply to '{format_name}': {', '.join(parts)}."
