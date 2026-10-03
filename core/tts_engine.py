"""
CHOTU AI TTS Engine
===================
Async text-to-speech engine using edge-tts (Microsoft Neural TTS) with a
pyttsx3 fallback.  Audio is played via pygame.  A background worker thread
drains a Queue so that multiple speak() calls never overlap.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import tempfile
import threading
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Optional third-party imports
# ---------------------------------------------------------------------------
try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "edge-tts not installed – will fall back to pyttsx3."
    )

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "pygame not installed – audio playback may not work."
    )

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except ImportError:
    _PYTTSX3_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_VOICE = "en-IN-PrabhatNeural"   # Male Indian English voice
DEFAULT_VOLUME = 1.0                     # 0.0 – 1.0
DEFAULT_RATE = 1.0                       # Relative to edge-tts default (+0%)


class TTSEngine:
    """
    Queue-based, async-capable Text-to-Speech engine.

    Usage
    -----
    >>> engine = TTSEngine()
    >>> asyncio.run(engine.speak("Hello, I am CHOTU."))
    """

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        volume: float = DEFAULT_VOLUME,
        rate: float = DEFAULT_RATE,
    ) -> None:
        self.voice: str = voice
        self._volume: float = max(0.0, min(1.0, volume))
        self._rate: float = rate            # multiplier; 1.0 = normal speed
        self._stopped: bool = False

        # Queue that the background player thread drains
        self._speech_queue: queue.Queue[Optional[str]] = queue.Queue()
        self._current_temp_file: Optional[str] = None

        # Initialise pygame mixer once
        if _PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                pygame.mixer.music.set_volume(self._volume)
                logger.debug("pygame mixer initialised.")
            except Exception as exc:  # pragma: no cover
                logger.error("pygame mixer init failed: %s", exc)

        # Initialise pyttsx3 fallback engine (lazy)
        self._pyttsx3_engine: Optional[object] = None

        # Start the background playback thread
        self._player_thread = threading.Thread(
            target=self._player_loop,
            daemon=True,
            name="TTSPlayerThread",
        )
        self._player_thread.start()
        logger.info("TTSEngine initialised with voice '%s'.", self.voice)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def speak(self, text: str) -> None:
        """
        Convert *text* to speech asynchronously and enqueue for playback.

        The actual synthesis may run on an executor so the calling event-loop
        is not blocked.
        """
        if self._stopped:
            logger.warning("speak() called after stop() – ignoring.")
            return
        if not text or not text.strip():
            return

        logger.debug("Enqueueing TTS: %r", text[:80])
        loop = asyncio.get_event_loop()
        tmp_path = await loop.run_in_executor(None, self._synthesise_sync, text)
        if tmp_path:
            self._speech_queue.put(tmp_path)

    def save_audio(self, text: str, filename: str) -> bool:
        """
        Synthesise *text* and save the resulting audio to *filename*.

        Returns True on success, False on failure.
        """
        try:
            asyncio.run(self._save_with_edge_tts(text, filename))
            logger.info("Audio saved to '%s'.", filename)
            return True
        except Exception as exc:
            logger.error("save_audio failed: %s", exc)
            return False

    def stop(self) -> None:
        """Stop all ongoing and queued speech immediately."""
        self._stopped = True
        # Drain the queue
        while not self._speech_queue.empty():
            try:
                path = self._speech_queue.get_nowait()
                self._cleanup_temp(path)
            except queue.Empty:
                break

        if _PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

        # Signal the player thread to exit
        self._speech_queue.put(None)
        logger.info("TTSEngine stopped.")

    def set_volume(self, volume: float) -> None:
        """
        Set playback volume.

        Parameters
        ----------
        volume:
            Float in [0.0, 1.0].  Values are clamped.
        """
        self._volume = max(0.0, min(1.0, volume))
        if _PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.set_volume(self._volume)
            except Exception as exc:
                logger.warning("Could not set pygame volume: %s", exc)
        logger.debug("Volume set to %.2f.", self._volume)

    def set_rate(self, rate: float = DEFAULT_RATE) -> None:
        """
        Set speech rate multiplier.

        Parameters
        ----------
        rate:
            1.0 = normal speed; > 1.0 faster; < 1.0 slower.
        """
        if rate <= 0:
            raise ValueError("rate must be a positive number.")
        self._rate = rate
        logger.debug("Rate set to %.2f.", self._rate)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_to_edge_percent(self) -> str:
        """Convert self._rate multiplier to an edge-tts rate string like '+20%'."""
        percent = int((self._rate - 1.0) * 100)
        if percent >= 0:
            return f"+{percent}%"
        return f"{percent}%"

    def _synthesise_sync(self, text: str) -> Optional[str]:
        """
        Blocking synthesis.  Tries edge-tts first, then pyttsx3.
        Returns path to a temp .mp3 file, or None on total failure.
        """
        if _EDGE_TTS_AVAILABLE:
            try:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False, prefix="chotu_tts_"
                )
                tmp.close()
                asyncio.run(self._save_with_edge_tts(text, tmp.name))
                return tmp.name
            except Exception as exc:
                logger.warning("edge-tts synthesis failed (%s), trying pyttsx3.", exc)

        # pyttsx3 fallback
        if _PYTTSX3_AVAILABLE:
            return self._synthesise_pyttsx3(text)

        logger.error("No TTS backend available – cannot speak.")
        return None

    async def _save_with_edge_tts(self, text: str, filename: str) -> None:
        """Use edge-tts to save synthesised speech to *filename*."""
        rate_str = self._rate_to_edge_percent()
        communicate = edge_tts.Communicate(text, self.voice, rate=rate_str)
        await communicate.save(filename)

    def _synthesise_pyttsx3(self, text: str) -> Optional[str]:
        """Use pyttsx3 to synthesise speech and save to a temp WAV file."""
        try:
            if self._pyttsx3_engine is None:
                self._pyttsx3_engine = pyttsx3.init()
            engine = self._pyttsx3_engine
            # Adjust rate (~200 wpm default; scale by self._rate)
            base_rate = engine.getProperty("rate")
            engine.setProperty("rate", int(base_rate * self._rate))
            engine.setProperty("volume", self._volume)

            tmp = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="chotu_tts_"
            )
            tmp.close()
            engine.save_to_file(text, tmp.name)
            engine.runAndWait()
            return tmp.name
        except Exception as exc:
            logger.error("pyttsx3 synthesis failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Background player thread
    # ------------------------------------------------------------------

    def _player_loop(self) -> None:
        """Continuously dequeue and play audio files."""
        while True:
            path = self._speech_queue.get()
            if path is None:        # Sentinel – exit signal
                break
            self._play_file(path)
            self._cleanup_temp(path)

    def _play_file(self, path: str) -> None:
        """Play an audio file via pygame, blocking until finished."""
        if not os.path.exists(path):
            logger.warning("Audio file not found: %s", path)
            return

        if _PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.play()
                # Block until playback finishes or stop() is called
                while pygame.mixer.music.get_busy():
                    if self._stopped:
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.05)
                return
            except Exception as exc:
                logger.warning("pygame playback failed (%s); trying OS fallback.", exc)

        # Last-resort: pyttsx3 speak directly
        if _PYTTSX3_AVAILABLE:
            try:
                if self._pyttsx3_engine is None:
                    self._pyttsx3_engine = pyttsx3.init()
                # pyttsx3 cannot play files easily; re-use already saved audio
                # We play using subprocess as last resort on Windows
                os.startfile(path)  # type: ignore[attr-defined]
                time.sleep(2)       # rough wait
            except Exception as exc:
                logger.error("Fallback playback failed: %s", exc)

    @staticmethod
    def _cleanup_temp(path: Optional[str]) -> None:
        """Delete a temporary audio file, ignoring errors."""
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Convenience entry-point for quick tests
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    async def _demo() -> None:
        engine = TTSEngine()
        await engine.speak("Hello! I am CHOTU, your personal AI assistant.")
        await asyncio.sleep(5)
        engine.stop()

    asyncio.run(_demo())
