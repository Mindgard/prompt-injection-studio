"""Flipper Zero remote control and sequence subcommand handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.commands.hw.command import HwCommand
    from pistudio.core.protocols import StudioProtocol


def handle_remote(shell: StudioProtocol, args: list[str]) -> None:
    """Interactive remote control of Flipper Zero over serial bridge."""
    from pistudio.hardware.flipper.bridge import FlipperBridge
    from pistudio.hardware.flipper.serial_console import (
        find_flipper_bridge_port,
        find_flipper_serial_ports,
    )

    t = active_theme()

    port = None
    baud = 115200
    remaining = list(args)
    if "--serial-port" in remaining:
        idx = remaining.index("--serial-port")
        if idx + 1 < len(remaining):
            port = remaining[idx + 1]
            remaining = remaining[:idx] + remaining[idx + 2 :]
    if "--baud" in remaining:
        idx = remaining.index("--baud")
        if idx + 1 < len(remaining):
            try:
                baud = int(remaining[idx + 1])
            except ValueError:
                shell.out.error(f"Invalid baud rate: {remaining[idx + 1]}")
                return
            remaining = remaining[:idx] + remaining[idx + 2 :]

    if port is None:
        port = find_flipper_bridge_port()
        if port is None:
            shell.out.error(
                "No Flipper Zero serial port found.\n"
                "  - Connect Flipper via USB\n"
                "  - Open the Mindgard app -> Remote Mode on the Flipper\n"
                "  - Use --serial-port to specify manually"
            )
            return

        all_ports = find_flipper_serial_ports()
        if len(all_ports) >= 2:
            shell.console.print(f"  [{t.muted}]Dual-CDC detected: using bridge port {port}[/]")
        elif len(all_ports) == 1:
            shell.console.print(
                f"  [{t.muted}]Single port detected: {port}[/]\n"
                f"  [{t.muted}]If this fails, ensure Flipper is in Remote Mode (dual-CDC).[/]"
            )

    bridge = FlipperBridge(port, baud)
    try:
        bridge.connect()
    except Exception as e:
        shell.out.error(f"Failed to connect to {port}: {e}")
        return

    if not bridge.ping():
        bridge.disconnect()
        _report_bridge_failure(shell, port)
        return

    shell.console.print(f"  [{t.success}]🐬[/] Connected to Flipper Zero @ [{t.accent}]{port}[/]")
    shell.audit.log("hw_flipper_remote_connect", port=port)

    if remaining and remaining[0] in ("exec", "run"):
        _remote_run(shell, bridge, remaining[1:])
        bridge.disconnect()
        return

    if remaining and remaining[0] == "status":
        _remote_status(shell, bridge)
        bridge.disconnect()
        return

    _remote_repl(shell, bridge)
    bridge.disconnect()
    shell.console.print(f"  [{t.muted}]Disconnected.[/]")


def _report_bridge_failure(shell: StudioProtocol, port: str) -> None:
    """Report bridge connection failure with diagnostics."""
    from pistudio.hardware.flipper.serial_console import find_flipper_serial_ports

    all_ports = find_flipper_serial_ports()
    if len(all_ports) < 2:
        shell.out.error(
            "Flipper is not responding on the bridge protocol.\n"
            "  Only one serial port was found -- the Flipper may not be\n"
            "  in Remote Mode yet (dual-CDC mode).\n\n"
            "  Steps:\n"
            "  1. On the Flipper, open Mindgard app -> Remote Mode\n"
            "  2. Wait for the Flipper to show 'Listening'\n"
            "  3. Run 'hw flipper remote' again"
        )
    else:
        shell.out.error(
            f"Connected to {port} but Flipper bridge is not responding.\n"
            f"  Detected ports: {', '.join(all_ports)}\n"
            "  Make sure the Mindgard app is in Remote Mode.\n"
            "  Try: hw flipper remote --serial-port <other_port>"
        )


def _remote_run(shell: StudioProtocol, bridge, args: list[str]) -> None:
    """One-shot remote payload execution."""
    t = active_theme()
    if not args:
        shell.out.error("Usage: hw flipper remote exec <payload_name>")
        return

    name = args[0]

    shell.console.print(f"  [{t.muted}]Executing '{name}'...[/]")
    ok, msg = bridge.execute_badusb(name)

    if ok:
        shell.console.print(f"  [{t.success}]✓[/] {msg}")
        shell.audit.log("hw_flipper_remote_exec", name=name, success=True)
    else:
        shell.out.error(msg)


def _remote_status(shell: StudioProtocol, bridge) -> None:
    """One-shot status query."""
    t = active_theme()
    status = bridge.status()
    shell.console.print(f"\n  [{t.secondary} bold]Flipper Status[/]")
    shell.console.print(f"  [{t.muted}]State:[/]         [{t.accent}]{status['state']}[/]")
    shell.console.print(f"  [{t.muted}]Payloads:[/]      [{t.accent}]{status['payloads']}[/]")
    shell.console.print()


# The verbs this nested console accepts, and the aliases for them.  It is a
# third dispatcher -- separate from the CLI and the main REPL -- which is how
# `ls` came to work everywhere else and not here.
_REMOTE_COMMANDS = ("list", "exec", "load", "stop", "status", "set", "reload", "ping", "help", "exit")
_REMOTE_ALIASES = {
    "ls": "list",
    "run": "exec",
    "q": "exit",
    "quit": "exit",
    "?": "help",
}


def _unknown_remote_command(cmd: str) -> str:
    """Name the closest verb, as the rest of the tool does for a typo."""
    import difflib

    known = [*_REMOTE_COMMANDS, *_REMOTE_ALIASES]
    matches = difflib.get_close_matches(cmd, known, n=1, cutoff=0.6)
    hint = f" Did you mean '{matches[0]}'?" if matches else ""
    return f"Unknown command: '{cmd}'.{hint} Type 'help' for usage."


def _remote_repl(shell: StudioProtocol, bridge) -> None:
    """Interactive remote control mini-REPL."""
    t = active_theme()
    shell.console.print(f"  [{t.muted}]Type 'help' for commands, 'exit' to disconnect.[/]\n")

    while True:
        answer = shell.ask("flipper>")
        if answer is None:
            shell.console.print()
            break
        line = answer.strip()

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        cmd = _REMOTE_ALIASES.get(cmd, cmd)

        if cmd in ("exit", "quit"):
            break
        elif cmd == "help":
            _repl_help(shell, t)
        elif cmd == "reload":
            ok, msg = bridge.reload()
            shell.console.print(f"  [{t.success if ok else t.error}]{msg}[/]")
        elif cmd == "ping":
            ok = bridge.ping()
            shell.console.print(f"  [{t.success if ok else t.error}]{'✓ PONG' if ok else '✗ No response'}[/]")
        elif cmd == "status":
            _remote_status(shell, bridge)
        elif cmd == "stop":
            _repl_stop(shell, bridge, parts, t)
        elif cmd == "list":
            _repl_list(shell, bridge, t)
        elif cmd == "exec":
            # Arity is checked per verb rather than folded into the branch
            # condition: `exec badusb` with no name used to fall through to
            # "Unknown command", blaming the verb for a missing argument.
            if len(parts) >= 3:
                _repl_run(shell, bridge, parts, t)
            else:
                shell.out.error("Usage: exec <badusb|nfc|ble|qr> <name>")
        elif cmd == "load":
            if len(parts) >= 3:
                ok, msg = bridge.load_payload(parts[1], " ".join(parts[2:]))
                shell.console.print(f"  [{t.success if ok else t.error}]{msg}[/]")
            else:
                shell.out.error('Usage: load <name> "<text>"')
        elif cmd == "set":
            if len(parts) >= 3:
                _repl_set(shell, bridge, parts, t)
            else:
                shell.out.error("Usage: set delay <ms>")
        else:
            shell.out.error(_unknown_remote_command(cmd))


def _repl_help(shell: StudioProtocol, t) -> None:
    """Print REPL help text."""
    shell.console.print(
        f"\n  [{t.secondary} bold]Remote Commands[/]\n"
        f"  [{t.accent}]list (ls)[/]              List payloads on Flipper\n"
        f"  [{t.accent}]exec badusb <name>[/]     Run payload via BadUSB\n"
        f"  [{t.accent}]exec nfc <name>[/]        Write NFC file on Flipper\n"
        f"  [{t.accent}]exec ble <name>[/]        Start BLE beacon advertising\n"
        f"  [{t.accent}]exec qr <name>[/]         Display payload as QR code\n"
        f"  [{t.accent}]load <name> <text>[/]     Push a one-off payload\n"
        f"  [{t.accent}]stop[/]                   Abort current action\n"
        f"  [{t.accent}]stop ble[/]               Stop BLE beacon\n"
        f"  [{t.accent}]status[/]                 Flipper state + counts\n"
        f"  [{t.accent}]set delay <ms>[/]         Set BadUSB start delay\n"
        f"  [{t.accent}]reload[/]                 Reload data from SD card\n"
        f"  [{t.accent}]ping[/]                   Heartbeat check\n"
        f"  [{t.accent}]exit[/]                   Disconnect\n"
    )


def _repl_stop(shell: StudioProtocol, bridge, parts: list[str], t) -> None:
    """Handle stop commands in the REPL."""
    if len(parts) > 1 and parts[1].lower() == "ble":
        ok = bridge.stop_ble()
        shell.console.print(f"  [{t.success if ok else t.error}]{'✓ BLE stopped' if ok else '✗ Failed'}[/]")
    else:
        ok = bridge.stop()
        shell.console.print(f"  [{t.success if ok else t.error}]{'✓ Stopped' if ok else '✗ Failed'}[/]")


def _repl_list(shell: StudioProtocol, bridge, t) -> None:
    """Handle list commands in the REPL."""
    from pistudio.hardware.flipper.bridge import IncompleteResponse

    try:
        payloads = bridge.list_payloads()
    except IncompleteResponse as exc:
        # Reporting "No payloads loaded" here was actively misleading: the
        # device had answered, and the answer was cut short in transit.
        shell.out.error(f"The Flipper's payload list arrived truncated. {exc}")
        shell.console.print(
            f"  [{t.muted}]The payloads are on the device; the bridge could not read them all.\n"
            f"  Update the Flipper app (vendor/flipper-field-kit), or use 'hw flipper sync'\n"
            f"  and read the list from this side with 'payloads list'.[/]"
        )
        return
    if not payloads:
        shell.console.print(f"  [{t.muted}]No payloads loaded.[/]")
        return
    shell.console.print(f"  [{t.accent}]{len(payloads)}[/] payloads loaded:")
    for p in payloads:
        builtin = " (builtin)" if p.get("builtin") else ""
        shell.console.print(f"    {p.get('name', '?')}{builtin}")


def _repl_run(shell: StudioProtocol, bridge, parts: list[str], t) -> None:
    """Handle run/exec commands in the REPL."""
    proto = parts[1].lower()
    name = parts[2]
    proto_handlers = {
        "badusb": ("Executing '{name}' via BadUSB...", bridge.execute_badusb),
        "nfc": ("Writing NFC file for '{name}'...", bridge.execute_nfc),
        "ble": ("Starting BLE beacon for '{name}'...", bridge.execute_ble),
        "qr": ("Displaying QR code for '{name}'...", bridge.execute_qr),
    }
    if proto in proto_handlers:
        label_template, handler = proto_handlers[proto]
        shell.console.print(f"  [{t.muted}]{label_template.format(name=name)}[/]")
        ok, msg = handler(name)
        shell.console.print(f"  [{t.success if ok else t.error}]{msg}[/]")
    else:
        shell.out.error(f"Unknown protocol: {proto}")


def _repl_set(shell: StudioProtocol, bridge, parts: list[str], t) -> None:
    """Handle set commands in the REPL."""
    setting = parts[1].lower()
    try:
        value = int(parts[2])
    except ValueError:
        shell.out.error("Value must be a number")
        return
    if setting == "delay":
        ok = bridge.set_delay(value)
    else:
        shell.out.error(f"Unknown setting: {setting}")
        return
    shell.console.print(f"  [{t.success if ok else t.error}]{'✓ Set' if ok else '✗ Failed'}[/]")


# ── Sequence handlers ────────────────────────────────────────────


def handle_sequence(hw: HwCommand, shell: StudioProtocol, args: list[str]) -> None:
    """Handle Flipper sequence subcommands."""
    from pistudio.hardware.flipper.sequence import (
        add_step,
        create_sequence,
        deploy_sequence,
        get_sequence,
        list_sequences,
        remove_sequence,
    )

    if not args:
        shell.out.info(
            "Usage:\n"
            "  hw flipper sequence create <name> [<description>]\n"
            "  hw flipper sequence add <name> <protocol> <payload> [--delay <ms>]\n"
            "  hw flipper sequence show <name>\n"
            "  hw flipper sequence list\n"
            "  hw flipper sequence deploy <name> [--path <dir>]\n"
            "  hw flipper sequence rm <name> [--global]\n"
        )
        return

    sub = args[0].lower()
    remaining = args[1:]
    t = active_theme()

    if sub == "create":
        _seq_create(shell, remaining, args, t, create_sequence)
    elif sub == "add":
        _seq_add(shell, remaining, t, add_step)
    elif sub == "show":
        _seq_show(shell, remaining, t, get_sequence)
    elif sub in ("list", "ls"):
        _seq_list(shell, t, list_sequences)
    elif sub == "deploy":
        _seq_deploy(shell, remaining, t, deploy_sequence)
    elif sub == "rm":
        _seq_rm(shell, remaining, t, remove_sequence)
    else:
        shell.out.error(hw.suggest_subcommand(sub, ["create", "add", "show", "list", "deploy", "rm"]))


def _seq_create(shell, remaining, args, t, create_sequence) -> None:
    if not remaining:
        shell.out.error("Usage: hw flipper sequence create <name> [<description>]")
        return
    name = remaining[0]
    desc = " ".join(remaining[1:]) if len(remaining) > 1 else ""
    global_scope = "--global" in args
    try:
        seq = create_sequence(name, shell.session_dir, description=desc, global_scope=global_scope)
        shell.console.print(f"  [{t.success}]✓[/] Created sequence '{seq.name}'")
        shell.audit.log("hw_flipper_sequence_create", name=name)
    except ValueError as e:
        shell.out.error(str(e))


def _seq_add(shell, remaining, t, add_step) -> None:

    delay_ms = 0
    if "--delay" in remaining:
        idx = remaining.index("--delay")
        if idx + 1 < len(remaining):
            try:
                delay_ms = int(remaining[idx + 1])
            except ValueError:
                shell.out.error("--delay must be a number (milliseconds)")
                return
            remaining = remaining[:idx] + remaining[idx + 2 :]

    global_scope = "--global" in remaining
    remaining = [a for a in remaining if a != "--global"]

    if len(remaining) < 3:
        shell.out.error("Usage: hw flipper sequence add <name> <protocol> <payload> [--delay <ms>]")
        return

    name, protocol, payload = remaining[0], remaining[1], remaining[2]
    try:
        seq = add_step(
            name,
            protocol,
            payload,
            shell.session_dir,
            delay_after_ms=delay_ms,
            global_scope=global_scope,
        )
        step_num = len(seq.steps)
        shell.console.print(f"  [{t.success}]✓[/] Added step {step_num}: {protocol} payload '{payload}'")
        if delay_ms:
            shell.console.print(f"  [{t.muted}]  +{delay_ms}ms delay after[/]")
        shell.audit.log("hw_flipper_sequence_add", name=name, step=step_num)
    except ValueError as e:
        shell.out.error(str(e))


def _seq_show(shell, remaining, t, get_sequence) -> None:
    if not remaining:
        shell.out.error("Usage: hw flipper sequence show <name>")
        return
    name = remaining[0]
    result = get_sequence(name, shell.session_dir)
    if result is None:
        shell.out.error(f"Sequence '{name}' not found.")
        return
    seq, scope = result

    shell.console.print(f"\n  [{t.accent} bold]{seq.name}[/] [{t.muted}]({scope})[/]")
    if seq.description:
        shell.console.print(f"  [{t.muted}]{seq.description}[/]")
    shell.console.print(f"  [{t.muted}]{len(seq.steps)} steps[/]\n")

    if not seq.steps:
        shell.console.print(f"  [{t.muted}](no steps yet)[/]")
    for i, step in enumerate(seq.steps, 1):
        kind = "payload"
        delay_str = f" (+{step.delay_after_ms}ms)" if step.delay_after_ms else ""
        shell.console.print(
            f"  [{t.secondary}]{i}.[/] [{t.accent}]{step.protocol}[/] {kind}: {step.payload}{delay_str}"
        )
    shell.console.print()


def _seq_list(shell, t, list_sequences) -> None:
    seqs = list_sequences(shell.session_dir)
    if not seqs:
        shell.console.print(f"  [{t.muted}]No sequences found.[/]")
        return
    shell.console.print(f"\n  [{t.secondary} bold]Attack Sequences[/]\n")
    for seq, scope in seqs:
        scope_badge = f"[{t.muted}]({scope})[/]" if scope != "session" else ""
        steps = f"[{t.muted}]{len(seq.steps)} steps[/]"
        shell.console.print(f"  [{t.accent}]{seq.name:<24}[/] {steps} {scope_badge}")
    shell.console.print()


def _seq_deploy(shell, remaining, t, deploy_sequence) -> None:
    if not remaining:
        shell.out.error("Usage: hw flipper sequence deploy <name> [--path <dir>]")
        return
    name = remaining[0]
    path = None
    if "--path" in remaining:
        idx = remaining.index("--path")
        if idx + 1 < len(remaining):
            path = remaining[idx + 1]
    try:
        deployed = deploy_sequence(name, shell.session_dir, path=path)
        shell.console.print(f"  [{t.success}]🐬[/] Deployed sequence -> [{t.accent}]{deployed}[/]")
        shell.audit.log("hw_flipper_sequence_deploy", name=name, path=deployed)
    except (ValueError, FileNotFoundError) as e:
        shell.out.error(str(e))


def _seq_rm(shell, remaining, t, remove_sequence) -> None:
    if not remaining:
        shell.out.error("Usage: hw flipper sequence rm <name> [--global]")
        return
    name = remaining[0]
    global_scope = "--global" in remaining
    try:
        remove_sequence(name, shell.session_dir, global_scope=global_scope)
        shell.console.print(f"  [{t.success}]✓[/] Removed sequence '{name}'")
        shell.audit.log("hw_flipper_sequence_rm", name=name)
    except ValueError as e:
        shell.out.error(str(e))
