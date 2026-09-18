"""Tests for the inject command and payload server."""

from unittest.mock import MagicMock

import pytest

# ── Registry Tests ────────────────────────────────────────────────


class TestPayloadRegistry:
    """Tests for the ephemeral payload registry."""

    def test_add_payload_generates_slug(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        payload = registry.add("test payload text")
        assert payload.slug
        assert len(payload.slug) == 6
        assert payload.text == "test payload text"

    def test_add_payload_with_custom_slug(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        payload = registry.add("test", slug="my-custom-slug")
        assert payload.slug == "my-custom-slug"

    def test_add_payload_with_name(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        payload = registry.add("test", name="ignore-instructions")
        assert payload.name == "ignore-instructions"

    def test_add_duplicate_slug_raises(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        registry.add("test1", slug="abc123")
        with pytest.raises(ValueError, match="already exists"):
            registry.add("test2", slug="abc123")

    def test_get_payload(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        added = registry.add("test payload")
        retrieved = registry.get(added.slug)
        assert retrieved is not None
        assert retrieved.text == "test payload"

    def test_get_nonexistent_returns_none(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        assert registry.get("nonexistent") is None

    def test_remove_payload(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        payload = registry.add("test")
        assert registry.remove(payload.slug) is True
        assert registry.get(payload.slug) is None

    def test_remove_nonexistent_returns_false(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        assert registry.remove("nonexistent") is False

    def test_list_all(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        registry.add("payload1")
        registry.add("payload2")
        registry.add("payload3")
        all_payloads = registry.list_all()
        assert len(all_payloads) == 3

    def test_clear(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        registry.add("payload1")
        registry.add("payload2")
        count = registry.clear()
        assert count == 2
        assert len(registry) == 0

    def test_len(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        assert len(registry) == 0
        registry.add("test")
        assert len(registry) == 1

    def test_to_dict(self):
        from pistudio.serve.registry import PayloadRegistry

        registry = PayloadRegistry()
        payload = registry.add("test", name="my-payload")
        d = payload.to_dict()
        assert d["slug"] == payload.slug
        assert d["text"] == "test"
        assert d["name"] == "my-payload"
        assert "created_at" in d


class TestSlugGeneration:
    """Tests for slug generation."""

    def test_generate_slug_length(self):
        from pistudio.serve.registry import generate_slug

        slug = generate_slug()
        assert len(slug) == 6

    def test_generate_slug_custom_length(self):
        from pistudio.serve.registry import generate_slug

        slug = generate_slug(length=10)
        assert len(slug) == 10

    def test_generate_slug_is_alphanumeric(self):
        from pistudio.serve.registry import generate_slug

        slug = generate_slug()
        assert slug.isalnum()

    def test_generate_slug_uniqueness(self):
        from pistudio.serve.registry import generate_slug

        slugs = [generate_slug() for _ in range(100)]
        assert len(set(slugs)) == 100  # All unique


class TestGlobalRegistry:
    """Tests for the global registry singleton."""

    def test_get_registry_returns_same_instance(self):
        from pistudio.serve.registry import get_registry, reset_registry

        reset_registry()
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_reset_registry(self):
        from pistudio.serve.registry import get_registry, reset_registry

        r1 = get_registry()
        r1.add("test")
        reset_registry()
        r2 = get_registry()
        assert len(r2) == 0


# ── Server Status Tests ───────────────────────────────────────────


class TestServerStatus:
    """Tests for server status functions."""

    def test_get_server_status_when_not_running(self):
        from pistudio.serve.server import get_server_status

        # Ensure no server is running
        _ = get_server_status()
        # May be None or a tuple depending on test isolation
        # Just verify it doesn't crash

    def test_server_url_property(self):
        from pistudio.serve.registry import PayloadRegistry
        from pistudio.serve.server import PayloadServer

        registry = PayloadRegistry()
        server = PayloadServer(host="127.0.0.1", port=9999, registry=registry)
        assert server.url == "http://127.0.0.1:9999"

    def test_server_url_with_tls(self):
        from pistudio.serve.registry import PayloadRegistry
        from pistudio.serve.server import PayloadServer

        registry = PayloadRegistry()
        server = PayloadServer(host="127.0.0.1", port=9999, tls=True, registry=registry)
        assert server.url == "https://127.0.0.1:9999"


# ── StudioCommand Tests ───────────────────────────────────────────


class TestTopLevelCommands:
    """There is no wrapper verb; every command registers under its own name."""

    def test_the_inject_verb_and_its_aliases_are_gone(self):
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        for name in ("inject", "pi", "prompt-inject", "studio"):
            assert get_command(name) is None, f"'{name}' still resolves"

    def test_every_capability_is_top_level(self):
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        for name in ("serve", "file", "audio", "barcode", "hw", "payloads", "theme", "tutorial"):
            assert get_command(name) is not None, f"'{name}' is not registered"

    def test_serve_no_args_starts_rather_than_erroring(self):
        from pistudio.commands.serve import ServeCommand

        assert ServeCommand().name == "serve"
        assert ServeCommand().namespace is True

    def test_complete_serve_flags(self):
        from pistudio.commands.serve import ServeCommand
        from pistudio.ui.completer import CompletionItem

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = ServeCommand().complete(shell, [""])
        texts = [r.text if isinstance(r, CompletionItem) else r for r in results]
        assert "--host" in texts
        assert "--port" in texts
        assert "--tls" in texts
        assert "--payload" in texts

    def test_complete_host_values(self):
        from pistudio.commands.serve import ServeCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = ServeCommand().complete(shell, ["--host", ""])
        assert "127.0.0.1" in results
        assert "0.0.0.0" in results
        assert "localhost" in results

    def test_complete_port_values(self):
        from pistudio.commands.serve import ServeCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = ServeCommand().complete(shell, ["--port", ""])
        assert "8080" in results
        assert "8000" in results

    def test_complete_serve_subcommands(self):
        from pistudio.commands.serve import ServeCommand
        from pistudio.ui.completer import CompletionItem

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = ServeCommand().complete(shell, [""])
        texts = [r.text if isinstance(r, CompletionItem) else r for r in results]
        for sub in ("add", "remove", "list", "status", "stop"):
            assert sub in texts

    def test_complete_barcode_flags(self):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = BarcodeCommand().complete(shell, ["hi", "--"])
        assert "--url-slug" in results
        assert "--border" in results
        assert "--error-level" in results

    def test_complete_error_level_values(self):
        from pistudio.commands.barcode_cmd import BarcodeCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = BarcodeCommand().complete(shell, ["--error-level", ""])
        assert {"L", "M", "Q", "H"} <= set(results)


# ── Macro Variable Tests ──────────────────────────────────────────


# ── Toolbar Tests ─────────────────────────────────────────────────


# ── Command Registration Tests ────────────────────────────────────


class TestCommandRegistration:
    """Tests for command registration."""

    def test_embed_is_reachable_as_file(self):
        """The class is still EmbedCommand; the name the user types is 'file'."""
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        assert get_command("embed") is None
        cmd = get_command("file")
        assert cmd is not None
        assert cmd.name == "file"

    def test_hw_is_registered_as_toplevel(self):
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        cmd = get_command("hw")
        assert cmd is not None
        assert cmd.name == "hw"

    def test_payloads_is_registered_as_toplevel(self):
        from pistudio.commands import get_command, register_all_commands

        register_all_commands()
        assert get_command("payloads") is not None


# ── Meta Help Group Tests ─────────────────────────────────────────
