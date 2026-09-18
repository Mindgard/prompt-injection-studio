"""TTS engine abstraction for audio prompt injection.

Provides a pluggable architecture for text-to-speech synthesis with
edge-tts as the default implementation and placeholder stubs for
future engines (gTTS, pyttsx3, OpenAI TTS).
"""

import asyncio
import contextlib
import logging
import os
import tempfile
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ── Base class ─────────────────────────────────────────────────────


class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    name: str = "base"
    description: str = "Abstract TTS engine"
    requires_network: bool = True

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        """Synthesize text to an audio file.

        Parameters
        ----------
        text:
            The text to synthesize.
        path:
            Output path for the audio file (WAV format).
        voice:
            Voice name/identifier (engine-specific).
        rate:
            Speech rate adjustment (e.g. "+10%", "-20%").
        volume:
            Volume adjustment (e.g. "+50%", "-25%").
        """
        ...

    def synthesize_sync(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        """Synchronous wrapper for synthesize()."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an async context — create a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.synthesize(text, path, voice=voice, rate=rate, volume=volume),
                )
                future.result()
        else:
            asyncio.run(self.synthesize(text, path, voice=voice, rate=rate, volume=volume))


# ── Edge TTS (default, fully implemented) ──────────────────────────


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS engine using edge-tts library.

    Free, high-quality neural TTS with many voices. Requires network.
    No API key needed.
    """

    name = "edge"
    description = "Microsoft Edge TTS (free, high-quality, no API key)"
    requires_network = True

    # Default voice — natural-sounding US English
    DEFAULT_VOICE = "en-US-AriaNeural"

    async def synthesize(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        """Synthesize text using edge-tts."""
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError(
                "edge-tts is required for TTS audio generation. "
                "Install with: pip install prompt-injection-studio[embed-audio-tts]"
            ) from exc

        voice = voice or self.DEFAULT_VOICE

        # Build kwargs — edge-tts doesn't accept None for rate/volume
        kwargs: dict = {"voice": voice}
        if rate is not None:
            kwargs["rate"] = rate
        if volume is not None:
            kwargs["volume"] = volume

        communicate = edge_tts.Communicate(text, **kwargs)

        # edge-tts outputs MP3 by default; we need to convert to WAV
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_mp3 = tmp.name

        try:
            await communicate.save(tmp_mp3)

            # Convert MP3 to WAV using pydub if available, else keep as MP3
            # and rename (most audio tools handle this)
            if path.lower().endswith(".wav"):
                try:
                    from pydub import AudioSegment

                    audio = AudioSegment.from_mp3(tmp_mp3)
                    audio.export(path, format="wav")
                except ImportError:
                    # pydub not available — use raw conversion via wave module
                    # This is a fallback; edge-tts MP3 is valid audio
                    import shutil

                    # Just copy the MP3 with .wav extension — many tools accept this
                    # For proper conversion, user should install pydub
                    shutil.copy(tmp_mp3, path)
                    logger.warning(
                        "pydub not installed; output is MP3 data in .wav file. Install pydub for proper WAV conversion."
                    )
            else:
                import shutil

                shutil.copy(tmp_mp3, path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_mp3)

    @staticmethod
    async def list_voices(locale: str | None = None) -> list[dict]:
        """List available voices, optionally filtered by locale."""
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError(
                "edge-tts is required. Install with: pip install prompt-injection-studio[embed-audio-tts]"
            ) from exc

        voices = await edge_tts.list_voices()
        if locale:
            locale_lower = locale.lower()
            voices = [v for v in voices if locale_lower in v.get("Locale", "").lower()]
        return voices


# ── Placeholder engines (for future expansion) ─────────────────────


class GTTSEngine(TTSEngine):
    """Google Text-to-Speech engine (placeholder).

    Uses gTTS library for Google Translate TTS. Free, requires network.
    """

    name = "gtts"
    description = "Google TTS via gTTS (placeholder — not yet implemented)"
    requires_network = True

    async def synthesize(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "gTTS engine is not yet implemented. "
            "Use --engine edge (default) for now. "
            "gTTS support is planned for a future release."
        )


class Pyttsx3Engine(TTSEngine):
    """pyttsx3 offline TTS engine (placeholder).

    Uses system TTS (SAPI5 on Windows, NSSpeechSynthesizer on macOS,
    espeak on Linux). Fully offline, no network required.
    """

    name = "pyttsx3"
    description = "Offline system TTS via pyttsx3 (placeholder — not yet implemented)"
    requires_network = False

    async def synthesize(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "pyttsx3 engine is not yet implemented. "
            "Use --engine edge (default) for now. "
            "Offline TTS support is planned for a future release."
        )


class OpenAITTSEngine(TTSEngine):
    """OpenAI TTS engine (placeholder).

    Uses OpenAI's TTS API for high-quality neural voices.
    Requires API key and network.
    """

    name = "openai"
    description = "OpenAI TTS API (placeholder — not yet implemented)"
    requires_network = True

    async def synthesize(
        self,
        text: str,
        path: str,
        *,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
    ) -> None:
        raise NotImplementedError(
            "OpenAI TTS engine is not yet implemented. "
            "Use --engine edge (default) for now. "
            "OpenAI TTS support is planned for a future release."
        )


# ── Engine registry ────────────────────────────────────────────────


ENGINES: dict[str, TTSEngine] = {
    "edge": EdgeTTSEngine(),
    "gtts": GTTSEngine(),
    "pyttsx3": Pyttsx3Engine(),
    "openai": OpenAITTSEngine(),
}

DEFAULT_ENGINE = "edge"


def get_engine(name: str) -> TTSEngine:
    """Get a TTS engine by name.

    Parameters
    ----------
    name:
        Engine name (edge, gtts, pyttsx3, openai).

    Returns
    -------
    TTSEngine instance.

    Raises
    ------
    ValueError:
        If the engine name is not recognized.
    """
    engine = ENGINES.get(name.lower())
    if engine is None:
        available = ", ".join(ENGINES.keys())
        raise ValueError(f"Unknown TTS engine '{name}'. Available: {available}")
    return engine


def list_engines() -> list[dict]:
    """List all available TTS engines with their status."""
    result = []
    for name, engine in ENGINES.items():
        # Check if the engine is actually usable (not a placeholder)
        is_placeholder = False
        with contextlib.suppress(AttributeError, TypeError):
            # Placeholder engines say so in their description.
            is_placeholder = "placeholder" in (engine.description or "").lower()

        result.append(
            {
                "name": name,
                "description": engine.description,
                "requires_network": engine.requires_network,
                "available": not is_placeholder,
            }
        )
    return result
