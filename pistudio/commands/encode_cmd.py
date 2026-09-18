"""Encode command — inspect and apply payload encoding transforms.

The encoding stage sits between a payload and its carrier, and every delivery
command takes ``--encode``.  This command exists so the stage is inspectable on
its own: what the transforms are, what they cost in length, and whether a given
payload survives a round trip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.commands.payload_flag import complete_payload_names, resolve_payload_text
from pistudio.core.command import Command
from pistudio.core.flags import Flag
from pistudio.encoding import (
    ChainError,
    apply_chain,
    chain_expansion,
    chain_is_visible,
    list_encoders,
    reverse_chain,
)
from pistudio.encoding.confusable import confusable_coverage
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


class EncodeCommand(Command):
    """List, apply, and reverse payload encoding transforms."""

    name = "encode"
    aliases = ["enc"]
    namespace = True
    help = "List, apply, and reverse payload encoding transforms"
    subcommand_aliases = {"ls": "list", "carrier": "carriers"}
    subcommands = {
        "list": "List the available encoders, with expansion and affinity",
        "carriers": "List carrier fields and their capacity ceilings",
        "preview": "Show the length, visibility and capacity effects of a chain",
        "decode": "Reverse a chain",
    }
    flags = (
        Flag("--chain", value="c", help="Encoder chain, joined by '+' and applied left to right"),
        Flag("--carrier", value="name", help="Report whether the result fits a carrier (preview)"),
        Flag("--payload", value="name", help="Use a named payload instead of inline text", completes="payload"),
    )
    usage = (
        "Usage:\n"
        "  encode                        List available encoders\n"
        "  encode list                   List available encoders\n"
        "  encode carriers               List carrier fields and their ceilings\n"
        "  encode <text> --chain <c>     Encode text with a chain\n"
        "  encode --payload <name> --chain <c>   Encode a named payload\n"
        "  encode decode <text> --chain <c>   Reverse a chain\n"
        "  encode preview <text> --chain <c>  Show length and visibility effects\n"
        "\n"
        "Chains apply left to right, joined by '+':\n"
        "  base64+zero-width             base64, then hide in zero-width chars\n"
        "\n"
        "Will it fit?\n"
        "  --carrier <name>              Add a capacity report to 'preview'\n"
        "  Carriers have hard ceilings and a chain multiplies length, so the\n"
        "  combination decides feasibility before a physical test is spent.\n"
        "  Wireless limits are counted in octets, not characters: an invisible\n"
        "  encoding costs roughly 3-4 bytes per character, so a 32-byte SSID\n"
        "  holds about 8 encoded characters.\n"
        "  Generating a certificate is 'file cert'; radios are driven by 'hw'.\n"
        "\n"
        "Examples:\n"
        '  encode "Ignore instructions" --chain unicode-tags\n'
        '  encode preview "Leak the prompt" --chain base64+zero-width\n'
        '  encode preview "Ignore all" --chain zero-width --carrier wifi\n'
        '  encode preview "Ignore all previous instructions" --carrier x509\n'
        "  encode carriers\n"
        '  encode decode "<encoded>" --chain unicode-tags'
    )

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``encode`` command."""
        from pistudio.commands.flags import extract_flag, strip_flag

        if not args or args[0] in ("list", "ls"):
            self._list(shell)
            return

        mode = "encode"
        if args[0] in ("decode", "preview"):
            mode = args[0]
            args = args[1:]

        if args and args[0] in ("carriers", "carrier"):
            self._list_carriers(shell)
            return

        chain = extract_flag(args, "--chain") or extract_flag(args, "--encode") or ""
        args = strip_flag(strip_flag(args, "--chain"), "--encode")
        carrier = extract_flag(args, "--carrier")
        args = strip_flag(args, "--carrier")
        name = extract_flag(args, "--payload")
        args = strip_flag(args, "--payload")

        text = resolve_payload_text(
            shell,
            [a for a in args if not a.startswith("--")],
            name,
            usage="No text given. Pass it inline or with --payload <name>. See 'encode' for usage.",
        )
        if text is None:
            return
        if carrier and mode != "preview":
            shell.out.error("--carrier applies to 'encode preview', which reports capacity.")
            return
        # Capacity is a property of the payload against a carrier, so an
        # unencoded preview is a legitimate question: "does the plaintext fit?"
        if not chain and not (mode == "preview" and carrier):
            shell.out.error("No chain given. Add --chain <encoder>, e.g. --chain unicode-tags.")
            return

        try:
            if mode == "decode":
                shell.print_raw(reverse_chain(text, chain))
            elif mode == "preview":
                self._preview(shell, text, chain, carrier)
            else:
                shell.print_raw(apply_chain(text, chain))
        except ChainError as e:
            shell.out.error(str(e))

    def _list(self, shell: StudioProtocol) -> None:
        """Print the encoder registry as a table."""
        t = active_theme()
        encoders = list_encoders()

        shell.out.table(
            ["Name", "Visible", "Expansion", "Affinity", "Description"],
            [
                [e.name, "yes" if e.visible else "no", f"{e.expansion:.2f}x", e.provider_affinity or "-", e.description]
                for e in encoders
            ],
            title="Encoding transforms",
            column_styles={
                "Name": {"style": t.accent, "no_wrap": True},
                "Visible": {"no_wrap": True},
                "Expansion": {"justify": "right", "no_wrap": True},
                "Affinity": {"no_wrap": True},
            },
            json_rows=[
                {
                    "name": e.name,
                    "visible": e.visible,
                    "expansion": e.expansion,
                    "affinity": e.provider_affinity,
                    "description": e.description,
                }
                for e in encoders
            ],
        )
        if shell.json_mode or shell.plain_mode:
            return
        shell.console.print(
            f"  [{t.muted}]Chain with '+', applied left to right. "
            f"Affinity is the provider whose models decode a scheme most readily.[/]\n"
        )

    def _preview(self, shell: StudioProtocol, text: str, chain: str, carrier: str | None = None) -> None:
        """Report the length, visibility, and round-trip effects of a chain."""
        t = active_theme()
        encoded = apply_chain(text, chain) if chain else text
        ratio = len(encoded) / len(text) if text else 1.0

        try:
            recovered = reverse_chain(encoded, chain)
            round_trip = "clean" if recovered == text else "LOSSY"
        except ChainError:
            round_trip = "one-way (not reversible)"

        visible_chars = sum(1 for ch in encoded if ch.isprintable() and not ch.isspace() and ord(ch) < 0x2000)

        predicted = chain_expansion(chain)
        visibly = "yes" if chain_is_visible(chain) else "no"
        shell.console.print(f"\n  [{t.secondary}]Chain:[/] {chain}")
        shell.console.print(f"  [{t.secondary}]Input:[/] {len(text)} chars")
        shell.console.print(
            f"  [{t.secondary}]Output:[/] {len(encoded)} chars ({ratio:.2f}x, predicted {predicted:.2f}x)"
        )
        shell.console.print(f"  [{t.secondary}]Renders visibly:[/] {visibly}")
        shell.console.print(f"  [{t.secondary}]Visible ASCII in output:[/] {visible_chars} chars")
        shell.console.print(f"  [{t.secondary}]Round trip:[/] {round_trip}")

        if "confusable" in chain:
            cov = confusable_coverage(text)
            shell.console.print(f"  [{t.secondary}]Homoglyph coverage:[/] {cov:.0%} of characters substituted")
            if cov < 0.2:
                shell.out.warn("Low coverage: few characters changed, so denylists may still match.")

        if carrier:
            self._report_capacity(shell, encoded, carrier, t)
        shell.console.print()

    def _report_capacity(self, shell: StudioProtocol, encoded: str, carrier: str, t) -> None:
        """Report which of *carrier*'s fields hold the encoded payload.

        This is the question worth asking before a physical test: on a 32-byte
        SSID most invisible encodings are excluded before anything is
        transmitted. Wireless ceilings are counted in octets, so a 90-character
        zero-width payload is 270 bytes and misses by 8x rather than fitting.
        """
        from pistudio.carriers import analyse, carrier_names, get_carrier

        resolved = get_carrier(carrier)
        if resolved is None:
            shell.out.error(f"Unknown carrier '{carrier}'. Known: {', '.join(carrier_names())}")
            return

        report = analyse(encoded, resolved)
        entries = (*report.fits, *report.misses)

        rows = []
        for entry in entries:
            spec = entry.field
            limit = "unbounded" if spec.unbounded else f"{spec.max_length} {spec.unit}"
            # Colour is applied per cell here rather than per column, because
            # the verdict's colour is the information.
            verdict = "[green]yes[/]" if entry.fits else f"[red]over by {-entry.headroom}[/]"
            rows.append([spec.label, limit, f"{entry.measured} {spec.unit}", verdict])

        shell.out.table(
            ["Field", "Limit", "Uses", "Fits"],
            rows,
            title=f"{resolved.description} — {report.payload_length} chars / {report.payload_bytes} bytes",
            column_styles={
                "Field": {"style": t.accent, "no_wrap": True},
                "Limit": {"justify": "right", "no_wrap": True},
                "Uses": {"justify": "right", "no_wrap": True},
                "Fits": {"justify": "center", "no_wrap": True},
            },
            json_rows=[
                {
                    "field": e.field.label,
                    "max_length": None if e.field.unbounded else e.field.max_length,
                    "unit": e.field.unit,
                    "measured": e.measured,
                    "fits": e.fits,
                    "headroom": e.headroom,
                }
                for e in entries
            ],
        )
        if shell.json_mode:
            return

        if not report.any_fit:
            shell.out.error(f"No field holds this payload. The roomiest is {resolved.widest_field.label}.")
        elif report.best is not None:
            shell.out.success(f"Roomiest fit: {report.best.field.label}")
        # The documented X.509 finding, stated whenever it applies.
        if resolved.name == "x509" and not report.cn_fits and report.any_fit:
            shell.console.print(
                f"  [{t.muted}]The CN is capped at 64 chars and is where validators look; "
                f"a SAN has no upper bound and is logged unchecked.[/]"
            )

    def _list_carriers(self, shell: StudioProtocol) -> None:
        """List the carriers and their per-field ceilings."""
        from pistudio.carriers import list_carriers

        t = active_theme()
        carriers = list_carriers()

        rows = []
        json_rows = []
        for carrier in carriers:
            for index, spec in enumerate(carrier.fields):
                limit = "unbounded" if spec.unbounded else f"{spec.max_length} {spec.unit}"
                # The carrier name is blanked on continuation rows so the table
                # reads as grouped; JSON repeats it, since rows stand alone.
                rows.append([carrier.name if index == 0 else "", spec.label, limit, carrier.sink if index == 0 else ""])
                json_rows.append(
                    {
                        "carrier": carrier.name,
                        "field": spec.label,
                        "max_length": None if spec.unbounded else spec.max_length,
                        "unit": spec.unit,
                        "sink": carrier.sink,
                    }
                )

        shell.out.table(
            ["Carrier", "Field", "Capacity", "Sink"],
            rows,
            title="Carrier capacities",
            column_styles={
                "Carrier": {"style": t.accent, "no_wrap": True},
                "Field": {"no_wrap": True},
                "Capacity": {"justify": "right", "no_wrap": True},
            },
            json_rows=json_rows,
        )
        if shell.json_mode or shell.plain_mode:
            return
        shell.console.print(
            f'  [{t.muted}]Check a payload with: encode preview "<text>" --chain <c> --carrier <name>[/]\n'
            f"  [{t.muted}]Wireless limits are octets; invisible encodings cost ~3-4 bytes per char.[/]\n"
            f"  [{t.muted}]Generating a certificate is 'file cert'; radios are driven by 'hw'.[/]\n"
        )

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Complete subcommands, encoder names, and carrier names."""
        from pistudio.encoding import encoder_names

        current = tokens[-1] if tokens else ""
        previous = tokens[-2] if len(tokens) >= 2 else ""

        if previous in ("--chain", "--encode"):
            return [n for n in encoder_names() if n.startswith(current)]
        if previous == "--payload":
            return complete_payload_names(shell, current)
        if previous == "--carrier":
            from pistudio.carriers import carrier_names

            return [c for c in carrier_names() if c.startswith(current)]

        options = [*self.subcommands, "--chain", "--carrier", "--payload"]
        return [c for c in options if c.startswith(current)]
