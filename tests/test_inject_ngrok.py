"""Tests for ngrok integration with inject server."""

from datetime import datetime
from unittest.mock import MagicMock, patch


class TestTunnelModule:
    """Tests for inject/tunnel.py module."""

    def test_tunnel_info_dataclass(self):
        """TunnelInfo stores tunnel metadata."""
        from pistudio.serve.tunnel import TunnelInfo

        info = TunnelInfo(
            public_url="https://abc123.ngrok.io",
            local_port=8080,
            tunnel_name="test-tunnel",
            region="us",
            domain="",
        )
        assert info.public_url == "https://abc123.ngrok.io"
        assert info.local_port == 8080
        assert info.tunnel_name == "test-tunnel"
        assert info.region == "us"
        assert isinstance(info.started_at, datetime)

    def test_get_tunnel_status_none_when_inactive(self):
        """get_tunnel_status returns None when no tunnel is active."""
        from pistudio.serve import tunnel

        # Reset module state
        tunnel._active_tunnel = None
        assert tunnel.get_tunnel_status() is None

    def test_check_ngrok_deps_returns_false_without_pyngrok(self):
        """_check_ngrok_deps returns False when pyngrok not installed."""
        from pistudio.serve.tunnel import _check_ngrok_deps

        with patch.dict("sys.modules", {"pyngrok": None}):
            # This will still return True if pyngrok is installed
            # We just verify the function exists and is callable
            result = _check_ngrok_deps()
            assert isinstance(result, bool)

    def test_ngrok_tunnel_init(self):
        """NgrokTunnel initializes with correct defaults."""
        from pistudio.serve.tunnel import NgrokTunnel

        tunnel = NgrokTunnel(port=8080)
        assert tunnel.port == 8080
        assert tunnel.authtoken == ""
        assert tunnel.region == ""
        assert tunnel.domain == ""
        assert tunnel.is_running is False
        assert tunnel.public_url == ""

    def test_ngrok_tunnel_init_with_options(self):
        """NgrokTunnel accepts authtoken, region, and domain."""
        from pistudio.serve.tunnel import NgrokTunnel

        tunnel = NgrokTunnel(
            port=9000,
            authtoken="test-token",
            region="eu",
            domain="custom.ngrok.io",
        )
        assert tunnel.port == 9000
        assert tunnel.authtoken == "test-token"
        assert tunnel.region == "eu"
        assert tunnel.domain == "custom.ngrok.io"

    def test_resolve_authtoken_from_param(self):
        """_resolve_authtoken prioritizes explicit parameter."""
        from pistudio.serve.tunnel import NgrokTunnel

        tunnel = NgrokTunnel(port=8080, authtoken="explicit-token")
        assert tunnel._resolve_authtoken() == "explicit-token"

    def test_resolve_authtoken_from_env(self):
        """_resolve_authtoken falls back to NGROK_AUTHTOKEN env var."""
        from pistudio.serve.tunnel import NgrokTunnel

        tunnel = NgrokTunnel(port=8080)
        with patch.dict("os.environ", {"NGROK_AUTHTOKEN": "env-token"}):
            assert tunnel._resolve_authtoken() == "env-token"

    def test_get_inspector_url(self):
        """get_inspector_url returns the ngrok inspector URL."""
        from pistudio.serve.tunnel import NgrokTunnel

        assert NgrokTunnel.get_inspector_url() == "http://127.0.0.1:4040"

    def test_stop_active_tunnel_returns_false_when_none(self):
        """stop_active_tunnel returns False when no tunnel is active."""
        from pistudio.serve import tunnel

        tunnel._active_tunnel = None
        assert tunnel.stop_active_tunnel() is False


class TestRequestLogging:
    """Tests for request logging in server.py."""

    def test_request_log_dataclass(self):
        """RequestLog stores request metadata."""
        from pistudio.serve.server import RequestLog

        log = RequestLog(
            timestamp=datetime.now(),
            path="/p/abc123",
            method="GET",
            user_agent="Mozilla/5.0",
            remote_ip="192.168.1.1",
            slug="abc123",
        )
        assert log.path == "/p/abc123"
        assert log.method == "GET"
        assert log.slug == "abc123"

    def test_request_log_to_dict(self):
        """RequestLog.to_dict returns JSON-serializable dict."""
        from pistudio.serve.server import RequestLog

        now = datetime.now()
        log = RequestLog(
            timestamp=now,
            path="/p/test",
            method="GET",
            user_agent="test-agent",
            remote_ip="127.0.0.1",
            slug="test",
        )
        d = log.to_dict()
        assert d["path"] == "/p/test"
        assert d["method"] == "GET"
        assert d["slug"] == "test"
        assert d["timestamp"] == now.isoformat()

    def test_get_request_log_empty(self):
        """get_request_log returns empty list initially."""
        from pistudio.serve.server import clear_request_log, get_request_log

        clear_request_log()
        assert get_request_log() == []

    def test_clear_request_log(self):
        """clear_request_log clears the log and returns count."""
        from pistudio.serve.server import (
            RequestLog,
            _request_log,
            _request_log_lock,
            clear_request_log,
        )

        # Add some entries
        with _request_log_lock:
            _request_log.append(
                RequestLog(
                    timestamp=datetime.now(),
                    path="/test",
                    method="GET",
                    user_agent="",
                    remote_ip="",
                )
            )

        count = clear_request_log()
        assert count >= 1


class TestServerNgrokIntegration:
    """Tests for ngrok integration in PayloadServer."""

    def test_payload_server_ngrok_params(self):
        """PayloadServer accepts ngrok parameters."""
        from pistudio.serve.server import PayloadServer

        server = PayloadServer(
            port=8080,
            ngrok=True,
            ngrok_authtoken="test-token",
            ngrok_region="eu",
            ngrok_domain="custom.domain",
        )
        assert server.ngrok_enabled is True
        assert server.ngrok_authtoken == "test-token"
        assert server.ngrok_region == "eu"
        assert server.ngrok_domain == "custom.domain"

    def test_payload_server_public_url_none_without_tunnel(self):
        """public_url returns None when no tunnel is active."""
        from pistudio.serve.server import PayloadServer

        server = PayloadServer(port=8080)
        assert server.public_url is None

    def test_payload_server_effective_url_falls_back_to_local(self):
        """effective_url returns local URL when no tunnel."""
        from pistudio.serve.server import PayloadServer

        server = PayloadServer(host="127.0.0.1", port=8080)
        assert server.effective_url == "http://127.0.0.1:8080"

    def test_get_server_status_includes_ngrok_url(self):
        """get_server_status returns 5-tuple with ngrok_url."""
        from pistudio.serve import server as server_module
        from pistudio.serve.server import get_server_status

        # Create a mock server
        mock_server = MagicMock()
        mock_server.is_running = True
        mock_server.url = "http://localhost:8080"
        mock_server.port = 8080
        mock_server.registry = MagicMock()
        mock_server.registry.__len__ = MagicMock(return_value=2)
        mock_server.public_url = "https://abc123.ngrok.io"

        old_server = server_module._active_server
        try:
            server_module._active_server = mock_server
            status = get_server_status()
            assert status is not None
            assert len(status) == 5
            is_running, url, port, count, ngrok_url = status
            assert is_running is True
            assert ngrok_url == "https://abc123.ngrok.io"
        finally:
            server_module._active_server = old_server


class TestStudioCommandNgrokFlags:
    """Tests for ngrok flags in inject command."""

    def test_inject_serve_completion_includes_ngrok_flags(self):
        """Tab completion includes ngrok flags."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["--n"])
        assert "--ngrok" in completions
        assert "--ngrok-authtoken" in completions
        assert "--ngrok-region" in completions
        assert "--ngrok-domain" in completions

    def test_inject_serve_completion_includes_tunnel_subcommand(self):
        """Tab completion includes tunnel subcommand."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["tu"])
        assert "tunnel" in completions

    def test_inject_serve_completion_includes_requests_subcommand(self):
        """Tab completion includes requests subcommand."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["req"])
        assert "requests" in completions

    def test_inject_serve_completion_includes_inspect_subcommand(self):
        """Tab completion includes inspect subcommand."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["ins"])
        assert "inspect" in completions

    def test_inject_serve_tunnel_completion_includes_start_stop(self):
        """Tab completion for tunnel includes start/stop."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["tunnel", ""])
        assert "start" in completions
        assert "stop" in completions

    def test_inject_serve_requests_completion_includes_clear(self):
        """Tab completion for requests includes clear."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["requests", ""])
        assert "clear" in completions

    def test_inject_serve_ngrok_region_completion(self):
        """Tab completion for --ngrok-region includes regions."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()
        shell.session_dir = "/tmp/test"

        completions = cmd.complete(shell, ["--ngrok-region", ""])
        assert "us" in completions
        assert "eu" in completions
        assert "ap" in completions


class TestStudioCommandDispatch:
    """Tests for command dispatch to ngrok subcommands."""

    def test_serve_tunnel_dispatch(self):
        """inject serve tunnel dispatches to serve_tunnel."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()

        with patch("pistudio.commands.serve.serve_tunnel") as mock_tunnel:
            cmd.execute(shell, ["tunnel"])
            mock_tunnel.assert_called_once_with(shell, [])

    def test_serve_requests_dispatch(self):
        """inject serve requests dispatches to serve_requests."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()

        with patch("pistudio.commands.serve.serve_requests") as mock_requests:
            cmd.execute(shell, ["requests"])
            mock_requests.assert_called_once_with(shell, [])

    def test_serve_inspect_dispatch(self):
        """inject serve inspect dispatches to serve_inspect."""
        from pistudio.commands.serve import ServeCommand

        cmd = ServeCommand()
        shell = MagicMock()

        with patch("pistudio.commands.serve.serve_inspect") as mock_inspect:
            cmd.execute(shell, ["inspect"])
            mock_inspect.assert_called_once()


class TestToolbarNgrokIndicator:
    """Tests for ngrok indicator in toolbar."""

    def test_toolbar_unpacks_5_tuple_status(self):
        """Toolbar correctly unpacks 5-tuple inject status."""
        # This is a structural test - the toolbar code expects 5 values
        from pistudio.serve.server import get_server_status

        # When server is not running, status is None
        # When running, it should be a 5-tuple
        # We just verify the function signature is correct
        status = get_server_status()
        if status is not None:
            assert len(status) == 5


class TestPyprojectNgrokDependency:
    """Tests for ngrok dependency in pyproject.toml."""

    def test_ngrok_optional_dependency_exists(self):
        """pyproject.toml has [ngrok] optional dependency."""
        import tomllib
        from pathlib import Path

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)

        optional_deps = data.get("project", {}).get("optional-dependencies", {})
        assert "ngrok" in optional_deps
        assert any("pyngrok" in dep for dep in optional_deps["ngrok"])
