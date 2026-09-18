"""Tests for Bunny file upload feature — registry, compiler, device, and command."""

import hashlib
import os
from io import StringIO
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from pistudio.hardware.hak5 import bunny_files

# ── bunny_files.py — File registry CRUD ─────────────────────────


class TestBunnyFileRegistry:
    """Unit tests for hak5/bunny_files.py."""

    def test_add_file(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, get_file

        f = tmp_path / "payload.pdf"
        f.write_bytes(b"fake pdf content")

        session_dir = str(tmp_path / "session")
        bf, warning = add_file("my-pdf", str(f), session_dir)

        assert bf.name == "my-pdf"
        assert bf.filename == "payload.pdf"
        assert bf.size_bytes == len(b"fake pdf content")
        assert bf.sha256 == hashlib.sha256(b"fake pdf content").hexdigest()
        assert warning is False

        result = get_file("my-pdf", session_dir)
        assert result is not None
        assert result[0].name == "my-pdf"
        assert result[1] == "session"

    def test_add_file_duplicate_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        f = tmp_path / "test.txt"
        f.write_text("hello")
        session_dir = str(tmp_path / "session")

        add_file("dup-test", str(f), session_dir)
        with pytest.raises(ValueError, match="already registered"):
            add_file("dup-test", str(f), session_dir)

    def test_add_file_not_found_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        session_dir = str(tmp_path / "session")
        with pytest.raises(FileNotFoundError):
            add_file("ghost", str(tmp_path / "nonexistent.pdf"), session_dir)

    def test_add_file_invalid_name_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        f = tmp_path / "test.txt"
        f.write_text("hello")
        session_dir = str(tmp_path / "session")

        with pytest.raises(ValueError, match="Invalid file name"):
            add_file("bad name!", str(f), session_dir)

    def test_add_file_path_traversal_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        f = tmp_path / "test.txt"
        f.write_text("hello")
        session_dir = str(tmp_path / "session")

        with pytest.raises(ValueError, match="Invalid file name"):
            add_file("../evil", str(f), session_dir)

    def test_list_files_empty(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import list_files

        assert list_files(str(tmp_path / "session")) == []

    def test_list_files(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, list_files

        f = tmp_path / "a.txt"
        f.write_text("aaa")
        session_dir = str(tmp_path / "session")

        add_file("file-a", str(f), session_dir)
        files = list_files(session_dir)
        assert len(files) == 1
        assert files[0][0].name == "file-a"
        assert files[0][1] == "session"

    def test_remove_file(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, file_names, remove_file

        f = tmp_path / "rm.txt"
        f.write_text("remove me")
        session_dir = str(tmp_path / "session")

        add_file("to-remove", str(f), session_dir)
        assert "to-remove" in file_names(session_dir)

        remove_file("to-remove", session_dir)
        assert "to-remove" not in file_names(session_dir)

    def test_remove_file_not_found_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import remove_file

        with pytest.raises(ValueError, match="not found"):
            remove_file("nonexistent", str(tmp_path / "session"))

    def test_file_names(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, file_names

        session_dir = str(tmp_path / "session")
        for name in ("charlie", "alpha", "bravo"):
            f = tmp_path / f"{name}.txt"
            f.write_text(name)
            add_file(name, str(f), session_dir)

        names = file_names(session_dir)
        assert names == ["alpha", "bravo", "charlie"]

    def test_size_warning(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * 100)
        session_dir = str(tmp_path / "session")

        import pistudio.hardware.hak5.bunny_files as bf_mod

        original = bf_mod._SIZE_WARNING_BYTES
        try:
            bf_mod._SIZE_WARNING_BYTES = 50
            _, warning = add_file("big-file", str(f), session_dir)
            assert warning is True
        finally:
            bf_mod._SIZE_WARNING_BYTES = original

    def test_get_files_by_names(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, get_files_by_names

        session_dir = str(tmp_path / "session")
        for name in ("one", "two"):
            f = tmp_path / f"{name}.txt"
            f.write_text(name)
            add_file(name, str(f), session_dir)

        files = get_files_by_names(["one", "two"], session_dir)
        assert len(files) == 2
        assert {f.name for f in files} == {"one", "two"}

    def test_get_files_by_names_missing_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import get_files_by_names

        with pytest.raises(ValueError, match="not found"):
            get_files_by_names(["missing"], str(tmp_path / "session"))

    def test_global_scope(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, list_files

        f = tmp_path / "global.txt"
        f.write_text("global file")
        session_dir = str(tmp_path / "session")

        add_file("global-file", str(f), session_dir, global_scope=True)
        files = list_files(session_dir)
        assert len(files) == 1
        assert files[0][1] == "global"

    def test_session_shadows_global(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file, list_files

        f = tmp_path / "shadow.txt"
        f.write_text("shadow")
        session_dir = str(tmp_path / "session")

        add_file("shadow", str(f), session_dir, global_scope=True)
        add_file("shadow", str(f), session_dir, global_scope=False)

        files = list_files(session_dir)
        assert len(files) == 1
        assert files[0][1] == "session"

    def test_duplicate_filename_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import add_file

        # Create two files with the same basename in different dirs
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        (dir_a / "payload.pdf").write_bytes(b"aaa")
        (dir_b / "payload.pdf").write_bytes(b"bbb")

        session_dir = str(tmp_path / "session")
        add_file("first-pdf", str(dir_a / "payload.pdf"), session_dir)

        with pytest.raises(ValueError, match="already uses the basename"):
            add_file("second-pdf", str(dir_b / "payload.pdf"), session_dir)

    def test_corrupt_registry_is_reported_not_silently_empty(self, tmp_path, caplog):
        """An empty result must not be indistinguishable from a lost registry.

        The next 'add' would overwrite whatever was there, so the operator
        needs to know the file could not be read.
        """
        from pistudio.hardware.hak5.bunny_files import _load_files

        path = tmp_path / "files.json"
        path.write_text("{ not valid json")

        assert _load_files(str(path)) == []
        assert "unreadable file registry" in caplog.text

    def test_registry_that_is_not_a_list_is_reported(self, tmp_path, caplog):
        from pistudio.hardware.hak5.bunny_files import _load_files

        path = tmp_path / "files.json"
        path.write_text('{"name": "x"}')

        assert _load_files(str(path)) == []
        assert "malformed file registry" in caplog.text

    def test_invalid_entry_is_skipped_and_others_kept(self, tmp_path, caplog):
        from pistudio.hardware.hak5.bunny_files import _load_files

        path = tmp_path / "files.json"
        path.write_text('[{"nope": 1}, {"name": "ok", "local_path": "/tmp/a", "filename": "a"}]')

        files = _load_files(str(path))
        assert [f.name for f in files] == ["ok"]
        assert "Skipping invalid entry" in caplog.text

    def test_human_size(self):
        from pistudio.hardware.hak5.bunny_files import _human_size

        assert _human_size(0) == "0 B"
        assert _human_size(512) == "512 B"
        assert _human_size(1024) == "1.0 KB"
        assert _human_size(1048576) == "1.0 MB"
        assert _human_size(1073741824) == "1.0 GB"


# ── compiler_bunny.py — File reference expansion ────────────────


class TestCompilerFileRefs:
    """Tests for {{file:name}} expansion in compiler_bunny.py."""

    def test_extract_file_references(self):
        from pistudio.hardware.hak5.compiler_bunny import extract_file_references

        text = "Open {{file:my-pdf}} and also {{file:evil.docx}} please"
        refs = extract_file_references(text)
        assert refs == ["my-pdf", "evil.docx"]

    def test_extract_no_references(self):
        from pistudio.hardware.hak5.compiler_bunny import extract_file_references

        assert extract_file_references("no file refs here") == []

    def test_detect_os_returns_valid_target(self):
        from pistudio.hardware.hak5.compiler_bunny import detect_os

        result = detect_os()
        assert result in ("windows", "linux", "mac")

    def test_detect_os_darwin(self, monkeypatch):
        from pistudio.hardware.hak5 import compiler_bunny as compiler

        monkeypatch.setattr(compiler.sys, "platform", "darwin")
        assert compiler.detect_os() == "mac"

    def test_detect_os_win32(self, monkeypatch):
        from pistudio.hardware.hak5 import compiler_bunny as compiler

        monkeypatch.setattr(compiler.sys, "platform", "win32")
        assert compiler.detect_os() == "windows"

    def test_detect_os_linux(self, monkeypatch):
        from pistudio.hardware.hak5 import compiler_bunny as compiler

        monkeypatch.setattr(compiler.sys, "platform", "linux")
        assert compiler.detect_os() == "linux"

    def test_compile_payload_with_files_windows(self):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(
            name="test-payload",
            text="Open the file at {{file:my-pdf}} now",
            description="Test",
        )
        files = [
            BunnyFile(
                name="my-pdf",
                local_path="/tmp/test.pdf",
                filename="test.pdf",
                size_bytes=100,
                sha256="abc123",
            )
        ]

        script = compile_payload_with_files(payload, files, os_target="windows")
        assert "ATTACKMODE HID STORAGE" in script
        assert "ATTACKMODE HID\n" not in script
        assert "test.pdf" in script
        assert "powershell" in script.lower()
        # The drive letter is held in a PowerShell variable in the session the
        # preamble opens. A process-scoped environment variable would be empty
        # by the time paths are typed, because the process that set it exited.
        assert "$BunnyDrive" in script
        assert "$env:BUNNY_DRIVE" not in script

    def test_windows_preamble_types_paths_into_the_session_that_defines_the_drive(self):
        """The variable must be set and used in one interactive session."""
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="p", text="Open {{file:doc}}")
        files = [BunnyFile(name="doc", local_path="/tmp/d.pdf", filename="d.pdf")]

        script = compile_payload_with_files(payload, files, os_target="windows")
        lines = script.splitlines()
        assign_idx = next(i for i, line in enumerate(lines) if "$BunnyDrive=" in line)
        use_idx = next(i for i, line in enumerate(lines) if "d.pdf" in line and "Q STRING" in line)
        assert assign_idx < use_idx
        # No SetEnvironmentVariable: that value dies with the PowerShell process.
        assert "SetEnvironmentVariable" not in script

    def test_compile_payload_with_files_linux(self):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(
            name="test-payload",
            text="Open {{file:doc}}",
        )
        files = [
            BunnyFile(
                name="doc",
                local_path="/tmp/doc.txt",
                filename="doc.txt",
                size_bytes=50,
                sha256="def456",
            )
        ]

        script = compile_payload_with_files(payload, files, os_target="linux")
        assert "ATTACKMODE HID STORAGE" in script
        assert "/media/usb0/payloads/switch1/files/doc.txt" in script
        assert "powershell" not in script.lower()

    def test_compile_payload_with_files_mac(self):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="test", text="{{file:img}}")
        files = [
            BunnyFile(
                name="img",
                local_path="/tmp/img.png",
                filename="img.png",
                size_bytes=200,
                sha256="ghi789",
            )
        ]

        script = compile_payload_with_files(payload, files, os_target="mac")
        assert "/Volumes/BashBunny/payloads/switch1/files/img.png" in script

    def test_compile_payload_with_files_invalid_os_raises(self):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="test", text="{{file:x}}")
        files = [BunnyFile(name="x", local_path="/tmp/x", filename="x", size_bytes=1, sha256="a")]

        with pytest.raises(ValueError, match="--os is required"):
            compile_payload_with_files(payload, files, os_target="bsd")

    def test_compile_with_switch2(self):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="test", text="{{file:x}}")
        files = [BunnyFile(name="x", local_path="/tmp/x.bin", filename="x.bin", size_bytes=1, sha256="a")]

        script = compile_payload_with_files(payload, files, os_target="linux", switch=2)
        assert "switch2" in script

    def test_unresolved_ref_left_as_is(self):
        from pistudio.hardware.hak5.compiler_bunny import compile_payload_with_files
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="test", text="{{file:missing}}")
        script = compile_payload_with_files(payload, [], os_target="linux")
        assert "{{file:missing}}" in script


# ── device.py — deploy_bunny_files ──────────────────────────────


class TestDeployBunnyFiles:
    """Tests for deploy_bunny_files in device.py."""

    def test_deploy_copies_files(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.device import deploy_bunny_files

        src = tmp_path / "source.pdf"
        src.write_bytes(b"pdf content")

        bf = BunnyFile(
            name="my-file",
            local_path=str(src),
            filename="source.pdf",
            size_bytes=11,
            sha256="abc",
        )

        device_path = str(tmp_path / "device")
        deployed = deploy_bunny_files([bf], path=device_path, switch=1)

        assert len(deployed) == 1
        dest = os.path.join(device_path, "payloads", "switch1", "files", "source.pdf")
        assert deployed[0] == dest
        assert os.path.isfile(dest)
        assert open(dest, "rb").read() == b"pdf content"

    def test_deploy_switch2(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.device import deploy_bunny_files

        src = tmp_path / "test.txt"
        src.write_text("hello")
        bf = BunnyFile(name="t", local_path=str(src), filename="test.txt", size_bytes=5, sha256="x")

        device_path = str(tmp_path / "device")
        deployed = deploy_bunny_files([bf], path=device_path, switch=2)
        assert "switch2" in deployed[0]

    def test_deploy_invalid_switch_raises(self, tmp_path):
        from pistudio.hardware.hak5.device import deploy_bunny_files

        with pytest.raises(ValueError, match="Switch must be 1 or 2"):
            deploy_bunny_files([], path=str(tmp_path), switch=3)

    def test_deploy_missing_source_raises(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.device import deploy_bunny_files

        bf = BunnyFile(
            name="gone",
            local_path=str(tmp_path / "nonexistent.pdf"),
            filename="nonexistent.pdf",
            size_bytes=0,
            sha256="x",
        )

        with pytest.raises(FileNotFoundError, match="no longer exists"):
            deploy_bunny_files([bf], path=str(tmp_path / "device"), switch=1)

    def test_deploy_multiple_files(self, tmp_path):
        from pistudio.hardware.hak5.bunny_files import BunnyFile
        from pistudio.hardware.hak5.device import deploy_bunny_files

        files = []
        for i in range(3):
            src = tmp_path / f"file{i}.txt"
            src.write_text(f"content {i}")
            files.append(
                BunnyFile(
                    name=f"f{i}",
                    local_path=str(src),
                    filename=f"file{i}.txt",
                    size_bytes=9,
                    sha256=f"hash{i}",
                )
            )

        device_path = str(tmp_path / "device")
        deployed = deploy_bunny_files(files, path=device_path, switch=1)
        assert len(deployed) == 3
        for dp in deployed:
            assert os.path.isfile(dp)


# ── commands/bunny.py — Command dispatch ────────────────────────


def _make_shell(tmp_path):
    """Create a MagicMock shell matching the pattern in test_hak5.py."""
    shell = MagicMock()
    buf = StringIO()
    shell.console = Console(file=buf, no_color=True, width=120)
    session = str(tmp_path / "session")
    os.makedirs(session, exist_ok=True)
    shell.session_dir = session
    shell.session_dir = session
    shell.json_mode = False
    shell.out = MagicMock()
    shell.audit = MagicMock()
    shell.print_raw = lambda x: buf.write(x)
    shell.confirm = MagicMock(return_value=True)
    return shell, buf


class TestFileDeliveryWiring:
    """The CLI must actually reach the file-delivery code path.

    The registry, the with-files compilers and deploy_bunny_files existed and
    were tested in isolation, but nothing in the command layer called them: a
    payload referencing {{file:x}} was compiled as plain ATTACKMODE HID and the
    placeholder was typed literally at the target.
    """

    def _register(self, shell, tmp_path, monkeypatch, name="doc"):
        src = tmp_path / "invoice.pdf"
        src.write_bytes(b"%PDF-1.4 test")
        bunny_files.add_file(name, str(src), shell.session_dir)

    def _payload(self, monkeypatch, tmp_path, text):
        """Make get_payload return a payload with *text*."""
        from pistudio.hardware.payloads import Payload

        payload = Payload(name="lure", text=text)
        monkeypatch.setattr(
            "pistudio.hardware.payloads.get_payload",
            lambda name, session_dir: (payload, "session"),
        )
        return payload

    def test_compile_selects_storage_attackmode_and_expands_path(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.hak5 import _compile

        shell, _ = _make_shell(tmp_path)
        self._register(shell, tmp_path, monkeypatch)
        self._payload(monkeypatch, tmp_path, "Read {{file:doc}} now")

        result = _compile(shell, "bunny", "lure", {"os": "windows"})
        assert result is not None
        script, files, _opts = result

        assert "ATTACKMODE HID STORAGE" in script
        assert "{{file:doc}}" not in script
        assert "invoice.pdf" in script
        assert [bf.name for bf in files] == ["doc"]

    def test_compile_without_file_refs_stays_hid_only(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.hak5 import _compile

        shell, _ = _make_shell(tmp_path)
        self._payload(monkeypatch, tmp_path, "No files here")

        result = _compile(shell, "bunny", "lure", {})
        assert result is not None
        script, files, _opts = result
        assert "ATTACKMODE HID STORAGE" not in script
        assert files == []

    def test_compile_reports_unresolvable_reference(self, tmp_path, monkeypatch):
        """An unregistered reference must fail loudly, not deploy a literal."""
        from pistudio.commands.hw.hak5 import _compile

        shell, _ = _make_shell(tmp_path)
        self._payload(monkeypatch, tmp_path, "Read {{file:missing}}")

        assert _compile(shell, "bunny", "lure", {}) is None
        assert shell.out.error.called
        assert "missing" in str(shell.out.error.call_args)

    def test_deploy_copies_referenced_files(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.hak5 import _CompileOptions, _deploy

        shell, _ = _make_shell(tmp_path)
        self._register(shell, tmp_path, monkeypatch)
        files = bunny_files.get_files_by_names(["doc"], shell.session_dir)

        mount = tmp_path / "bunny"
        (mount / "payloads").mkdir(parents=True)
        _deploy(shell, "bunny", "Bash Bunny", "lure", "#!/bin/bash\n", files, _CompileOptions(), {"path": str(mount)})

        assert (mount / "payloads" / "switch1" / "payload.txt").is_file()
        assert (mount / "payloads" / "switch1" / "files" / "invoice.pdf").is_file()

    def test_deploy_names_the_destination_in_the_prompt(self, tmp_path, monkeypatch):
        """With two devices attached, "the Bash Bunny" is ambiguous."""
        from pistudio.commands.hw.hak5 import _CompileOptions, _deploy

        shell, _ = _make_shell(tmp_path)
        mount = tmp_path / "bunny"
        (mount / "payloads").mkdir(parents=True)
        shell.confirm.return_value = False

        _deploy(shell, "bunny", "Bash Bunny", "lure", "x", [], _CompileOptions(), {"path": str(mount)})

        assert str(mount) in shell.confirm.call_args[0][0]


class TestCompileOptions:
    """Flags documented in docs/hak5.md were parsed and then ignored."""

    def test_threads_start_delay_and_preamble(self):
        from pistudio.commands.hw.hak5 import _compile_options

        opts = _compile_options({"start-delay": "2500", "preamble": "Q GUI r"})
        assert opts.ducky_payload["start_delay"] == 2500
        assert opts.bunny_payload["preamble"] == "Q GUI r"

    def test_rejects_unknown_os(self):
        from pistudio.commands.hw.hak5 import _compile_options

        with pytest.raises(ValueError, match="--os must be one of"):
            _compile_options({"os": "solaris"})

    def test_rejects_non_numeric_delay(self):
        from pistudio.commands.hw.hak5 import _compile_options

        with pytest.raises(ValueError, match="--start-delay must be a number"):
            _compile_options({"start-delay": "soon"})

    def test_rejects_unknown_layout(self):
        from pistudio.commands.hw.hak5 import _compile_options

        with pytest.raises(ValueError, match="--layout must be one of"):
            _compile_options({"layout": "martian"})


class TestDuckyEncodeCommand:
    """The Ducky compile/deploy path must produce the inject.bin the device runs."""

    def _payload(self, monkeypatch, text):
        from pistudio.hardware.payloads import Payload

        monkeypatch.setattr(
            "pistudio.hardware.payloads.get_payload",
            lambda name, session_dir: (Payload(name="p", text=text), "session"),
        )

    def test_compile_inject_bin_writes_the_binary(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.command import HwCommand
        from pistudio.commands.hw.hak5 import handle_hak5

        shell, _ = _make_shell(tmp_path)
        self._payload(monkeypatch, "hello")
        out = tmp_path / "inject.bin"
        handle_hak5(HwCommand(), shell, "ducky", ["compile", "p", "--inject-bin", str(out)])

        assert out.is_file()
        data = out.read_bytes()
        # Whole 2-byte pairs, starting with the compiled DELAY 1000 and ending
        # with the 'hello' keystrokes plus a trailing Enter (0x28).
        assert len(data) % 2 == 0
        assert data.startswith(b"\x00\xff")  # first DELAY chunk (255ms)
        assert data.endswith(b"\x12\x00\x28\x00")  # 'o' (0x12) then Enter (0x28)

    def test_compile_inject_bin_rejected_for_bunny(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.command import HwCommand
        from pistudio.commands.hw.hak5 import handle_hak5

        shell, _ = _make_shell(tmp_path)
        self._payload(monkeypatch, "hello")
        handle_hak5(HwCommand(), shell, "bunny", ["compile", "p", "--inject-bin", str(tmp_path / "x.bin")])

        assert shell.out.error.called
        assert "Ducky" in str(shell.out.error.call_args)

    def test_compile_inject_bin_reports_untypeable_payload(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.command import HwCommand
        from pistudio.commands.hw.hak5 import handle_hak5

        shell, _ = _make_shell(tmp_path)
        self._payload(monkeypatch, "café")
        out = tmp_path / "inject.bin"
        handle_hak5(HwCommand(), shell, "ducky", ["compile", "p", "--inject-bin", str(out)])

        assert shell.out.error.called
        assert not out.exists()

    def test_deploy_ducky_arms_with_inject_bin(self, tmp_path, monkeypatch):
        from pistudio.commands.hw.command import HwCommand
        from pistudio.commands.hw.hak5 import handle_hak5

        shell, _ = _make_shell(tmp_path)
        shell.confirm = MagicMock(return_value=True)
        self._payload(monkeypatch, "hello")
        mount = tmp_path / "DUCKY"
        mount.mkdir()

        handle_hak5(HwCommand(), shell, "ducky", ["deploy", "p", "--path", str(mount)])

        assert (mount / "inject.bin").is_file()
        assert (mount / "payload.txt").is_file()
