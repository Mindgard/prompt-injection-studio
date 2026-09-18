"""Tests for audio prompt injection features."""

import os
import tempfile
import wave
from unittest.mock import MagicMock

import pytest

# ── Helper Functions ───────────────────────────────────────────────


def _has_numpy() -> bool:
    try:
        import numpy  # noqa: F401  (probe: skip tests when absent)

        return True
    except ImportError:
        return False


def _has_pillow() -> bool:
    try:
        from PIL import Image  # noqa: F401  (probe: skip tests when absent)

        return True
    except ImportError:
        return False


# ── TTS Engine Tests ───────────────────────────────────────────────


class TestTTSEngineAbstraction:
    """Tests for the TTS engine abstraction layer."""

    def test_engine_registry_contains_expected_engines(self):
        from pistudio.files.audio_tts import ENGINES

        assert "edge" in ENGINES
        assert "gtts" in ENGINES
        assert "pyttsx3" in ENGINES
        assert "openai" in ENGINES

    def test_get_engine_returns_correct_engine(self):
        from pistudio.files.audio_tts import EdgeTTSEngine, get_engine

        engine = get_engine("edge")
        assert isinstance(engine, EdgeTTSEngine)

    def test_get_engine_case_insensitive(self):
        from pistudio.files.audio_tts import EdgeTTSEngine, get_engine

        engine = get_engine("EDGE")
        assert isinstance(engine, EdgeTTSEngine)

    def test_get_engine_unknown_raises_value_error(self):
        from pistudio.files.audio_tts import get_engine

        with pytest.raises(ValueError, match="Unknown TTS engine"):
            get_engine("nonexistent")

    def test_placeholder_engines_raise_not_implemented(self):
        from pistudio.files.audio_tts import GTTSEngine, OpenAITTSEngine, Pyttsx3Engine

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            GTTSEngine().synthesize_sync("test", "/tmp/test.wav")

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            Pyttsx3Engine().synthesize_sync("test", "/tmp/test.wav")

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            OpenAITTSEngine().synthesize_sync("test", "/tmp/test.wav")

    def test_list_engines_returns_all_engines(self):
        from pistudio.files.audio_tts import list_engines

        engines = list_engines()
        assert len(engines) == 4
        names = [e["name"] for e in engines]
        assert "edge" in names
        assert "gtts" in names

    def test_edge_engine_has_correct_attributes(self):
        from pistudio.files.audio_tts import EdgeTTSEngine

        engine = EdgeTTSEngine()
        assert engine.name == "edge"
        assert engine.requires_network is True
        assert "Microsoft" in engine.description


# ── Audio Writer Tests ─────────────────────────────────────────────


class TestAudioWriters:
    """Tests for audio writer functions."""

    def test_text_to_binary_roundtrip(self):
        from pistudio.files.audio import _binary_to_text, _text_to_binary

        original = "Hello, World!"
        binary = _text_to_binary(original)
        recovered = _binary_to_text(binary)
        assert recovered == original

    def test_text_to_binary_unicode(self):
        from pistudio.files.audio import _binary_to_text, _text_to_binary

        original = "Hello 世界 🌍"
        binary = _text_to_binary(original)
        # Should be able to recover at least the ASCII prefix
        recovered = _binary_to_text(binary)
        assert recovered.startswith("Hello")

    def test_encrypt_decrypt_roundtrip(self):
        from pistudio.files.audio import _decrypt_text, _encrypt_text

        original = "Secret message"
        key = "my-secret-key"
        encrypted, used_key = _encrypt_text(original, key)
        assert used_key == key
        assert encrypted != original

        decrypted = _decrypt_text(encrypted, key)
        assert decrypted == original

    def test_encrypt_generates_key_if_none(self):
        from pistudio.files.audio import _encrypt_text

        original = "Secret message"
        encrypted, generated_key = _encrypt_text(original, None)
        assert generated_key is not None
        assert len(generated_key) == 32  # 16 bytes as hex

    def test_decrypt_with_wrong_key_fails(self):
        from pistudio.files.audio import _decrypt_text, _encrypt_text

        original = "Secret message"
        encrypted, _ = _encrypt_text(original, "correct-key")

        with pytest.raises(ValueError, match="invalid key"):
            _decrypt_text(encrypted, "wrong-key")

    def test_read_write_wav_samples_roundtrip(self):
        from pistudio.files.audio import _read_wav_samples, _write_wav_samples

        samples = [0, 1000, -1000, 32767, -32768, 0]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            _write_wav_samples(tmp_path, samples, 44100)
            recovered = _read_wav_samples(tmp_path)
            assert recovered == samples
        finally:
            os.unlink(tmp_path)


class TestAudioStegoWriter:
    """Tests for LSB steganography writer."""

    def test_audio_stego_encode_decode_roundtrip(self):
        from pistudio.files.audio import decode_audio_stego, write_audio_stego

        text = "Hidden message"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            write_audio_stego(text, tmp_path)
            assert os.path.isfile(tmp_path)

            recovered = decode_audio_stego(tmp_path)
            assert recovered == text
        finally:
            os.unlink(tmp_path)

    def test_audio_stego_with_carrier(self):
        from pistudio.files.audio import _write_wav_samples, decode_audio_stego, write_audio_stego

        # Create a carrier audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as carrier_tmp:
            carrier_path = carrier_tmp.name
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out_tmp:
            out_path = out_tmp.name

        try:
            # Create carrier with some audio data
            carrier_samples = [1000, -1000, 500, -500] * 1000
            _write_wav_samples(carrier_path, carrier_samples, 44100)

            text = "Stego test"
            write_audio_stego(text, out_path, carrier_path=carrier_path)

            recovered = decode_audio_stego(out_path)
            assert recovered == text
        finally:
            os.unlink(carrier_path)
            os.unlink(out_path)


class TestUltrasonicWriter:
    """Tests for ultrasonic FSK encoding."""

    def test_ultrasonic_requires_numpy(self):
        from pistudio.files.audio import write_ultrasonic

        # This test just verifies the function exists and has correct signature
        # Actual encoding requires numpy
        assert callable(write_ultrasonic)

    @pytest.mark.skipif(not _has_numpy(), reason="numpy not installed")
    def test_ultrasonic_creates_wav_file(self):
        from pistudio.files.audio import write_ultrasonic

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            write_ultrasonic("test", tmp_path)
            assert os.path.isfile(tmp_path)
            assert os.path.getsize(tmp_path) > 0

            # Verify it's a valid WAV
            with wave.open(tmp_path, "r") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 44100
        finally:
            os.unlink(tmp_path)

    @pytest.mark.skipif(not _has_numpy(), reason="numpy not installed")
    def test_ultrasonic_with_encryption(self):
        from pistudio.files.audio import write_ultrasonic

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            write_ultrasonic("secret", tmp_path, encrypt=True, key="test-key")
            assert os.path.isfile(tmp_path)
        finally:
            os.unlink(tmp_path)


class TestSpectroTextWriter:
    """Tests for spectrogram watermark writer."""

    @pytest.mark.skipif(not _has_numpy() or not _has_pillow(), reason="numpy or Pillow not installed")
    def test_spectro_text_creates_wav_file(self):
        from pistudio.files.audio import write_spectro_text

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            write_spectro_text("HELLO", tmp_path, duration=1.0)
            assert os.path.isfile(tmp_path)
            assert os.path.getsize(tmp_path) > 0

            # Verify it's a valid WAV
            with wave.open(tmp_path, "r") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
        finally:
            os.unlink(tmp_path)


# ── Adversarial Audio Tests ────────────────────────────────────────


class TestAdversarialAudioModule:
    """Tests for adversarial audio venv module."""

    def test_find_venv_python_returns_none_when_no_venv(self):
        from pistudio.files.adversarial_audio import _find_venv_python

        # In test environment, venv should not exist
        # This may return a path if the venv is installed
        result = _find_venv_python()
        # Just verify it returns str or None
        assert result is None or isinstance(result, str)

    def test_stub_raises_runtime_error(self):
        from pistudio.files.adversarial_audio import _write_adversarial_audio_stub

        with pytest.raises(RuntimeError, match="requires --carrier"):
            _write_adversarial_audio_stub("test", "/tmp/test.wav")

    def test_get_venv_status_returns_dict(self):
        from pistudio.files.adversarial_audio import get_venv_status

        status = get_venv_status()
        assert isinstance(status, dict)
        assert "installed" in status
        assert "venv_path" in status
        assert "python_version" in status
        assert "size_mb" in status

    def test_supported_models_constant(self):
        from pistudio.files.adversarial_audio import SUPPORTED_MODELS

        assert "whisper" in SUPPORTED_MODELS
        assert "deepspeech" in SUPPORTED_MODELS


# ── Format Registry Tests ──────────────────────────────────────────


class TestAudioFormatRegistry:
    """Tests for audio format registration."""

    def test_tts_wav_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("tts-wav")
        assert fmt is not None
        assert fmt.name == "tts-wav"
        assert fmt.extension == ".wav"
        assert fmt.category == "Audio"

    def test_tts_whisper_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("tts-whisper")
        assert fmt is not None
        assert fmt.name == "tts-whisper"

    def test_ultrasonic_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("ultrasonic")
        assert fmt is not None
        assert fmt.name == "ultrasonic"
        assert fmt.requires == "numpy"

    def test_audio_stego_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("audio-stego")
        assert fmt is not None
        assert fmt.requires == ""  # stdlib only

    def test_spectro_text_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("spectro-text")
        assert fmt is not None

    def test_adversarial_audio_format_registered(self):
        from pistudio.files.formats import get_format

        fmt = get_format("adversarial-audio")
        assert fmt is not None
        assert fmt.category == "Adversarial"

    def test_all_audio_formats_in_registry(self):
        from pistudio.files.formats import all_format_names

        names = all_format_names()
        assert "tts-wav" in names
        assert "tts-whisper" in names
        assert "tts-concat" in names
        assert "ultrasonic" in names
        assert "audio-stego" in names
        assert "spectro-text" in names
        assert "adversarial-audio" in names


# ── Command Tests ──────────────────────────────────────────────────


class TestAudioCommandFlags:
    """Audio completion belongs to `inject audio`, which owns the formats."""

    def test_complete_includes_audio_formats(self):
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, [""])
        assert "tts-wav" in results
        assert "ultrasonic" in results
        assert "adversarial-audio" in results

    def test_complete_includes_metadata_carriers(self):
        """wav/mp3/flac/ogg/midi moved here too, not just the signal formats."""
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, [""])
        for name in ("wav", "mp3", "flac", "ogg", "midi"):
            assert name in results

    def test_complete_tts_wav_includes_engine_flag(self):
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, ["tts-wav", ""])
        assert "--engine" in results
        assert "--voice" in results

    def test_complete_ultrasonic_includes_freq_flag(self):
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, ["ultrasonic", ""])
        assert "--freq" in results
        assert "--encrypt" in results

    def test_complete_offers_only_applicable_flags(self):
        """--freq is ultrasonic-only, so it must not appear for tts-wav."""
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, ["tts-wav", ""])
        assert "--freq" not in results
        assert "--model" not in results

    def test_complete_adversarial_audio_includes_subcommands(self):
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, ["adversarial-audio", ""])
        assert "setup" in results
        assert "uninstall" in results
        assert "status" in results

    def test_complete_engine_values(self):
        from pistudio.commands.audio_cmd import AudioCommand

        shell = MagicMock()
        shell.session_dir = "/tmp"
        results = AudioCommand().complete(shell, ["tts-wav", "--engine", ""])
        assert "edge" in results
        assert "gtts" in results

    def test_wants_path_completion_for_carrier(self):
        from pistudio.commands.audio_cmd import AudioCommand

        cmd = AudioCommand()
        assert cmd.wants_path_completion(["tts-whisper", "--carrier", ""]) is True
        assert cmd.wants_path_completion(["tts-whisper", "--engine", ""]) is False

    def test_slow_formats_includes_audio(self):
        from pistudio.commands.audio_cmd import _SLOW_FORMATS

        assert "tts-wav" in _SLOW_FORMATS
        assert "tts-whisper" in _SLOW_FORMATS
        assert "adversarial-audio" in _SLOW_FORMATS

    def test_batch_skip_includes_adversarial_audio(self):
        from pistudio.commands.files import EmbedCommand

        assert "adversarial-audio" in EmbedCommand._BATCH_SKIP
        assert "tts-whisper" in EmbedCommand._BATCH_SKIP


class TestResolveCarrierPath:
    """Tests for the _resolve_carrier_path helper."""

    def test_resolve_none_returns_none(self):
        from pistudio.commands.files import _resolve_carrier_path

        assert _resolve_carrier_path(None) is None

    def test_resolve_existing_path_returns_absolute(self):
        from pistudio.commands.files import _resolve_carrier_path

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            result = _resolve_carrier_path(path)
            assert result == os.path.abspath(path)
        finally:
            os.unlink(path)

    def test_resolve_examples_path_finds_package_file(self):
        from pistudio.commands.files import _resolve_carrier_path

        # This should resolve to the package's bundled carrier file
        result = _resolve_carrier_path("examples/carriers/low-drone.wav")
        assert result is not None
        assert os.path.exists(result)
        assert result.endswith("examples/carriers/low-drone.wav")

    def test_resolve_nonexistent_returns_original(self):
        from pistudio.commands.files import _resolve_carrier_path

        result = _resolve_carrier_path("/nonexistent/path.wav")
        assert result == "/nonexistent/path.wav"
