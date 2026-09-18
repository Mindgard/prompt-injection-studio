"""ngrok tunnel management for the inject server.

Provides NgrokTunnel class that wraps pyngrok to expose the local
inject server on a public internet-resolvable URL.
"""

import logging
import os
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Module-level tunnel status ────────────────────────────────────

_active_tunnel: Optional["NgrokTunnel"] = None


def get_tunnel_status() -> tuple[str, int, datetime] | None:
    """Return ``(public_url, local_port, started_at)`` or ``None``.

    Called by the toolbar to show ngrok tunnel status.
    """
    if _active_tunnel is not None and _active_tunnel.is_running:
        return (
            _active_tunnel.public_url,
            _active_tunnel.port,
            _active_tunnel.started_at,
        )
    return None


def _check_ngrok_deps() -> bool:
    """Check if pyngrok is installed."""
    try:
        import pyngrok  # noqa: F401 — availability check

        return True
    except ImportError:
        return False


@dataclass
class TunnelInfo:
    """Information about an active ngrok tunnel."""

    public_url: str
    local_port: int
    tunnel_name: str
    started_at: datetime = field(default_factory=datetime.now)
    region: str = ""
    domain: str = ""


class NgrokTunnel:
    """Manages an ngrok tunnel to expose a local port publicly.

    Usage:
        tunnel = NgrokTunnel(port=8080)
        tunnel.start()
        print(tunnel.public_url)  # https://abc123.ngrok.io
        tunnel.stop()
    """

    def __init__(
        self,
        port: int,
        authtoken: str = "",
        region: str = "",
        domain: str = "",
    ) -> None:
        """Create an ngrok tunnel manager.

        Args:
            port: Local port to expose.
            authtoken: ngrok auth token (falls back to env/config).
            region: ngrok region (us, eu, ap, au, sa, jp, in).
            domain: Custom domain (requires paid ngrok plan).
        """
        self.port = port
        self.authtoken = authtoken
        self.region = region
        self.domain = domain

        self._tunnel: object | None = None
        self._public_url: str = ""
        self.started_at: datetime | None = None
        self.is_running = False

    @property
    def public_url(self) -> str:
        """Return the public ngrok URL, or empty string if not running."""
        return self._public_url

    def _resolve_authtoken(self) -> str:
        """Resolve auth token from flag, env var, or config file."""
        # 1. Explicit parameter (highest priority)
        if self.authtoken:
            return self.authtoken

        # 2. Environment variable
        env_token = os.environ.get("NGROK_AUTHTOKEN", "")
        if env_token:
            return env_token

        # 3. Studio config file
        config_path = Path.home() / ".pistudio" / "ngrok.yml"
        if config_path.exists():
            try:
                import yaml

                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    if config and "authtoken" in config:
                        return config["authtoken"]
            except (ImportError, OSError, ValueError):
                logger.debug("Failed to read ngrok config from %s", config_path, exc_info=True)

        # 4. Let pyngrok use its default config
        return ""

    def start(self) -> TunnelInfo:
        """Start the ngrok tunnel.

        Returns:
            TunnelInfo with the public URL and metadata.

        Raises:
            ImportError: If pyngrok is not installed.
            RuntimeError: If tunnel fails to start.
        """
        global _active_tunnel

        if self.is_running:
            raise RuntimeError("Tunnel is already running")

        if not _check_ngrok_deps():
            raise ImportError(
                "pyngrok is required for ngrok tunneling. Install with: pip install 'prompt-injection-studio[ngrok]'"
            )

        from pyngrok import conf, ngrok

        # Configure pyngrok
        authtoken = self._resolve_authtoken()
        if authtoken:
            conf.get_default().auth_token = authtoken

        if self.region:
            conf.get_default().region = self.region

        # Build tunnel kwargs
        tunnel_kwargs = {
            "addr": str(self.port),
            "bind_tls": True,  # HTTPS only
        }

        if self.domain:
            tunnel_kwargs["domain"] = self.domain

        try:
            # Open the tunnel
            self._tunnel = ngrok.connect(**tunnel_kwargs)
            self._public_url = self._tunnel.public_url
            self.started_at = datetime.now()
            self.is_running = True
            _active_tunnel = self

            logger.info(f"ngrok tunnel started: {self._public_url} -> localhost:{self.port}")

            return TunnelInfo(
                public_url=self._public_url,
                local_port=self.port,
                tunnel_name=getattr(self._tunnel, "name", ""),
                started_at=self.started_at,
                region=self.region,
                domain=self.domain,
            )

        except Exception as e:
            self.is_running = False
            raise RuntimeError(f"Failed to start ngrok tunnel: {e}") from e

    def stop(self) -> None:
        """Stop the ngrok tunnel."""
        global _active_tunnel

        if not self.is_running:
            return

        try:
            from pyngrok import ngrok

            if self._public_url:
                ngrok.disconnect(self._public_url)
                logger.info(f"ngrok tunnel stopped: {self._public_url}")

        except Exception as e:
            logger.warning(f"Error stopping ngrok tunnel: {e}")

        finally:
            self._tunnel = None
            self._public_url = ""
            self.started_at = None
            self.is_running = False
            if _active_tunnel is self:
                _active_tunnel = None

    @staticmethod
    def open_inspector() -> bool:
        """Open the ngrok web inspector in the default browser.

        Returns:
            True if opened successfully, False otherwise.
        """
        inspector_url = "http://127.0.0.1:4040"
        try:
            webbrowser.open(inspector_url)
            return True
        except OSError:
            return False

    @staticmethod
    def get_inspector_url() -> str:
        """Return the ngrok web inspector URL."""
        return "http://127.0.0.1:4040"


def stop_active_tunnel() -> bool:
    """Stop the active tunnel if one exists.

    Returns:
        True if a tunnel was stopped, False if none was running.
    """
    global _active_tunnel
    if _active_tunnel is not None:
        _active_tunnel.stop()
        return True
    return False
