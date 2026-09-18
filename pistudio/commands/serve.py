"""The ``serve`` command — host payloads at URLs.

The server is an in-process singleton, so one-shot CLI invocations lose it
between steps; the interactive session is where hosting is actually useful.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pistudio.commands.flags import unknown_flag_message
from pistudio.commands.payload_flag import complete_payload_names
from pistudio.core.command import Command
from pistudio.core.flags import Flag
from pistudio.ui.theme import active_theme

if TYPE_CHECKING:
    from pistudio.core.protocols import StudioProtocol

logger = logging.getLogger(__name__)

_SERVER_INSTALL_HINT = "pip install prompt-injection-studio[serve]"

_NGROK_REGIONS = ("us", "eu", "ap", "au", "sa", "jp", "in")

SERVE_FLAGS: tuple[Flag, ...] = (
    Flag("--host", value="ip", help="Interface to bind (default 127.0.0.1)"),
    Flag("--port", value="n", help="TCP port to listen on (default 8080)"),
    Flag("--tls", help="Serve over self-signed HTTPS"),
    Flag("--payload", value="name", help="Host a payload from the library", completes="payload"),
    Flag("--slug", value="slug", help="Use a specific URL slug rather than a random one"),
    Flag("--ngrok", help="Expose on a public ngrok URL"),
    Flag("--ngrok-authtoken", value="token", help="ngrok auth token (or set NGROK_AUTHTOKEN)"),
    Flag("--ngrok-region", value="region", help="ngrok region", choices=_NGROK_REGIONS, completes="choices"),
    Flag("--ngrok-domain", value="domain", help="Custom ngrok domain (paid plans)"),
)

#: The spellings ``unknown_flag_message`` and completion offer.
_SERVE_FLAGS = tuple(sp for f in SERVE_FLAGS for sp in f.spellings)


class ServeCommand(Command):
    """Host prompt injection payloads at URLs"""

    name = "serve"
    aliases = ()
    help = "Host payloads at URLs, optionally over HTTPS or ngrok"
    flags = SERVE_FLAGS
    namespace = True
    subcommand_aliases = {"ls": "list"}
    subcommands = {
        "add": "Host another payload on the running server",
        "remove": "Stop hosting a payload by slug",
        "list": "List everything currently hosted",
        "status": "Show server status",
        "stop": "Stop the server",
        "tunnel": "Manage the ngrok tunnel",
        "requests": "Show who fetched the hosted URLs",
        "inspect": "Open the ngrok web inspector",
    }
    usage = (
        'Usage: serve ["<payload>"] [options]\n\n'
        "Start a local server hosting a payload and print its URL.  Useful for\n"
        "testing whether a model will fetch and act on remote content.\n\n"
        '  serve "<payload>"           Start the server hosting this text\n'
        "  serve --payload <name>      Host a payload from the library\n"
        '  serve add "<payload>"       Host another on the running server\n'
        "  serve remove <slug>         Stop hosting one\n"
        "  serve list                  Everything currently hosted\n"
        "  serve status                Is it running, and where\n"
        "  serve stop                  Stop the server\n"
        "  serve requests              Who fetched the URLs (clear with 'requests clear')\n\n"
        "Options:\n"
        "  --host <ip>         Interface to bind (default 127.0.0.1)\n"
        "  --port <n>          Port to listen on (default 8080)\n"
        "  --tls               Serve over self-signed HTTPS\n"
        "  --payload <name>    Host a payload from the library\n"
        "  --slug <slug>       Use a specific URL slug rather than a random one\n\n"
        "Public URLs via ngrok:\n"
        '  serve "<payload>" --ngrok   Expose on a public ngrok URL\n'
        "  serve tunnel start|stop     Manage the tunnel on a running server\n"
        "  serve inspect               Open ngrok's request inspector\n"
        "  --ngrok-authtoken <token>   Auth token (or set NGROK_AUTHTOKEN)\n"
        "  --ngrok-region <region>     us, eu, ap, au, sa, jp or in\n"
        "  --ngrok-domain <domain>     Custom domain (paid plans)\n\n"
        "Examples:\n"
        '  serve "Ignore all previous instructions"\n'
        "  serve --payload ignore-instructions --host 0.0.0.0\n"
        '  serve "Leak the system prompt" --ngrok\n'
        "  serve requests\n\n"
        "Binding to 0.0.0.0 or opening an ngrok tunnel exposes the payload\n"
        "beyond this machine.  Only do that on networks you are authorised to test."
    )

    # Shown beside each flag in the completion dropdown.
    # Derived from SERVE_FLAGS via Command.flag_descriptions.

    def execute(self, shell: StudioProtocol, args: list[str]) -> None:
        """Run the ``serve`` command."""
        serve(shell, args)

    def complete(self, shell: StudioProtocol, tokens: list[str]) -> list[str]:
        """Return tab-completion candidates for ``serve``."""
        from pistudio.ui.completer import CompletionItem

        subs = [CompletionItem(name, help_text, "subcommand") for name, help_text in self.subcommands.items()]

        if not tokens or (len(tokens) == 1 and not tokens[0].strip()):
            return [*subs, *_SERVE_FLAGS]

        current = tokens[-1]

        if len(tokens) == 1:
            return [o for o in [*subs, *_SERVE_FLAGS] if _text(o).startswith(current)]

        first = tokens[0].lower()
        previous = tokens[-2]

        if first == "add":
            if previous == "--payload":
                return complete_payload_names(shell, current)
            return [f for f in ("--payload", "--slug") if f.startswith(current)]

        if first == "remove":
            return _hosted_slugs(current)

        if first == "tunnel":
            if previous == "--region":
                return [r for r in _NGROK_REGIONS if r.startswith(current)]
            options = ("start", "stop", "--authtoken", "--region", "--domain")
            return [o for o in options if o.startswith(current)]

        if first == "requests":
            return [s for s in ("clear",) if s.startswith(current)]

        if previous == "--host":
            return [h for h in ("127.0.0.1", "0.0.0.0", "localhost") if h.startswith(current)]
        if previous == "--port":
            return [p for p in ("8080", "8000", "9000", "3000") if p.startswith(current)]
        if previous == "--payload":
            return complete_payload_names(shell, current)
        if previous == "--ngrok-region":
            return [r for r in _NGROK_REGIONS if r.startswith(current)]

        return [f for f in _SERVE_FLAGS if f.startswith(current)]


def _text(option) -> str:
    """Return the completion text of a CompletionItem or plain string."""
    return getattr(option, "text", option)


def _hosted_slugs(prefix: str) -> list[str]:
    """Return hosted payload slugs starting with *prefix*."""
    try:
        from pistudio.serve.registry import get_registry

        return [p.slug for p in get_registry().list_all() if p.slug.startswith(prefix)]
    except Exception:
        return []


def _check_server_deps() -> bool:
    """Check if server dependencies are installed."""
    try:
        import starlette  # noqa: F401
        import uvicorn  # noqa: F401

        return True
    except ImportError:
        return False


def serve(shell: StudioProtocol, args: list[str]) -> None:
    """Handle serve command and its subcommands."""
    if args:
        sub = args[0].lower()
        if sub == "add":
            serve_add(shell, args[1:])
            return
        elif sub == "remove":
            serve_remove(shell, args[1:])
            return
        elif sub in ("list", "ls"):
            serve_list(shell)
            return
        elif sub == "stop":
            serve_stop(shell)
            return
        elif sub == "status":
            serve_status(shell)
            return
        elif sub == "tunnel":
            serve_tunnel(shell, args[1:])
            return
        elif sub == "requests":
            serve_requests(shell, args[1:])
            return
        elif sub == "inspect":
            serve_inspect(shell)
            return

    serve_start(shell, args)


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", ""})


def _confirm_exposure(shell: StudioProtocol, host: str, ngrok_enabled: bool) -> bool:
    """Ask before serving payloads anywhere other than loopback.

    The default binds to 127.0.0.1, which reaches nothing but this machine.
    ``--host`` and ``--ngrok`` both change that, and ngrok in particular
    publishes to the open internet where a URL can be cached or indexed even
    after the tunnel is closed. Neither used to say anything: the ngrok path
    printed the public URL as a success line.

    Returns:
        True to carry on, False if the operator declined.
    """
    if ngrok_enabled:
        warning = (
            "Publish payloads to the public internet via ngrok? "
            "Anyone with the URL can fetch them, and it may be cached or indexed."
        )
    elif host not in _LOOPBACK_HOSTS:
        warning = f"Serve payloads on {host}, reachable by other hosts on the network?"
    else:
        return True

    if not shell.confirm(warning):
        shell.out.info("Cancelled.")
        return False
    return True


def serve_start(shell: StudioProtocol, args: list[str]) -> None:
    """Start the payload hosting server."""
    from pistudio.serve.server import PayloadServer, get_server_status

    if not _check_server_deps():
        shell.out.error(f"Server dependencies not installed. {_SERVER_INSTALL_HINT}")
        return

    status = get_server_status()
    if status is not None:
        shell.out.error(f"Server already running at {status[1]}")
        shell.out.info("Use 'serve stop' to stop it first.")
        return

    t = active_theme()

    host = "127.0.0.1"
    port = 8080
    tls = False
    payload_text = None
    payload_name = None
    slug = None
    ngrok_enabled = False
    ngrok_authtoken = ""
    ngrok_region = ""
    ngrok_domain = ""

    i = 0
    positional = []
    while i < len(args):
        arg = args[i]
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif arg == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                shell.out.error(f"Invalid port: {args[i + 1]}")
                return
            i += 2
        elif arg == "--tls":
            tls = True
            i += 1
        elif arg == "--ngrok":
            ngrok_enabled = True
            i += 1
        elif arg == "--ngrok-authtoken" and i + 1 < len(args):
            ngrok_authtoken = args[i + 1]
            ngrok_enabled = True
            i += 2
        elif arg == "--ngrok-region" and i + 1 < len(args):
            ngrok_region = args[i + 1]
            ngrok_enabled = True
            i += 2
        elif arg == "--ngrok-domain" and i + 1 < len(args):
            ngrok_domain = args[i + 1]
            ngrok_enabled = True
            i += 2
        elif arg == "--payload" and i + 1 < len(args):
            payload_name = args[i + 1]
            i += 2
        elif arg == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
            i += 2
        elif arg.startswith("-"):
            shell.out.error(unknown_flag_message(arg, _SERVE_FLAGS))
            return
        else:
            positional.append(arg)
            i += 1

    if positional:
        payload_text = " ".join(positional)
    elif payload_name:
        # Aliased: a local variable in this function is also called payload_text.
        from pistudio.commands.payload_flag import payload_text as resolve_named

        resolved = resolve_named(shell, payload_name)
        if resolved is None:
            return
        payload_text = resolved

    if not _confirm_exposure(shell, host, ngrok_enabled):
        return

    try:
        server = PayloadServer(
            host=host,
            port=port,
            tls=tls,
            ngrok=ngrok_enabled,
            ngrok_authtoken=ngrok_authtoken,
            ngrok_region=ngrok_region,
            ngrok_domain=ngrok_domain,
        )
        server.start()

        shell.console.print(f"\n  [{t.success}]✓[/] Inject server started")
        shell.console.print(f"  [{t.accent}]Local URL:[/] {server.url}")
        if server.public_url:
            shell.console.print(f"  [{t.success}]🌐 Public URL:[/] [{t.accent}]{server.public_url}[/]")
        if tls:
            shell.console.print(f"  [{t.muted}]TLS: Self-signed certificate[/]")
        shell.console.print()

        if payload_text:
            from pistudio.serve.registry import get_registry

            registry = get_registry()
            hosted = registry.add(text=payload_text, name=payload_name or "", slug=slug or "")
            payload_url = f"{server.url}/p/{hosted.slug}"
            shell.console.print(f"  [{t.success}]✓[/] Payload hosted at: [{t.accent}]{payload_url}[/]")
            shell.console.print(f"  [{t.muted}]Slug: {hosted.slug}[/]")
            shell.console.print()

        shell.console.print(f"  [{t.muted}]Use 'serve add' to host more payloads[/]")
        shell.console.print(f"  [{t.muted}]Use 'serve stop' to stop the server[/]")
        if ngrok_enabled and server.public_url:
            shell.console.print(f"  [{t.muted}]Use 'serve requests' to view access log[/]")
            shell.console.print(f"  [{t.muted}]Use 'serve inspect' to open ngrok inspector[/]")
        shell.console.print()

        shell.audit.log("inject_serve", host=host, port=port, tls=tls, ngrok=ngrok_enabled)

    except ImportError as e:
        shell.out.error(str(e))
    except Exception as e:
        shell.out.error(f"Failed to start server: {e}")


def serve_add(shell: StudioProtocol, args: list[str]) -> None:
    """Add a payload to the running server."""
    from pistudio.serve.registry import get_registry
    from pistudio.serve.server import get_server_status

    status = get_server_status()
    if status is None:
        shell.out.error("No server running. Use 'serve' first.")
        return

    t = active_theme()
    server_url = status[1]

    payload_name = None
    slug = None
    i = 0
    positional = []
    while i < len(args):
        arg = args[i]
        if arg == "--payload" and i + 1 < len(args):
            payload_name = args[i + 1]
            i += 2
        elif arg == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
            i += 2
        elif arg.startswith("-"):
            shell.out.error(unknown_flag_message(arg, _SERVE_FLAGS))
            return
        else:
            positional.append(arg)
            i += 1

    if positional:
        payload_text = " ".join(positional)
    elif payload_name:
        # Aliased: a local variable in this function is also called payload_text.
        from pistudio.commands.payload_flag import payload_text as resolve_named

        resolved = resolve_named(shell, payload_name)
        if resolved is None:
            return
        payload_text = resolved
    else:
        shell.out.error('Usage: serve add "<payload>" or serve add --payload <name>')
        return

    try:
        registry = get_registry()
        hosted = registry.add(text=payload_text, name=payload_name or "", slug=slug or "")
        payload_url = f"{server_url}/p/{hosted.slug}"
        shell.console.print(f"  [{t.success}]✓[/] Payload hosted at: [{t.accent}]{payload_url}[/]")
        shell.console.print(f"  [{t.muted}]Slug: {hosted.slug}[/]")
        shell.audit.log("inject_serve_add", slug=hosted.slug)
    except ValueError as e:
        shell.out.error(str(e))


def serve_remove(shell: StudioProtocol, args: list[str]) -> None:
    """Remove a payload from the running server."""
    from pistudio.serve.registry import get_registry
    from pistudio.serve.server import get_server_status

    status = get_server_status()
    if status is None:
        shell.out.error("No server running.")
        return

    if not args:
        shell.out.error("Usage: serve remove <slug>")
        return

    slug = args[0]
    registry = get_registry()
    if registry.remove(slug):
        t = active_theme()
        shell.console.print(f"  [{t.success}]✓[/] Removed payload '{slug}'")
        shell.audit.log("inject_serve_remove", slug=slug)
    else:
        shell.out.error(f"Payload '{slug}' not found.")


def serve_list(shell: StudioProtocol) -> None:
    """List all hosted payloads."""
    from pistudio.serve.registry import get_registry
    from pistudio.serve.server import get_server_status

    status = get_server_status()
    if status is None:
        shell.out.error("No server running. Use 'serve' first.")
        return

    t = active_theme()
    server_url = status[1]
    registry = get_registry()
    payloads = registry.list_all()

    if shell.json_mode:
        data = {
            "server_url": server_url,
            "payloads": [p.to_dict() for p in payloads],
        }
        shell.print_raw(json.dumps(data, indent=2))
        return

    if not payloads:
        shell.console.print(f"  [{t.muted}]No payloads hosted.[/]")
        shell.console.print(f"  [{t.muted}]Use 'serve add' to host a payload.[/]")
        return

    shell.console.print(f"\n  [{t.secondary} bold]Hosted Payloads[/] ({server_url})\n")
    for p in payloads:
        name_part = f" [{t.muted}]({p.name})[/]" if p.name else ""
        preview = p.text[:40] + "..." if len(p.text) > 40 else p.text
        shell.console.print(f"  [{t.accent}]{p.slug}[/]{name_part}")
        shell.console.print(f"    [{t.muted}]{preview}[/]")
    shell.console.print()


def serve_stop(shell: StudioProtocol) -> None:
    """Stop the payload server."""
    from pistudio.serve.server import get_server_status

    status = get_server_status()
    if status is None:
        shell.out.empty_state("server running", "Start one with 'server'.")
        return

    t = active_theme()
    from pistudio.serve import server as server_module

    if server_module._active_server is not None:
        server_module._active_server.stop()
        shell.console.print(f"  [{t.success}]✓[/] Server stopped")
        shell.audit.log("inject_serve_stop")
    else:
        shell.out.error("Server reference not found.")


def serve_status(shell: StudioProtocol) -> None:
    """Show server status."""
    from pistudio.serve.server import get_request_log, get_server_status

    t = active_theme()
    status = get_server_status()

    if shell.json_mode:
        if status:
            shell.print_raw(
                json.dumps(
                    {
                        "running": True,
                        "url": status[1],
                        "port": status[2],
                        "payload_count": status[3],
                        "ngrok_url": status[4],
                    }
                )
            )
        else:
            shell.print_raw(json.dumps({"running": False}))
        return

    if status is None:
        shell.console.print(f"  [{t.muted}]Server not running.[/]")
        shell.console.print(f"  [{t.muted}]Use 'serve' to start.[/]")
        return

    _, url, port, count, ngrok_url = status
    request_count = len(get_request_log())

    shell.console.print(f"\n  [{t.success}]●[/] Inject Server Running")
    shell.console.print(f"  [{t.accent}]Local URL:[/] {url}")
    if ngrok_url:
        shell.console.print(f"  [{t.success}]🌐 Public URL:[/] [{t.accent}]{ngrok_url}[/]")
    shell.console.print(f"  [{t.muted}]Port:[/] {port}")
    shell.console.print(f"  [{t.muted}]Payloads:[/] {count}")
    shell.console.print(f"  [{t.muted}]Requests logged:[/] {request_count}")
    shell.console.print()


def serve_tunnel(shell: StudioProtocol, args: list[str]) -> None:
    """Manage ngrok tunnel."""
    from pistudio.serve import server as server_module
    from pistudio.serve.server import get_server_status

    t = active_theme()
    status = get_server_status()

    if status is None:
        shell.out.error("No server running. Use 'serve' first.")
        return

    server = server_module._active_server
    if server is None:
        shell.out.error("Server reference not found.")
        return

    if args:
        sub = args[0].lower()
        if sub == "stop":
            if server.stop_tunnel():
                shell.console.print(f"  [{t.success}]✓[/] ngrok tunnel stopped")
                shell.console.print(f"  [{t.muted}]Local server still running at {server.url}[/]")
            else:
                shell.out.info("No tunnel running.")
            return
        elif sub == "start":
            authtoken = ""
            region = ""
            domain = ""
            i = 1
            while i < len(args):
                arg = args[i]
                if arg == "--authtoken" and i + 1 < len(args):
                    authtoken = args[i + 1]
                    i += 2
                elif arg == "--region" and i + 1 < len(args):
                    region = args[i + 1]
                    i += 2
                elif arg == "--domain" and i + 1 < len(args):
                    domain = args[i + 1]
                    i += 2
                else:
                    i += 1

            if not _confirm_exposure(shell, "", ngrok_enabled=True):
                return

            public_url = server.start_tunnel(authtoken=authtoken, region=region, domain=domain)
            if public_url:
                shell.console.print(f"  [{t.success}]🌐 Tunnel started:[/] [{t.accent}]{public_url}[/]")
            else:
                shell.out.error("Failed to start ngrok tunnel. Check NGROK_AUTHTOKEN.")
            return

    if server.public_url:
        shell.console.print(f"\n  [{t.success}]🌐[/] ngrok Tunnel Active")
        shell.console.print(f"  [{t.accent}]Public URL:[/] {server.public_url}")
        shell.console.print(f"  [{t.muted}]Local:[/] {server.url}")
        shell.console.print(f"\n  [{t.muted}]Use 'serve tunnel stop' to close tunnel[/]")
    else:
        shell.console.print(f"  [{t.muted}]No ngrok tunnel active.[/]")
        shell.console.print(f"  [{t.muted}]Use 'serve tunnel start' to create one.[/]")
    shell.console.print()


def serve_requests(shell: StudioProtocol, args: list[str]) -> None:
    """Show request log."""
    from pistudio.serve.server import clear_request_log, get_request_log, get_server_status

    t = active_theme()
    status = get_server_status()

    if status is None:
        shell.out.error("No server running.")
        return

    if args and args[0].lower() == "clear":
        count = clear_request_log()
        shell.console.print(f"  [{t.success}]✓[/] Cleared {count} request log entries")
        return

    requests = get_request_log()

    if shell.json_mode:
        shell.print_raw(
            json.dumps(
                {
                    "count": len(requests),
                    "requests": [r.to_dict() for r in requests],
                }
            )
        )
        return

    if not requests:
        shell.console.print(f"  [{t.muted}]No requests logged yet.[/]")
        shell.console.print(f"  [{t.muted}]Requests to payload URLs will appear here.[/]")
        return

    shell.console.print(f"\n  [{t.secondary} bold]Request Log[/] ({len(requests)} requests)\n")

    for req in reversed(requests[-20:]):
        time_str = req.timestamp.strftime("%H:%M:%S")
        slug_part = f" → [{t.accent}]{req.slug}[/]" if req.slug else ""
        ua_short = req.user_agent[:50] + "..." if len(req.user_agent) > 50 else req.user_agent
        shell.console.print(f"  [{t.muted}]{time_str}[/] {req.method} {req.path}{slug_part}")
        shell.console.print(f"    [{t.muted}]IP: {req.remote_ip} | UA: {ua_short}[/]")

    if len(requests) > 20:
        shell.console.print(f"\n  [{t.muted}]... and {len(requests) - 20} more (showing last 20)[/]")

    shell.console.print(f"\n  [{t.muted}]Use 'serve requests clear' to clear log[/]")
    shell.console.print()


def serve_inspect(shell: StudioProtocol) -> None:
    """Open ngrok web inspector."""
    from pistudio.serve import server as server_module
    from pistudio.serve.server import get_server_status

    t = active_theme()
    status = get_server_status()

    if status is None:
        shell.out.error("No server running.")
        return

    server = server_module._active_server
    if server is None or not server.public_url:
        shell.out.error("No ngrok tunnel active. Start with 'serve --ngrok'")
        return

    try:
        from pistudio.serve.tunnel import NgrokTunnel

        inspector_url = NgrokTunnel.get_inspector_url()

        if NgrokTunnel.open_inspector():
            shell.console.print(f"  [{t.success}]✓[/] Opened ngrok inspector in browser")
            shell.console.print(f"  [{t.muted}]URL: {inspector_url}[/]")
        else:
            shell.console.print(f"  [{t.muted}]Open manually: {inspector_url}[/]")

    except ImportError:
        shell.out.error("ngrok not available. Install with: pip install 'prompt-injection-studio[ngrok]'")
