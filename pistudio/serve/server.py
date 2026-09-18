"""HTTP/HTTPS server for hosting prompt injection payloads.

Provides a PayloadServer that runs in a background thread and serves
payloads at URLs like /p/<slug>. Supports self-signed TLS and ngrok tunneling.
"""

import asyncio
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pistudio.serve.registry import PayloadRegistry, get_registry

logger = logging.getLogger(__name__)

# ── Module-level server status ────────────────────────────────────

_active_server: Optional["PayloadServer"] = None


def get_server_status() -> tuple[bool, str, int, int, str | None] | None:
    """Return ``(is_running, url, port, payload_count, ngrok_url)`` or ``None``.

    Called by the toolbar to show inject server status.
    """
    if _active_server is not None and _active_server.is_running:
        return (
            True,
            _active_server.url,
            _active_server.port,
            len(_active_server.registry),
            _active_server.public_url,
        )
    return None


# ── Request logging ───────────────────────────────────────────────


@dataclass
class RequestLog:
    """A logged HTTP request to the inject server."""

    timestamp: datetime
    path: str
    method: str
    user_agent: str
    remote_ip: str
    slug: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "path": self.path,
            "method": self.method,
            "user_agent": self.user_agent,
            "remote_ip": self.remote_ip,
            "slug": self.slug,
        }


_request_log: list[RequestLog] = []
_request_log_lock = threading.Lock()


def get_request_log() -> list[RequestLog]:
    """Return a copy of the request log."""
    with _request_log_lock:
        return list(_request_log)


def clear_request_log() -> int:
    """Clear the request log. Returns count of cleared entries."""
    with _request_log_lock:
        count = len(_request_log)
        _request_log.clear()
        return count


def _log_request(request, slug: str = "") -> None:
    """Log an incoming request."""
    entry = RequestLog(
        timestamp=datetime.now(),
        path=str(request.url.path),
        method=request.method,
        user_agent=request.headers.get("user-agent", ""),
        remote_ip=request.client.host if request.client else "",
        slug=slug,
    )
    with _request_log_lock:
        _request_log.append(entry)
        # Keep last 1000 requests
        if len(_request_log) > 1000:
            _request_log.pop(0)


def _generate_self_signed_cert(cert_path: str, key_path: str) -> None:
    """Generate a self-signed certificate for TLS."""
    from pistudio.serve.tls import generate_self_signed_cert

    generate_self_signed_cert(cert_path, key_path)


class PayloadServer:
    """HTTP/HTTPS server that hosts prompt injection payloads at URLs."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        tls: bool = False,
        cert_path: str = "",
        key_path: str = "",
        registry: PayloadRegistry | None = None,
        ngrok: bool = False,
        ngrok_authtoken: str = "",
        ngrok_region: str = "",
        ngrok_domain: str = "",
    ) -> None:
        """Create a payload server.

        Args:
            host: Interface to bind to (default: localhost only).
            port: Port to listen on (default: 8080).
            tls: Enable self-signed TLS (default: False).
            cert_path: Path to custom TLS certificate.
            key_path: Path to custom TLS key.
            registry: Payload registry (default: global singleton).
            ngrok: Enable ngrok tunneling for public URL.
            ngrok_authtoken: ngrok auth token (falls back to env/config).
            ngrok_region: ngrok region (us, eu, ap, au, sa, jp, in).
            ngrok_domain: Custom ngrok domain (requires paid plan).
        """
        self.host = host
        self.port = port
        self.tls = tls
        self.cert_path = cert_path
        self.key_path = key_path
        self.registry = registry or get_registry()

        # ngrok settings
        self.ngrok_enabled = ngrok
        self.ngrok_authtoken = ngrok_authtoken
        self.ngrok_region = ngrok_region
        self.ngrok_domain = ngrok_domain
        self._tunnel: object | None = None

        self.is_running = False
        self._server: object | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._temp_cert_dir: str | None = None

    @property
    def url(self) -> str:
        """Return the base URL of the server."""
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def payload_url(self) -> str:
        """Return the payload endpoint URL template."""
        return f"{self.url}/p/{{slug}}"

    @property
    def public_url(self) -> str | None:
        """Return the public ngrok URL, or None if not tunneled."""
        if self._tunnel is not None:
            return self._tunnel.public_url
        return None

    @property
    def effective_url(self) -> str:
        """Return the best URL to use (ngrok if available, else local)."""
        return self.public_url or self.url

    def start(self) -> None:
        """Start the server in a background thread."""
        global _active_server

        if self.is_running:
            raise RuntimeError("Server is already running")

        # Generate self-signed cert if TLS enabled without custom certs
        if self.tls and not (self.cert_path and self.key_path):
            self._temp_cert_dir = tempfile.mkdtemp(prefix="pistudio-serve-")
            self.cert_path = os.path.join(self._temp_cert_dir, "cert.pem")
            self.key_path = os.path.join(self._temp_cert_dir, "key.pem")
            _generate_self_signed_cert(self.cert_path, self.key_path)

        self._thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="inject-server",
        )
        self._thread.start()

        # Wait for server to be ready
        deadline = time.monotonic() + 10.0
        while not self.is_running and time.monotonic() < deadline:
            time.sleep(0.1)

        if not self.is_running:
            raise RuntimeError("Inject server failed to start within 10 seconds")

        _active_server = self
        logger.info(f"Inject server started at {self.url}")

        # Start ngrok tunnel if enabled
        if self.ngrok_enabled:
            self._start_ngrok_tunnel()

    def stop(self) -> None:
        """Stop the server and clear all payloads."""
        global _active_server

        # Stop ngrok tunnel first
        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception as e:
                logger.warning(f"Error stopping ngrok tunnel: {e}")
            self._tunnel = None

        if self._server:
            import uvicorn

            server = self._server
            if isinstance(server, uvicorn.Server):
                server.should_exit = True

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        # Clear payloads (ephemeral)
        self.registry.clear()

        # Clean up temp certs
        if self._temp_cert_dir and os.path.exists(self._temp_cert_dir):
            import shutil

            shutil.rmtree(self._temp_cert_dir, ignore_errors=True)
            self._temp_cert_dir = None

        self.is_running = False
        if _active_server is self:
            _active_server = None

        logger.info("Inject server stopped")

    def _start_ngrok_tunnel(self) -> None:
        """Start the ngrok tunnel."""
        try:
            from pistudio.serve.tunnel import NgrokTunnel

            self._tunnel = NgrokTunnel(
                port=self.port,
                authtoken=self.ngrok_authtoken,
                region=self.ngrok_region,
                domain=self.ngrok_domain,
            )
            self._tunnel.start()
            logger.info(f"ngrok tunnel started: {self._tunnel.public_url}")

        except ImportError as e:
            logger.warning(f"ngrok not available: {e}")
            self._tunnel = None
        except Exception as e:
            logger.warning(f"Failed to start ngrok tunnel: {e}")
            self._tunnel = None

    def stop_tunnel(self) -> bool:
        """Stop just the ngrok tunnel, keep server running.

        Returns:
            True if tunnel was stopped, False if none was running.
        """
        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception as e:
                logger.warning(f"Error stopping ngrok tunnel: {e}")
            self._tunnel = None
            return True
        return False

    def start_tunnel(
        self,
        authtoken: str = "",
        region: str = "",
        domain: str = "",
    ) -> str | None:
        """Start ngrok tunnel on running server.

        Returns:
            Public URL if successful, None otherwise.
        """
        if self._tunnel is not None:
            return self._tunnel.public_url

        self.ngrok_authtoken = authtoken or self.ngrok_authtoken
        self.ngrok_region = region or self.ngrok_region
        self.ngrok_domain = domain or self.ngrok_domain
        self.ngrok_enabled = True

        self._start_ngrok_tunnel()
        return self.public_url

    def _run_server(self) -> None:
        """Run the ASGI server in a new event loop (background thread)."""
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
        from starlette.routing import Route

        registry = self.registry

        async def get_payload(request: Request) -> Response:
            """Serve a payload by slug."""
            slug = request.path_params["slug"]
            _log_request(request, slug=slug)

            # Handle format extensions
            fmt = "text"
            if slug.endswith(".json"):
                slug = slug[:-5]
                fmt = "json"
            elif slug.endswith(".html"):
                slug = slug[:-5]
                fmt = "html"
            elif slug.endswith(".qr"):
                slug = slug[:-3]
                fmt = "qr"

            payload = registry.get(slug)
            if payload is None:
                return PlainTextResponse("Not found", status_code=404)

            # If this is a file payload, serve the binary content
            if payload.is_file:
                headers = {}
                if payload.filename:
                    headers["Content-Disposition"] = f'inline; filename="{payload.filename}"'
                return Response(
                    payload.content,
                    media_type=payload.content_type,
                    headers=headers,
                )

            if fmt == "json":
                return JSONResponse(payload.to_dict())
            elif fmt == "html":
                html = f"""<!DOCTYPE html>
<html>
<head><title>Payload: {slug}</title></head>
<body>
<h1>Payload</h1>
<pre>{payload.text}</pre>
</body>
</html>"""
                return HTMLResponse(html)
            elif fmt == "qr":
                # Return QR code image
                try:
                    import io

                    buf = io.BytesIO()
                    # Generate QR pointing to this payload's URL
                    payload_url = f"{self.url}/p/{slug}"
                    import segno

                    qr = segno.make(payload_url, error="M", micro=False)
                    qr.save(buf, kind="png", scale=10, border=4)
                    buf.seek(0)
                    return Response(buf.read(), media_type="image/png")
                except ImportError:
                    return PlainTextResponse("QR generation not available", status_code=501)
            else:
                return PlainTextResponse(payload.text)

        async def list_payloads(request: Request) -> JSONResponse:
            """List all hosted payloads."""
            _log_request(request)
            payloads = registry.list_all()
            return JSONResponse(
                {
                    "count": len(payloads),
                    "payloads": [p.to_dict() for p in payloads],
                }
            )

        async def add_payload(request: Request) -> JSONResponse:
            """Add a new payload via POST."""
            try:
                body = await request.json()
                text = body.get("text", "")
                name = body.get("name", "")
                slug = body.get("slug", "")

                if not text:
                    return JSONResponse(
                        {"error": "text is required"},
                        status_code=400,
                    )

                payload = registry.add(text=text, name=name, slug=slug)
                return JSONResponse(
                    {
                        "slug": payload.slug,
                        "url": f"{self.url}/p/{payload.slug}",
                        "payload": payload.to_dict(),
                    }
                )
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        async def health(request: Request) -> JSONResponse:
            """Return server health and stats."""
            return JSONResponse(
                {
                    "status": "ok",
                    "url": self.url,
                    "public_url": self.public_url,
                    "tls": self.tls,
                    "ngrok": self.ngrok_enabled and self._tunnel is not None,
                    "payload_count": len(registry),
                }
            )

        async def get_requests(request: Request) -> JSONResponse:
            """Return the request log."""
            log = get_request_log()
            return JSONResponse(
                {
                    "count": len(log),
                    "requests": [r.to_dict() for r in log],
                }
            )

        async def index(request: Request) -> HTMLResponse:
            """Serve an index page listing all hosted payloads."""
            payloads = registry.list_all()
            ngrok_url = self.public_url

            # Build payload list HTML
            if payloads:
                items = []
                for p in payloads:
                    # Description: use name if available, otherwise truncate text
                    if p.is_file:
                        desc = f"[FILE] {p.filename}" if p.filename else f"[FILE] {p.content_type}"
                    elif p.name:
                        desc = p.name
                    else:
                        desc = p.text[:80] + "..." if len(p.text) > 80 else p.text
                    # Escape HTML in description
                    import html

                    desc = html.escape(desc)
                    items.append(f'<li><a href="/p/{p.slug}">{p.slug}</a> — <span class="desc">{desc}</span></li>')
                payload_list = "\n".join(items)
            else:
                payload_list = '<li class="empty">No payloads hosted yet.</li>'

            # ngrok status line
            ngrok_line = ""
            if ngrok_url:
                ngrok_line = (
                    f'<p class="stats ngrok">🌐 Public URL: <code><a href="{ngrok_url}">{ngrok_url}</a></code></p>'
                )

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Prompt Injection Studio</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 40px auto; padding: 0 20px; background: #1a1a2e; color: #eee; }}
        h1 {{ color: #00d4ff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }}
        h2 {{ color: #888; font-weight: normal; margin-top: 30px; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ padding: 12px 15px; margin: 8px 0; background: #16213e; border-radius: 6px;
              border-left: 3px solid #00d4ff; }}
        li.empty {{ color: #666; border-left-color: #444; }}
        a {{ color: #00d4ff; text-decoration: none; font-family: monospace; font-size: 1.1em; }}
        a:hover {{ text-decoration: underline; }}
        .desc {{ color: #aaa; font-size: 0.9em; }}
        .stats {{ color: #666; font-size: 0.85em; margin-top: 30px; }}
        .stats.ngrok {{ color: #4ade80; }}
        code {{ background: #0f3460; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>🎯 Prompt Injection Studio</h1>
    <p class="stats">Server: <code>{self.url}</code> | Payloads: <code>{len(payloads)}</code></p>
    {ngrok_line}

    <h2>Hosted Payloads</h2>
    <ul>
        {payload_list}
    </ul>

    <p class="stats">
        Add payloads via CLI: <code>inject serve add "payload"</code><br>
        Or POST to <code>/payloads</code> with JSON: <code>{{"text": "...", "name": "..."}}</code>
    </p>
</body>
</html>"""
            return HTMLResponse(html_content)

        app = Starlette(
            routes=[
                Route("/", index, methods=["GET"]),
                Route("/p/{slug:path}", get_payload, methods=["GET"]),
                Route("/payloads", list_payloads, methods=["GET"]),
                Route("/payloads", add_payload, methods=["POST"]),
                Route("/health", health, methods=["GET"]),
                Route("/requests", get_requests, methods=["GET"]),
            ],
        )

        # Configure uvicorn
        ssl_kwargs = {}
        if self.tls:
            ssl_kwargs["ssl_certfile"] = self.cert_path
            ssl_kwargs["ssl_keyfile"] = self.key_path

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            **ssl_kwargs,
        )
        self._server = uvicorn.Server(config)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            self.is_running = True
            loop.run_until_complete(self._server.serve())
        except Exception:
            logger.exception("Inject server error")
        finally:
            self.is_running = False
            loop.close()
