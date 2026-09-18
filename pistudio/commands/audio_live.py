"""Live acoustic delivery and the survival oracle, as ``audio live`` / ``audio verify``.

These were a separate ``acoustic`` command. Two top-level commands both
offering TTS and ``ultrasonic`` meant the same words did different things
depending on which you typed, so they merged: ``audio <format>`` writes a file,
``audio live <verb>`` plays into a room.

The split is by destination, which is the distinction that matters. A file
carrier attacks whatever opens the file; live playback attacks a microphone and
the transcript behind it, and the transcript is the sink that persists.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pistudio.commands.payload_flag import complete_payload_names, payload_text, resolve_payload_text
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

# Near-ultrasonic default: above most adult hearing, inside the passband of
# laptop and conference microphones.
DEFAULT_ULTRASONIC_HZ = 18500

LIVE_VERBS: dict[str, str] = {
    "devices": "List audio output devices",
    "say": "Speak a payload through an output device",
    "ultrasonic": "Play a payload as near-ultrasonic FSK",
    "plan": "Suggest delivery windows for a meeting length",
}

# Flags each live verb accepts, for completion and for rejecting the rest.
# --payload works wherever a payload is delivered, matching the file formats;
# `plan` takes one too, since --split needs something to split.
LIVE_FLAGS: dict[str, tuple[str, ...]] = {
    "devices": (),
    "say": ("--payload", "--device", "--voice", "--rate", "--encode", "--keep"),
    "ultrasonic": ("--payload", "--device", "--freq", "--encode", "--keep"),
    "plan": ("--payload", "--minutes", "--split"),
}

VERIFY_FLAGS = ("--payload", "--encode")


def _int_flag(shell: StudioProtocol, name: str, raw: str | None) -> int | None:
    """Parse an integer flag, reporting the problem and returning None."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        shell.out.error(f"{name} needs a whole number, got '{raw}'.")
        return None


def _print_hint(shell: StudioProtocol, style: str) -> None:
    """Print the playback install hint, escaping the extras bracket.

    Rich reads ``[acoustic]`` as a markup tag and drops it, which is precisely
    the part of the hint the reader needs.
    """
    from rich.markup import escape

    from pistudio.acoustic import install_hint

    for line in install_hint().splitlines():
        shell.console.print(f"  [{style}]{escape(line)}[/]")


def handle_live(shell: StudioProtocol, args: list[str]) -> None:
    """Dispatch ``audio live <verb>``."""
    if not args:
        shell.out.error(f"Give a verb: {', '.join(LIVE_VERBS)}. See 'help audio'.")
        return

    verb, rest = args[0].lower(), args[1:]
    handlers = {
        "devices": _devices,
        "say": lambda s, a: _play(s, a, ultrasonic=False),
        "ultrasonic": lambda s, a: _play(s, a, ultrasonic=True),
        "plan": _plan,
    }
    handler = handlers.get(verb)
    if handler is None:
        from pistudio.core.command import Command

        shell.out.error(Command.suggest_subcommand(verb, list(LIVE_VERBS)))
        return
    handler(shell, rest)


# ── devices ──────────────────────────────────────────────────────


def _devices(shell: StudioProtocol, args: list[str]) -> None:
    """List output-capable audio devices."""

    from pistudio.acoustic import PlaybackUnavailableError, list_devices, playback_available

    t = active_theme()
    if not playback_available():
        shell.out.warn("Live playback is unavailable.")
        _print_hint(shell, t.muted)
        return

    try:
        devices = list_devices()
    except PlaybackUnavailableError as e:
        shell.out.error(str(e))
        return

    if not devices:
        shell.out.warn("No output devices found.")
        return

    shell.out.table(
        ["#", "Name", "Ch", "Rate", "Default"],
        [
            [str(d.index), d.name, str(d.channels), f"{d.default_samplerate:.0f}", "yes" if d.is_default else ""]
            for d in devices
        ],
        title="Audio output devices",
        column_styles={
            "#": {"justify": "right", "style": t.accent},
            "Ch": {"justify": "right"},
            "Rate": {"justify": "right"},
        },
        json_rows=[
            {
                "index": d.index,
                "name": d.name,
                "channels": d.channels,
                "samplerate": d.default_samplerate,
                "default": d.is_default,
            }
            for d in devices
        ],
    )
    if shell.json_mode or shell.plain_mode:
        return
    shell.console.print(f'  [{t.muted}]Target one with: audio live say "<payload>" --device <#>[/]')


# ── say / ultrasonic ─────────────────────────────────────────────


def _play(shell: StudioProtocol, args: list[str], *, ultrasonic: bool) -> None:
    """Generate a carrier for the payload and play it."""
    import tempfile

    from pistudio.acoustic import PlaybackUnavailableError, playback_available
    from pistudio.commands.encode_apply import apply_encoding
    from pistudio.commands.flags import extract_flag, strip_flag

    verb = "ultrasonic" if ultrasonic else "say"

    # Validate before stripping: strip_flag removes the flag *and* its value, so
    # a later check sees nothing to reject and --freq on `say` silently played.
    if not _reject_unknown_flags(shell, args, LIVE_FLAGS[verb], f"audio live {verb}"):
        return

    chain = extract_flag(args, "--encode")
    args = strip_flag(args, "--encode")
    device_raw = extract_flag(args, "--device")
    args = strip_flag(args, "--device")
    voice = extract_flag(args, "--voice")
    args = strip_flag(args, "--voice")
    rate = extract_flag(args, "--rate")
    args = strip_flag(args, "--rate")
    freq_raw = extract_flag(args, "--freq")
    args = strip_flag(args, "--freq")
    keep = extract_flag(args, "--keep")
    args = strip_flag(args, "--keep")
    name = extract_flag(args, "--payload")
    args = strip_flag(args, "--payload")

    payload = resolve_payload_text(
        shell,
        [a for a in args if not a.startswith("--")],
        name,
        usage=f'Give a payload: audio live {verb} "<payload>" (or --payload <name>)',
    )
    if payload is None:
        return

    if chain:
        encoded = apply_encoding(shell, payload, chain)
        if encoded is None:
            return
        if not ultrasonic:
            shell.out.warn(
                "Encoded text is spoken as characters, not bytes: TTS will not reproduce invisible "
                "codepoints. Encoding suits ultrasonic (which carries bytes) and file carriers."
            )
        payload = encoded

    device = _int_flag(shell, "--device", device_raw)
    if device_raw is not None and device is None:
        return
    freq = _int_flag(shell, "--freq", freq_raw) or DEFAULT_ULTRASONIC_HZ
    if freq_raw is not None and freq is None:
        return

    out_path = keep or os.path.join(tempfile.mkdtemp(prefix="pistudio-acoustic-"), "payload.wav")
    try:
        if ultrasonic:
            from pistudio.files.audio import write_ultrasonic

            with shell.spinner("Generating ultrasonic carrier..."):
                write_ultrasonic(payload, out_path, freq_0=freq, freq_1=freq + 1000)
        else:
            from pistudio.files.audio import write_tts_wav

            with shell.spinner("Synthesising speech..."):
                write_tts_wav(payload, out_path, voice=voice, rate=rate)
    except ImportError as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Could not generate audio: {e}")
        return

    if not playback_available():
        shell.out.warn("Playback unavailable; the carrier was written instead.")
        shell.out.success(f"Wrote {out_path}")
        _print_hint(shell, active_theme().muted)
        return

    try:
        from pistudio.acoustic import play_wav

        with shell.spinner("Playing..."):
            duration = play_wav(out_path, device=device)
    except PlaybackUnavailableError as e:
        shell.out.error(str(e))
        return
    except Exception as e:
        shell.out.error(f"Playback failed: {e}")
        return

    shell.out.success(f"Played {duration:.1f}s" + (f" (kept at {out_path})" if keep else ""))
    shell.out.info('Verify with: audio verify <transcript> --payload "..."')


def _reject_unknown_flags(
    shell: StudioProtocol,
    args: list[str],
    accepted: tuple[str, ...],
    context: str,
) -> bool:
    """Report any flag *context* does not accept. Returns False when one is found.

    Silently ignoring a flag is how ``--freq`` on ``say`` looked like it worked
    while doing nothing, so an unrecognised flag is an error here too.
    """
    from pistudio.commands.flags import unknown_flag_message

    for arg in args:
        if arg.startswith("--") and arg not in accepted:
            shell.out.error(f"{unknown_flag_message(arg, accepted)} ({context})")
            return False
    return True


# ── plan ─────────────────────────────────────────────────────────


def _plan(shell: StudioProtocol, args: list[str]) -> None:
    """Suggest delivery windows, optionally splitting a payload across them."""
    from pistudio.acoustic import format_timecode, split_payload, suggest_windows
    from pistudio.commands.flags import extract_flag, strip_flag

    t = active_theme()
    if not _reject_unknown_flags(shell, args, LIVE_FLAGS["plan"], "audio live plan"):
        return

    minutes_raw = extract_flag(args, "--minutes")
    args = strip_flag(args, "--minutes")
    split_raw = extract_flag(args, "--split")
    args = strip_flag(args, "--split")
    name = extract_flag(args, "--payload")
    args = strip_flag(args, "--payload")

    minutes = _int_flag(shell, "--minutes", minutes_raw) or 30
    if minutes_raw is not None and minutes is None:
        return
    if minutes < 1:
        shell.out.error("--minutes must be at least 1.")
        return

    windows = suggest_windows(minutes)
    # A payload is optional here: `plan` alone just reports the windows, and
    # only --split needs something to divide, so this cannot use
    # resolve_payload_text (which reports an error when neither source is given).
    payload = " ".join(a for a in args if not a.startswith("--")).strip()
    if name:
        resolved = payload_text(shell, name)
        if resolved is None:
            return
        payload = resolved

    fragments: list[str] = []
    if split_raw is not None:
        parts = _int_flag(shell, "--split", split_raw)
        if parts is None:
            return
        if not payload:
            shell.out.error("--split needs a payload to split: give one inline or with --payload.")
            return
        try:
            fragments = split_payload(payload, min(parts, len(windows)))
        except ValueError as e:
            shell.out.error(str(e))
            return

    shell.console.print(f"\n  [{t.secondary}]Delivery windows for a {minutes}-minute meeting[/]")
    for i, (offset, why) in enumerate(windows):
        line = f"  [{t.accent}]{format_timecode(offset):>7}[/]  {why}"
        if i < len(fragments):
            line += f'\n           [{t.muted}]say:[/] "{fragments[i]}"'
        shell.console.print(line)

    shell.console.print(
        f"\n  [{t.muted}]Windows follow reported notetaker weighting (primacy, recency, and\n"
        f"  transition points). Advisory: the effect is from studies of commercial\n"
        f"  notetakers, not measured here.[/]\n"
    )


# ── verify ───────────────────────────────────────────────────────


def handle_verify(shell: StudioProtocol, args: list[str]) -> None:
    """Score whether a payload survived into a recovered artifact.

    Not acoustic-specific: the sink can be a transcript, a log line, or a
    scanned code's contents, so this sits at the top level of ``audio`` rather
    than under ``live``.
    """
    from pistudio.acoustic import score
    from pistudio.commands.flags import extract_flag, strip_flag

    t = active_theme()
    if not _reject_unknown_flags(shell, args, VERIFY_FLAGS, "audio verify"):
        return

    payload = extract_flag(args, "--payload")
    args = strip_flag(args, "--payload")
    chain = extract_flag(args, "--encode")
    args = strip_flag(args, "--encode")

    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        shell.out.error('Give the file to check: audio verify <file> --payload "<payload>"')
        return
    if not payload:
        shell.out.error('Give the payload to look for: --payload "<payload>"')
        return

    path = os.path.abspath(os.path.expanduser(positional[0]))
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            sink_text = fh.read()
    except OSError as e:
        shell.out.error(f"Could not read {path}: {e}")
        return

    # When the payload was encoded on the way in, look for the encoded form:
    # that is what the sink actually received.
    needle = payload
    if chain:
        encoded = apply_encoding_quiet(payload, chain)
        if encoded is None:
            shell.out.error(f"Unknown encoding chain '{chain}'.")
            return
        needle = encoded

    verdict = score(needle, sink_text)

    colour = {
        "verbatim": t.success,
        "mutated": t.success,
        "truncated": t.warning,
        "stripped": t.error,
        "absent": t.error,
    }.get(verdict.verdict, t.text)

    shell.console.print(f"\n  [{t.secondary}]Sink:[/] {path}")
    shell.console.print(f"  [{t.secondary}]Verdict:[/] [{colour}]{verdict.verdict}[/]")
    shell.console.print(f"  [{t.secondary}]Survived:[/] {'yes' if verdict.survived else 'no'}")
    shell.console.print(f"  [{t.secondary}]Similarity:[/] {verdict.similarity:.0%}")
    shell.console.print(f"  [{t.secondary}]Recovered:[/] {verdict.recovered_len} of {verdict.original_len} chars")
    if verdict.truncated_at is not None:
        shell.console.print(f"  [{t.secondary}]Truncated at:[/] {verdict.truncated_at} chars")
    if verdict.mutations:
        shell.console.print(f"  [{t.secondary}]Mutations:[/] {', '.join(verdict.mutations)}")
    shell.console.print()


def apply_encoding_quiet(text: str, chain: str) -> str | None:
    """Apply an encoding chain without printing, for verification lookups."""
    from pistudio.encoding import ChainError, apply_chain

    try:
        return apply_chain(text, chain)
    except ChainError:
        return None


# ── completion ───────────────────────────────────────────────────


def complete_live(shell: StudioProtocol, tokens: list[str]) -> list[str]:
    """Complete ``audio live ...`` tokens.

    *tokens* starts at the token after ``live``.
    """
    current = tokens[-1] if tokens else ""

    if len(tokens) <= 1:
        return [v for v in LIVE_VERBS if v.startswith(current)]

    verb = tokens[0].lower()
    previous = tokens[-2]

    if previous == "--payload":
        return complete_payload_names(shell, current)
    if previous == "--device":
        return _device_indices(current)
    if previous == "--voice":
        return [v for v in _VOICES if v.startswith(current)]
    if previous == "--rate":
        return [r for r in ("-25%", "-10%", "+10%", "+25%") if r.startswith(current)]
    if previous == "--freq":
        return [f for f in ("17000", "18000", "18500", "19000", "20000") if f.startswith(current)]
    if previous == "--minutes":
        return [m for m in ("15", "30", "45", "60", "90") if m.startswith(current)]
    if previous == "--split":
        return [s for s in ("2", "3", "4") if s.startswith(current)]
    if previous == "--keep":
        return []

    return [f for f in LIVE_FLAGS.get(verb, ()) if f.startswith(current)]


# A short list of edge-tts voices, matching what `audio --voice` suggests.
_VOICES = (
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
)


def _device_indices(current: str) -> list[str]:
    """Offer real output device indices when playback is available."""
    try:
        from pistudio.acoustic import list_devices, playback_available

        if not playback_available():
            return []
        return [str(d.index) for d in list_devices() if str(d.index).startswith(current)]
    except Exception:
        return []


def complete_verify(shell: StudioProtocol, tokens: list[str]) -> list[str]:
    """Complete ``audio verify ...`` tokens, starting after ``verify``."""
    current = tokens[-1] if tokens else ""
    if tokens and len(tokens) >= 2 and tokens[-2] == "--payload":
        return complete_payload_names(shell, current)
    return [f for f in VERIFY_FLAGS if f.startswith(current)]
