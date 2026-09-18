"""Flipper Zero sync and serial console subcommand handlers.

Extracted from ``flipper.py`` to keep file sizes manageable.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol


def flipper_sync(shell: StudioProtocol, args: list[str]) -> None:
    """Sync the payload library to a Flipper SD card."""
    from pistudio.hardware.flipper.sync import sync_payloads

    t = active_theme()

    path = None
    if "--path" in args:
        idx = args.index("--path")
        if idx + 1 < len(args):
            path = args[idx + 1]

    try:
        dest, count = sync_payloads(shell.session_dir, path)
    except FileNotFoundError as e:
        shell.out.error(str(e))
        return

    shell.console.print(
        f"  [{t.success}]\U0001f42c[/] Synced [{t.accent}]{count}[/] payloads \u2192 [{t.accent}]{dest}[/]"
    )
    shell.audit.log("hw_flipper_sync", type="payloads", count=count)


def flipper_sync_results(shell: StudioProtocol, args: list[str]) -> None:
    """Sync scan results to Flipper SD card for on-device viewing."""
    from pistudio.hardware.flipper.sync import sync_results

    t = active_theme()

    path = None
    args = list(args)
    if "--path" in args:
        idx = args.index("--path")
        if idx + 1 < len(args):
            path = args[idx + 1]
            args = args[:idx] + args[idx + 2 :]

    test_id = None
    if "--test-id" in args:
        idx = args.index("--test-id")
        if idx + 1 < len(args):
            test_id = args[idx + 1]
            args = args[:idx] + args[idx + 2 :]

    results_file = os.path.join(shell.session_dir, "last_test_results.json")
    if test_id:
        specific = os.path.join(shell.session_dir, f"test_results_{test_id}.json")
        if os.path.isfile(specific):
            results_file = specific

    if not os.path.isfile(results_file):
        shell.out.error("No scan results found in this session.\n  Run 'test run' first, or specify --test-id.")
        return

    try:
        with open(results_file) as f:
            results_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        shell.out.error(f"Failed to read results: {e}")
        return

    try:
        dest = sync_results(results_data, path)
        shell.console.print(f"  [{t.success}]\U0001f42c[/] Synced scan results \u2192 [{t.accent}]{dest}[/]")
        shell.audit.log("hw_flipper_sync_results", path=dest, test_id=test_id)
    except FileNotFoundError as e:
        shell.out.error(str(e))


def flipper_tty(shell: StudioProtocol, args: list[str]) -> None:
    """Connect to Flipper Zero serial console (CLI)."""
    from pistudio.hardware.flipper.serial_console import (
        find_flipper_serial_ports,
        run_flipper_console,
    )

    t = active_theme()
    args = list(args)

    baud = 115200
    if "--baud" in args:
        idx = args.index("--baud")
        if idx + 1 < len(args):
            try:
                baud = int(args[idx + 1])
            except ValueError:
                shell.out.error(f"Invalid baud rate: {args[idx + 1]}")
                return
            args = args[:idx] + args[idx + 2 :]

    port = args[0] if args else None

    if port is None:
        ports = find_flipper_serial_ports()
        if shell.json_mode:
            shell.print_raw(json.dumps({"serial_ports": ports}))
            return

        if not ports:
            shell.out.error(
                "No Flipper Zero serial port found.\n"
                "  \u2022 Connect Flipper via USB\n"
                "  \u2022 Ensure it's not in Mass Storage mode (use CLI mode)\n"
                "  \u2022 On macOS/Linux, check /dev/tty.usbmodem* or /dev/ttyACM*"
            )
            return

        if len(ports) == 1:
            port = ports[0]
        else:
            shell.console.print(f"  [{t.muted}]Multiple serial ports found:[/]")
            for i, p in enumerate(ports, 1):
                shell.console.print(f"    [{t.accent}]{i}.[/] {p}")
            choice = shell.ask("Select port (1):")
            if choice is None:
                # No terminal to pick with.  `tty` takes the port as a
                # positional, so naming --serial-port here pointed at an option
                # this handler never parses.
                shell.out.error("Multiple serial ports found. Name one: hw flipper tty <device>.")
                return
            try:
                idx = int(choice.strip()) - 1 if choice.strip() else 0
                port = ports[idx]
            except (ValueError, IndexError):
                shell.out.error(f"Not one of the {len(ports)} listed ports: {choice.strip()!r}")
                return

    shell.console.print(f"  [{t.success}]\U0001f42c[/] Connecting to [{t.accent}]{port}[/] @ {baud} baud")
    shell.console.print(f"  [{t.muted}]Press Ctrl+] or Ctrl+C to disconnect[/]\n")

    try:
        run_flipper_console(port, baud)
    except ConnectionError as e:
        shell.out.error(str(e))
    except KeyboardInterrupt:
        pass
    finally:
        shell.console.print(f"\n  [{t.muted}]Disconnected.[/]")
