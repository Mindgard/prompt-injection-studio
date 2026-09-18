"""Ubertooth One subcommand handlers for the hw command."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from pistudio.commands.flags import take_flag
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.commands.hw.command import HwCommand
    from pistudio.core.protocols import StudioProtocol


UBERTOOTH_HELP = (
    "Usage: hw ubertooth <subcommand> [args]   📡  Ubertooth One\n\n"
    "Ubertooth One — BLE prompt injection delivery, sniffing, and reactive triggers.\n\n"
    "Subcommands:\n"
    "  devices                      Detect Ubertooth hardware + check host tools\n"
    "  ble-adv <payload> [flags]    Broadcast BLE advertisement with payload\n"
    "  ble-sniff [flags]            Passive BLE sniffing (PCAP capture)\n"
    "  ble-interfere [flags]        BLE connection interference\n"
    "  bt-scan [flags]              Classic Bluetooth device discovery\n"
    "  trigger <payload> [flags]    Reactive trigger — sniff then auto-broadcast\n"
    "  spectrum                     2.4 GHz spectrum analysis (coming soon)\n\n"
    "Options:\n"
    "  --mode <follow|promiscuous>  BLE sniff mode (default: follow)\n"
    "  --style <numbered|instructed|scattered>  Flood style (default: instructed)\n"
    "  --url-redirect <url>         Broadcast a URL instead of inline payload\n"
    "  --count <n>                  Number of fake BLE devices for flood\n"
    "  --duration <secs>            Capture/broadcast duration (default: 30)\n"
    "  --output <path>              Output PCAP file path\n"
    "  --dry-run                    Show what would happen without transmitting\n"
    "  --target <addr>              Target BLE address for follow mode\n"
    "  --identify-ai                Identify AI-enabled devices after sniff\n"
    "  --undiscoverable             Scan for undiscoverable BT devices (piconet survey)\n"
    "  --watch <pattern>            Reactive trigger: device name regex\n"
    "  --watch-oui <prefix>         Reactive trigger: OUI prefix match\n\n"
    "Strategy auto-selection (ble-adv):\n"
    "  <= 26 bytes        micro     Single ADV_IND, payload in device name\n"
    "  <= 55 bytes        packed    ADV + SCAN_RSP, split across both packets\n"
    "  <= 1650 bytes      extended  BLE 5.0 extended advertising (if supported)\n"
    "  > 55 bytes         flood     Multi-device instructed flood\n"
    "  --url-redirect     url       Broadcast URI, host payload elsewhere\n\n"
    "Examples:\n"
    "  hw ubertooth devices\n"
    "  hw ubertooth ble-adv ble-say-pwned\n"
    "  hw ubertooth ble-adv system-prompt-leak --style scattered --count 10\n"
    "  hw ubertooth ble-adv ignore-instructions --dry-run\n"
    "  hw ubertooth ble-adv redirect-payload --url-redirect https://evil.com/p.txt\n"
    "  hw ubertooth ble-sniff --duration 60 --output capture.pcap\n"
    "  hw ubertooth ble-sniff --mode promiscuous --identify-ai\n"
    "  hw ubertooth ble-interfere --duration 30\n"
    "  hw ubertooth bt-scan --duration 20\n"
    "  hw ubertooth bt-scan --undiscoverable\n"
    "  hw ubertooth trigger ble-say-pwned --watch 'Echo|Alexa'\n"
    "  hw ubertooth trigger ble-say-pwned --watch-oui 44:07:0B\n"
)


def handle_ubertooth(hw: HwCommand, shell: StudioProtocol, args: list[str]) -> None:
    """Route ubertooth subcommands."""
    if not args or args[0] in ("--help", "-h", "help"):
        shell.out.info(UBERTOOTH_HELP)
        return

    sub = args[0].lower().replace("-", "_")
    remaining = args[1:]

    handlers = {
        "devices": lambda: _devices(shell),
        "ble_adv": lambda: _ble_adv(hw, shell, remaining),
        "ble_sniff": lambda: _ble_sniff(shell, remaining),
        "ble_interfere": lambda: _ble_interfere(shell, remaining),
        "bt_scan": lambda: _bt_scan(shell, remaining),
        "trigger": lambda: _trigger(hw, shell, remaining),
        "spectrum": lambda: _spectrum(shell),
    }

    handler = handlers.get(sub)
    if handler:
        handler()
    else:
        display_subs = ["devices", "ble-adv", "ble-sniff", "ble-interfere", "bt-scan", "trigger", "spectrum"]
        shell.out.error(hw.suggest_subcommand(args[0], display_subs))


def _has_flag(args: list[str], flag: str) -> tuple[list[str], bool]:
    """Check for a boolean flag, returning (remaining_args, present)."""
    if flag in args:
        return [a for a in args if a != flag], True
    return list(args), False


def _devices(shell: StudioProtocol) -> None:
    """Detect Ubertooth hardware and check host tools."""
    from pistudio.hardware.ubertooth.device import check_tools, find_ubertooth

    t = active_theme()
    ut = find_ubertooth()

    if ut is None:
        shell.console.print(f"  [{t.muted}]No Ubertooth found.[/]")
        shell.console.print(f"  [{t.muted}]Connect Ubertooth One via USB.[/]")
        return

    shell.console.print(f"  [{t.success}]U[/] Ubertooth One [{t.accent}]fw:{ut['firmware_version']}[/]")
    shell.console.print(f"  [{t.muted}]VID:PID {ut['vid_pid']}[/]")

    missing = check_tools()
    if missing:
        shell.console.print(f"  [{t.warning}]Missing tools: {', '.join(missing)}[/]")
    else:
        shell.console.print(f"  [{t.success}]All required tools available[/]")

    for tool, available in ut["tools"].items():
        status = f"[{t.success}]ok[/]" if available else f"[{t.muted}]missing[/]"
        shell.console.print(f"    {tool}: {status}")


def _ble_adv(hw: HwCommand, shell: StudioProtocol, args: list[str]) -> None:
    """Broadcast BLE advertisement with a prompt injection payload."""
    from pistudio.hardware.payloads import get_payload
    from pistudio.hardware.ubertooth.packets import compile_auto

    if not args:
        shell.out.error(
            "Usage: hw ubertooth ble-adv <payload> [--style S] [--count N] [--url-redirect URL] [--dry-run]"
        )
        return

    remaining = list(args)
    remaining, dry_run = _has_flag(remaining, "--dry-run")
    remaining, style = take_flag(remaining, "--style", "instructed")
    remaining, count_str = take_flag(remaining, "--count", "0")
    remaining, url = take_flag(remaining, "--url-redirect")
    remaining, duration_str = take_flag(remaining, "--duration", "60")

    if not remaining:
        shell.out.error("Usage: hw ubertooth ble-adv <payload> [flags]")
        return

    name = remaining[0]
    result = get_payload(name, shell.session_dir)
    if result is None:
        shell.out.error(f"Payload '{name}' not found.")
        return

    payload, _ = result
    t = active_theme()

    compiled = compile_auto(payload.text, url=url)
    strategy = compiled["strategy"]
    device_count = len(compiled["devices"])

    shell.console.print(f"\n  [{t.secondary} bold]BLE Advertisement[/]")
    shell.console.print(f"  [{t.muted}]Payload:[/]  {name}")
    shell.console.print(f"  [{t.muted}]Strategy:[/] {strategy}")
    shell.console.print(f"  [{t.muted}]Note:[/]     {compiled['note']}")
    if device_count > 0:
        shell.console.print(f"  [{t.muted}]Devices:[/]  {device_count}")
    shell.console.print()

    if dry_run:
        shell.console.print(f"  [{t.accent}]--dry-run: no transmission[/]")
        shell.audit.log("hw_ubertooth_ble_adv_dry_run", payload=name, strategy=strategy)
        return

    if not shell.confirm("Transmit?"):
        shell.console.print(f"  [{t.muted}]Cancelled.[/]")
        return

    from pistudio.hardware.ubertooth.ble_advertise import advertise_hci

    try:
        duration = int(duration_str or "60")
    except ValueError:
        shell.out.error(f"Invalid duration: {duration_str}")
        return
    for i, (adv_data, scan_rsp) in enumerate(compiled["devices"], 1):
        if device_count > 1:
            shell.console.print(f"  [{t.muted}]Broadcasting device {i}/{device_count}...[/]")
        advertise_hci(adv_data, scan_rsp, duration_secs=duration)

    shell.console.print(f"  [{t.success}]Broadcast complete[/]")
    shell.audit.log("hw_ubertooth_ble_adv", payload=name, strategy=strategy, devices=device_count)


def _ble_sniff(shell: StudioProtocol, args: list[str]) -> None:
    """Passive BLE sniffing via Ubertooth."""
    remaining = list(args)
    remaining, mode = take_flag(remaining, "--mode", "follow")
    remaining, duration_str = take_flag(remaining, "--duration", "30")
    remaining, output_path = take_flag(remaining, "--output")
    remaining, identify_ai = _has_flag(remaining, "--identify-ai")
    remaining, target = take_flag(remaining, "--target")

    t = active_theme()
    try:
        duration = int(duration_str or "30")
    except ValueError:
        shell.out.error(f"Invalid duration: {duration_str}")
        return

    if output_path is None:
        output_path = os.path.join(shell.session_dir, "ubertooth_capture.pcap")

    shell.console.print(f"\n  [{t.secondary} bold]BLE Sniff[/]")
    shell.console.print(f"  [{t.muted}]Mode:[/]     {mode}")
    shell.console.print(f"  [{t.muted}]Duration:[/] {duration}s")
    shell.console.print(f"  [{t.muted}]Output:[/]   {output_path}")
    if target:
        shell.console.print(f"  [{t.muted}]Target:[/]   {target}")
    shell.console.print()

    from pistudio.hardware.ubertooth.ble_sniff import (
        identify_ai_devices,
        parse_sniff_output,
        sniff_follow,
        sniff_promiscuous,
    )

    if mode == "promiscuous":
        proc = sniff_promiscuous(output_path)
    else:
        proc = sniff_follow(output_path, duration_secs=duration, target_addr=target)

    shell.console.print(f"  [{t.muted}]Sniffing for {duration}s... (Ctrl+C to stop)[/]")
    try:
        stdout_bytes, _ = proc.communicate(timeout=duration + 10)
    except KeyboardInterrupt:
        proc.kill()
        stdout_bytes, _ = proc.communicate()
    except Exception:
        proc.kill()
        stdout_bytes, _ = proc.communicate()

    raw_output = stdout_bytes.decode("utf-8", errors="replace")
    devices = parse_sniff_output(raw_output)

    shell.console.print(f"\n  [{t.success}]Capture complete[/] — {len(devices)} device(s) seen")
    for dev in devices[:20]:
        shell.console.print(f"    [{t.accent}]{dev['addr']}[/] ({dev['addr_type']}) seen {dev['seen_count']}x")

    if identify_ai and devices:
        ai_devices = identify_ai_devices(devices)
        if ai_devices:
            shell.console.print(f"\n  [{t.secondary} bold]AI Devices Identified[/]")
            for dev in ai_devices:
                shell.console.print(f"    [{t.accent}]{dev['addr']}[/] -> {dev.get('ai_type', 'unknown')}")
        else:
            shell.console.print(f"  [{t.muted}]No AI devices identified.[/]")

    shell.audit.log("hw_ubertooth_ble_sniff", mode=mode, duration=duration, devices_found=len(devices))


def _ble_interfere(shell: StudioProtocol, args: list[str]) -> None:
    """BLE connection interference."""
    remaining = list(args)
    remaining, duration_str = take_flag(remaining, "--duration", "30")
    remaining, mode = take_flag(remaining, "--mode", "new")

    t = active_theme()
    try:
        duration = int(duration_str or "30")
    except ValueError:
        shell.out.error(f"Invalid duration: {duration_str}")
        return

    shell.console.print(f"\n  [{t.secondary} bold]BLE Interference[/]")
    shell.console.print(f"  [{t.muted}]Mode:[/]     {mode} connections")
    shell.console.print(f"  [{t.muted}]Duration:[/] {duration}s")

    if not shell.confirm("Start interference?"):
        shell.console.print(f"  [{t.muted}]Cancelled.[/]")
        return

    from pistudio.hardware.ubertooth.ble_interfere import (
        interfere_existing_connections,
        interfere_new_connections,
    )

    if mode == "existing":
        proc = interfere_existing_connections(duration_secs=duration)
    else:
        proc = interfere_new_connections(duration_secs=duration)

    shell.console.print(f"  [{t.muted}]Interfering for {duration}s... (Ctrl+C to stop)[/]")
    try:
        proc.communicate(timeout=duration + 10)
    except KeyboardInterrupt:
        proc.kill()
    except Exception:
        proc.kill()

    shell.console.print(f"  [{t.success}]Interference stopped[/]")
    shell.audit.log("hw_ubertooth_ble_interfere", mode=mode, duration=duration)


def _bt_scan(shell: StudioProtocol, args: list[str]) -> None:
    """Classic Bluetooth device discovery."""
    remaining = list(args)
    remaining, duration_str = take_flag(remaining, "--duration", "20")
    remaining, undiscoverable = _has_flag(remaining, "--undiscoverable")

    t = active_theme()
    try:
        duration = int(duration_str or "20")
    except ValueError:
        shell.out.error(f"Invalid duration: {duration_str}")
        return

    shell.console.print(f"\n  [{t.secondary} bold]Classic BT Scan[/]")
    scan_type = "piconet survey (undiscoverable)" if undiscoverable else "discoverable"
    shell.console.print(f"  [{t.muted}]Type:[/]     {scan_type}")
    shell.console.print(f"  [{t.muted}]Duration:[/] {duration}s")
    shell.console.print()

    from pistudio.hardware.ubertooth.classic_scan import scan_discoverable, survey_piconets

    shell.console.print(f"  [{t.muted}]Scanning for {duration}s...[/]")

    scanner = survey_piconets if undiscoverable else scan_discoverable
    devices = scanner(duration_secs=duration)

    shell.console.print(f"\n  [{t.success}]Scan complete[/] — {len(devices)} device(s) found")
    for dev in devices[:20]:
        addr = dev.get("addr") or dev.get("lap", "?")
        name = dev.get("name", "")
        dev_type = dev.get("type", "")
        label = f"{addr} {name}".strip()
        shell.console.print(f"    [{t.accent}]{label}[/] [{t.muted}]({dev_type})[/]")

    shell.audit.log("hw_ubertooth_bt_scan", scan_type=scan_type, duration=duration, devices_found=len(devices))


def _trigger(hw: HwCommand, shell: StudioProtocol, args: list[str]) -> None:
    """Reactive trigger: sniff for targets, auto-broadcast on match."""
    from pistudio.hardware.payloads import get_payload
    from pistudio.hardware.ubertooth.packets import compile_auto
    from pistudio.hardware.ubertooth.reactive import ReactiveTrigger

    if not args:
        shell.out.error("Usage: hw ubertooth trigger <payload> [--watch <pattern>] [--watch-oui <prefix>]")
        return

    remaining = list(args)
    remaining, watch = take_flag(remaining, "--watch")
    remaining, watch_oui = take_flag(remaining, "--watch-oui")

    if not remaining:
        shell.out.error("Usage: hw ubertooth trigger <payload> [--watch <pattern>] [--watch-oui <prefix>]")
        return

    if not watch and not watch_oui:
        shell.out.error("At least one of --watch or --watch-oui is required.")
        return

    name = remaining[0]
    result = get_payload(name, shell.session_dir)
    if result is None:
        shell.out.error(f"Payload '{name}' not found.")
        return

    payload, _ = result
    t = active_theme()

    compiled = compile_auto(payload.text)
    if not compiled["devices"]:
        shell.out.error("Payload compiled to zero devices; cannot set up trigger.")
        return

    adv_data, scan_rsp = compiled["devices"][0]

    shell.console.print(f"\n  [{t.secondary} bold]Reactive Trigger[/]")
    shell.console.print(f"  [{t.muted}]Payload:[/]  {name}")
    shell.console.print(f"  [{t.muted}]Strategy:[/] {compiled['strategy']}")
    if watch:
        shell.console.print(f"  [{t.muted}]Watch:[/]    {watch}")
    if watch_oui:
        shell.console.print(f"  [{t.muted}]OUI:[/]      {watch_oui}")
    shell.console.print()

    trigger = ReactiveTrigger(
        watch_pattern=watch,
        watch_oui=watch_oui,
        payload_adv_data=adv_data,
        payload_scan_rsp=scan_rsp,
    )

    shell.console.print(f"  [{t.muted}]Trigger armed — Ctrl+C to stop[/]")
    trigger.start()
    shell.audit.log("hw_ubertooth_trigger_start", payload=name, watch=watch, watch_oui=watch_oui)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        trigger.stop()
        shell.console.print(f"\n  [{t.success}]Trigger stopped[/]")
        shell.audit.log("hw_ubertooth_trigger_stop", payload=name)


def _spectrum(shell: StudioProtocol) -> None:
    """Spectrum analysis placeholder."""
    t = active_theme()
    shell.console.print(f"  [{t.muted}]Spectrum analysis is not yet implemented.[/]")
    shell.console.print(
        f"  [{t.muted}]This feature requires ubertooth-specan and will be added in a future release.[/]"
    )


def complete_ubertooth(shell: StudioProtocol, tokens: list[str]) -> list[str]:
    """Tab completion for ubertooth subcommands."""
    from pistudio.commands.payload_flag import complete_payload_names

    ubertooth_subs = [
        "devices",
        "ble-adv",
        "ble-sniff",
        "ble-interfere",
        "bt-scan",
        "trigger",
        "spectrum",
    ]

    if not tokens:
        return ubertooth_subs

    if len(tokens) == 1:
        return [s for s in ubertooth_subs if s.startswith(tokens[0])]

    first = tokens[0].lower().replace("-", "_")
    if first in ("ble_adv", "trigger") and len(tokens) == 2:
        return complete_payload_names(shell, tokens[1])

    return []
