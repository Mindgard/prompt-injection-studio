"""The payload server must ask before it becomes reachable off this machine.

Serving on 127.0.0.1 reaches nothing but the local machine. ``--host`` opens
it to the network and ``--ngrok`` publishes it to the open internet, where a
URL can be cached or indexed after the tunnel closes. Neither used to ask:
the ngrok path printed the public URL as a success line.
"""

from unittest.mock import MagicMock, patch

import pytest

from pistudio.commands.serve import _confirm_exposure, serve_start


def _shell(answer: bool = True):
    shell = MagicMock()
    shell.confirm.return_value = answer
    shell.out = MagicMock()
    return shell


class TestConfirmExposure:
    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", ""])
    def test_loopback_needs_no_confirmation(self, host):
        shell = _shell()

        assert _confirm_exposure(shell, host, ngrok_enabled=False) is True
        shell.confirm.assert_not_called()

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "10.0.0.1", "::"])
    def test_a_non_loopback_host_is_confirmed(self, host):
        shell = _shell()

        assert _confirm_exposure(shell, host, ngrok_enabled=False) is True
        shell.confirm.assert_called_once()
        assert host in shell.confirm.call_args[0][0]

    def test_ngrok_is_confirmed_even_on_loopback(self):
        """The tunnel reaches the payload regardless of the bind address."""
        shell = _shell()

        assert _confirm_exposure(shell, "127.0.0.1", ngrok_enabled=True) is True
        shell.confirm.assert_called_once()

    def test_the_ngrok_warning_says_it_is_public(self):
        shell = _shell()

        _confirm_exposure(shell, "127.0.0.1", ngrok_enabled=True)

        assert "public internet" in shell.confirm.call_args[0][0]

    @pytest.mark.parametrize(
        ("host", "ngrok"),
        [("0.0.0.0", False), ("127.0.0.1", True), ("0.0.0.0", True)],
    )
    def test_declining_stops_the_server(self, host, ngrok):
        shell = _shell(answer=False)

        assert _confirm_exposure(shell, host, ngrok_enabled=ngrok) is False
        shell.out.info.assert_called_once()


class TestServeStartHonoursTheGate:
    def _start(self, shell, args):
        with (
            patch("pistudio.commands.serve._check_server_deps", return_value=True),
            patch("pistudio.serve.server.get_server_status", return_value=None),
            patch("pistudio.serve.server.PayloadServer") as server_cls,
        ):
            serve_start(shell, args)
        return server_cls

    def test_declining_never_constructs_the_server(self):
        shell = _shell(answer=False)

        server_cls = self._start(shell, ["--host", "0.0.0.0"])

        server_cls.assert_not_called()

    def test_declining_ngrok_never_constructs_the_server(self):
        shell = _shell(answer=False)

        server_cls = self._start(shell, ["--ngrok"])

        server_cls.assert_not_called()

    def test_the_default_start_is_not_gated(self):
        """Loopback is the safe default and must stay frictionless."""
        shell = _shell()

        server_cls = self._start(shell, [])

        shell.confirm.assert_not_called()
        server_cls.assert_called_once()
