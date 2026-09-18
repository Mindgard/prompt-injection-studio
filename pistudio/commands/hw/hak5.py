"""Bash Bunny and USB Rubber Ducky delivery.

Payload authoring lives in ``payloads``; this module covers only what is
device-specific: compiling a payload to the device's script dialect, writing
it to the device, and the Bunny's serial console.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.commands.hw.command import HwCommand
    from pistudio.core.protocols import StudioProtocol

_SUBS = ("compile", "deploy", "devices", "tty")

# Target operating systems for Bunny file paths.
_OS_TARGETS = ("windows", "linux", "mac")

# Bunny switch positions.
_SWITCHES = (1, 2)


@dataclass
class _CompileOptions:
    """Compiler settings parsed from command flags."""

    switch: int = 1
    os_target: str = ""
    layout: str = "us"
    ducky_payload: dict = field(default_factory=dict)
    bunny_payload: dict = field(default_factory=dict)


def _int_flag(flags: dict[str, str], key: str, default: int, valid: tuple[int, ...] | None = None) -> int:
    """Parse an integer flag, raising ValueError with an actionable message."""
    raw = flags.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"--{key} must be a number, got '{raw}'.") from exc
    if valid is not None and value not in valid:
        allowed = " or ".join(str(v) for v in valid)
        raise ValueError(f"--{key} must be {allowed}, got {value}.")
    return value


def _compile_options(flags: dict[str, str]) -> _CompileOptions:
    """Build compiler keyword arguments from *flags*.

    Raises:
        ValueError: If a flag value is not usable.
    """
    opts = _CompileOptions()
    opts.switch = _int_flag(flags, "switch", 1, _SWITCHES)

    if os_target := flags.get("os", ""):
        if os_target not in _OS_TARGETS:
            raise ValueError(f"--os must be one of {', '.join(_OS_TARGETS)}, got '{os_target}'.")
        opts.os_target = os_target

    from pistudio.hardware.hak5.keymaps import LAYOUTS

    if layout := flags.get("layout", ""):
        if layout not in LAYOUTS:
            raise ValueError(f"--layout must be one of {', '.join(sorted(LAYOUTS))}, got '{layout}'.")
        opts.layout = layout

    shared: dict = {}
    if "start-delay" in flags:
        shared["start_delay"] = _int_flag(flags, "start-delay", 1000)
    if "default-delay" in flags:
        shared["default_delay"] = _int_flag(flags, "default-delay", 0)
    if preamble := flags.get("preamble", ""):
        shared["preamble"] = preamble

    opts.ducky_payload = dict(shared)
    opts.bunny_payload = dict(shared)
    return opts


_USAGE = """\
Usage: hw {device} <subcommand> [args]   {emoji}  {label}

  compile <payload>             Compile to {dialect} and print it
  deploy  <payload>             Compile and write to an attached device
  devices                       List attached {label} volumes
{extra}
Options:
  --output <path>     Write the compiled script to a file
  --path <mount>      Target a specific device mount point
  --start-delay <ms>  Delay before the first keystroke (default 1000)
  --default-delay <ms>  Delay between every keystroke; paces slow chat UIs
  --preamble <lines>  Script lines to run before typing{switch}{ducky}

Deploying against a device you do not own or have written permission to test
is unlawful in most jurisdictions.

Examples:
  hw {device} compile system-prompt-leak
  hw {device} deploy system-prompt-leak{ducky_example}
"""


def _resolve_source(shell: StudioProtocol, name: str):
    """Look up a payload by *name*.

    The registry lookup returns ``(object, scope)``; only the object is
    needed here.

    Returns:
        The payload object, or ``None`` after reporting the error.
    """
    from pistudio.hardware.payloads import get_payload

    found = get_payload(name, shell.session_dir)
    if found is None:
        shell.out.not_found("Payload", name, "payloads list")
        return None
    return found[0]


def _resolve_files(shell: StudioProtocol, source):
    """Resolve ``{{file:name}}`` references in *source* to registered files.

    Returns:
        ``(files, ok)``. ``files`` is empty when the payload references none;
        ``ok`` is False when a reference could not be resolved, in which case
        the error has already been reported.
    """
    from pistudio.hardware.hak5.bunny_files import get_files_by_names
    from pistudio.hardware.hak5.compiler_bunny import extract_file_references

    names = extract_file_references(source.text)
    if not names:
        return [], True

    # Preserve first-use order while dropping repeats.
    unique = list(dict.fromkeys(names))
    try:
        return get_files_by_names(unique, shell.session_dir), True
    except ValueError as exc:
        shell.out.error(f"{exc} Register it with 'hw files add <name> <path>'.")
        return [], False


def _compile(
    shell: StudioProtocol,
    device: str,
    name: str,
    flags: dict[str, str] | None = None,
) -> tuple[str, list, _CompileOptions] | None:
    """Compile *name* into the script dialect for *device*.

    Returns:
        ``(script, files, opts)`` where *files* are the registered files the
        payload references and *opts* carries the parsed settings (layout, …),
        or None on error.
    """
    flags = flags or {}
    source = _resolve_source(shell, name)
    if source is None:
        return None

    try:
        opts = _compile_options(flags)
    except ValueError as exc:
        shell.out.error(str(exc))
        return None

    if device == "ducky":
        from pistudio.hardware.hak5 import compiler_ducky

        return compiler_ducky.compile_payload(source, **opts.ducky_payload), [], opts

    from pistudio.hardware.hak5 import compiler_bunny

    files, ok = _resolve_files(shell, source)
    if not ok:
        return None

    if not files:
        return compiler_bunny.compile_payload(source, **opts.bunny_payload), [], opts

    # Files present: the payload needs ATTACKMODE HID STORAGE and OS-specific
    # paths, so a target OS must be chosen.
    os_target = opts.os_target or _detect_os_with_notice(shell)
    try:
        script = compiler_bunny.compile_payload_with_files(
            source, files, os_target=os_target, switch=opts.switch, **opts.bunny_payload
        )
    except ValueError as exc:
        shell.out.error(str(exc))
        return None
    return script, files, opts


def _detect_os_with_notice(shell: StudioProtocol) -> str:
    """Return the auto-detected target OS, telling the user what was assumed.

    File paths on the target are OS-specific, so a wrong guess produces a
    payload that references a path the target does not have.
    """
    from pistudio.hardware.hak5.compiler_bunny import detect_os

    os_target = detect_os()
    shell.out.info(f"Assuming target OS '{os_target}' for file paths — override with --os.")
    return os_target


def _flags(args: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split *args* into positionals and ``--flag value`` pairs."""
    positional: list[str] = []
    flags: dict[str, str] = {}
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("--") and i + 1 < len(args):
            flags[tok[2:]] = args[i + 1]
            i += 1
        else:
            positional.append(tok)
        i += 1
    return positional, flags


def handle_hak5(cmd: HwCommand, shell: StudioProtocol, device: str, args: list[str]) -> None:
    """Dispatch a ``hw bunny`` / ``hw ducky`` subcommand.

    Args:
        cmd: The parent ``hw`` command, for shared error helpers.
        shell: The studio context.
        device: Either ``"bunny"`` or ``"ducky"``.
        args: Tokens following the device name.
    """
    label = "Bash Bunny" if device == "bunny" else "Rubber Ducky"
    dialect = "Bunny Script" if device == "bunny" else "DuckyScript"
    extra = "  tty                           Open the Bunny serial console\n" if device == "bunny" else ""
    switch = (
        "\n  --switch <1|2>      Bunny switch position (default 1)"
        "\n  --os <target>       windows|linux|mac, for {{file:...}} paths (default: this host)"
        if device == "bunny"
        else ""
    )
    # The Ducky runs a compiled inject.bin, so it alone has encoding options.
    ducky = (
        "\n  --layout <name>     Target keyboard layout for encoding (default us)"
        "\n  --inject-bin <path>  compile only: write the encoded inject.bin to a file"
        if device == "ducky"
        else ""
    )
    ducky_example = "\n  hw ducky compile system-prompt-leak --inject-bin inject.bin" if device == "ducky" else ""
    from pistudio.hardware.devices import device_by_name

    _d = device_by_name(device)
    usage = _USAGE.format(
        emoji=_d.emoji if _d else "",
        device=device,
        dialect=dialect,
        label=label,
        extra=extra,
        switch=switch,
        ducky=ducky,
        ducky_example=ducky_example,
    )

    # Every other device handler answers --help; these two reported it as an
    # unknown subcommand, so `hw bunny --help` failed where `hw flipper --help`
    # worked.
    if not args or args[0] in ("--help", "-h", "help"):
        shell.out.info(usage)
        return

    sub = args[0].lower()
    positional, flags = _flags(args[1:])

    if sub == "devices":
        _list_devices(shell, device, label)
        return

    if sub == "tty":
        if device != "bunny":
            shell.out.error("Serial console is only available on the Bash Bunny.")
            return
        try:
            baud = _int_flag(flags, "baud", 115200)
        except ValueError as exc:
            shell.out.error(str(exc))
            return
        _tty(shell, positional[0] if positional else "", baud)
        return

    if sub not in ("compile", "deploy"):
        shell.out.error(cmd.suggest_subcommand(sub, list(_SUBS)))
        return

    if not positional:
        shell.out.usage_error(f"hw {device} {sub} <payload-name>")
        return

    name = positional[0]
    compiled = _compile(shell, device, name, flags)
    if compiled is None:
        return
    script, files, opts = compiled

    if sub == "compile":
        if not _emit_compiled(shell, device, dialect, script, flags, opts):
            return
        if files:
            names = ", ".join(bf.name for bf in files)
            shell.out.info(f"References {len(files)} file(s): {names}. 'deploy' copies them to the device.")
        return

    _deploy(shell, device, label, name, script, files, opts, flags)


def _emit_compiled(
    shell: StudioProtocol,
    device: str,
    dialect: str,
    script: str,
    flags: dict[str, str],
    opts: _CompileOptions,
) -> bool:
    """Print or write the compiled output. Returns False after reporting an error.

    ``--inject-bin <path>`` (Ducky only) writes the encoded binary the device
    actually runs, so a payload can be prepared without the device attached.
    """
    if inject_out := flags.get("inject-bin"):
        if device != "ducky":
            shell.out.error("--inject-bin applies to the Rubber Ducky; the Bash Bunny runs the script directly.")
            return False
        from pistudio.hardware.hak5.encoder import encode

        try:
            binary = encode(script, layout=opts.layout)
        except ValueError as exc:
            shell.out.error(str(exc))
            return False
        try:
            with open(inject_out, "wb") as fh:
                fh.write(binary)
        except OSError as exc:
            shell.out.failed(f"write {inject_out}", str(exc))
            return False
        shell.out.success(f"Encoded inject.bin ({len(binary)} bytes) written to: {inject_out}")
        return True

    if out_path := flags.get("output"):
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(script)
        except OSError as exc:
            shell.out.failed(f"write {out_path}", str(exc))
            return False
        shell.out.success(f"Compiled {dialect} written to: {out_path}")
        return True

    shell.print_raw(script)
    return True


def _deploy(
    shell: StudioProtocol,
    device: str,
    label: str,
    name: str,
    script: str,
    files: list,
    opts: _CompileOptions,
    flags: dict[str, str],
) -> None:
    """Write a compiled *script*, and any files it references, to a device."""
    from pistudio.hardware.hak5.device import (
        deploy_bunny,
        deploy_bunny_files,
        deploy_ducky,
        find_bunny_volumes,
        find_ducky_volumes,
    )

    target = flags.get("path")
    switch = opts.switch

    # Name the destination in the prompt: with two devices attached, "the Bash
    # Bunny" does not say which one is about to be written.
    destination = target
    if destination is None:
        volumes = find_bunny_volumes() if device == "bunny" else find_ducky_volumes()
        destination = volumes[0] if volumes else None
    if destination is None:
        shell.out.error(f"No {label} volume found. Attach the device or pass --path <mount>.")
        return

    detail = f" and {len(files)} file(s)" if files else ""
    if not shell.confirm(f"Deploy '{name}'{detail} to the {label} at {destination}?"):
        shell.out.info("Cancelled.")
        return

    try:
        if device == "bunny":
            path = deploy_bunny(script, path=target, switch=switch)
            deployed_files = deploy_bunny_files(files, path=target, switch=switch) if files else []
        else:
            path = deploy_ducky(script, path=target, layout=opts.layout)
            deployed_files = []
    except (OSError, RuntimeError, ValueError) as exc:
        shell.out.failed(f"deploy to the {label}", str(exc))
        return

    shell.audit.log(
        "hak5_deploy",
        device=device,
        payload=name,
        path=path,
        files=[bf.name for bf in files],
    )
    shell.out.success(f"Deployed '{name}' to {path}")
    for dest in deployed_files:
        shell.out.info(f"  copied {dest}")


def _list_devices(shell: StudioProtocol, device: str, label: str) -> None:
    """Print attached device volumes."""
    from pistudio.hardware.hak5.device import find_bunny_volumes, find_ducky_volumes

    volumes = find_bunny_volumes() if device == "bunny" else find_ducky_volumes()
    if not volumes:
        shell.out.empty_state(f"{label} volumes", f"Attach a {label} in arming/storage mode.")
        return

    t = active_theme()
    shell.console.print(f"\n  [bold {t.accent}]{label}[/]")
    for vol in volumes:
        shell.console.print(f"    [{t.success}]●[/] {vol}")
    shell.console.print("")


def _tty(shell: StudioProtocol, port: str = "", baud: int = 115200) -> None:
    """Open an interactive serial console to the Bash Bunny.

    Args:
        shell: The studio context.
        port: Explicit serial port.  Auto-detected when empty.
        baud: Baud rate.
    """
    import json

    from pistudio.hardware.hak5.serial_console import find_bunny_serial_ports, run_serial_console

    if not port:
        ports = find_bunny_serial_ports()
        if shell.json_mode:
            shell.print_raw(json.dumps({"serial_ports": ports}))
            return
        if not ports:
            shell.out.error("No Bash Bunny serial port found. Attach the Bunny in arming mode.")
            return
        port = ports[0]

    shell.out.info(f"Connecting to {port} — press Ctrl+] to exit.")
    shell.audit.log("bunny_tty", port=port, baud=baud)
    try:
        run_serial_console(port, baud=baud)
    except (OSError, ConnectionError) as exc:
        shell.out.error(f"Could not open the serial console: {exc}")


def complete_hak5(device: str, tokens: list[str], session_dir: str = "") -> list[str]:
    """Return completions for ``hw bunny`` / ``hw ducky``."""
    subs = list(_SUBS) if device == "bunny" else [s for s in _SUBS if s != "tty"]
    if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
        return subs
    if len(tokens) == 1:
        return [s for s in subs if s.startswith(tokens[0])]

    current = tokens[-1]

    # Second positional after compile/deploy is a payload name.
    if tokens[0] in ("compile", "deploy") and len(tokens) == 2:
        from pistudio.commands.payload_flag import complete_payload_names

        return complete_payload_names(session_dir, current)

    flags = ["--output", "--path", "--start-delay", "--default-delay", "--preamble"]
    if device == "bunny":
        flags += ["--switch", "--os", "--baud"]
    else:
        flags += ["--layout", "--inject-bin"]
    return [f for f in flags if f.startswith(current)]
