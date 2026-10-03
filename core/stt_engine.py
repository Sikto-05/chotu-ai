"""
CHOTU AI STT Engine
===================
Continuous speech-to-text engine that:
  * Listens in a background daemon thread
  * Detects the wake-word ("chotu" / "hey chotu")
  * Transcribes follow-up commands via Google Speech API (online)
  * Falls back to faster-whisper (offline) when Google is unavailable
  * Optionally uses webrtcvad for voice-activity detection
  * Fires an ``on_command`` callback with the recognised text
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

import speech_recognition as sr

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    from faster_whisper import WhisperModel
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False

try:
    import webrtcvad
    _VAD_AVAILABLE = True
except ImportError:
    _VAD_AVAILABLE = False

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WAKE_WORDS: tuple[str, ...] = ("chotu", "hey chotu", "ok chotu", "oi chotu")
LANGUAGE_CODE = "en-IN"           # Indian English
AMBIENT_CALIBRATION_DURATION = 1  # seconds
LISTEN_TIMEOUT = 5                # max seconds to wait for speech to start
PHRASE_TIME_LIMIT = 10            # max seconds for a single phrase
WHISPER_MODEL_SIZE = "base"       # tiny / base / small / medium / large


class STTEngine:
    """
    Continuous speech-to-text engine with wake-word gating.

    Parameters
    ----------
    on_command:
        Callback that receives the recognised command string.
    use_whisper_fallback:
        If True and faster-whisper is installed, use it when Google fails.
    vad_aggressiveness:
        0-3; higher = more aggressive filtering of non-speech.
    """

    def __init__(
        self,
        on_command: Optional[Callable[[str], None]] = None,
        use_whisper_fallback: bool = True,
        vad_aggressiveness: int = 2,
    ) -> None:
        self.on_command: Callable[[str], None] = on_command or (lambda t: print(f"[STT] Command: {t}"))
        self._use_whisper_fallback = use_whisper_fallback and _WHISPER_AVAILABLE
        self._vad_aggressiveness = vad_aggressiveness

        self._recogniser = sr.Recognizer()
        self._microphone: Optional[sr.Microphone] = None
        self._stop_flag = threading.Event()
        self._listen_thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue[Optional[sr.AudioData]] = queue.Queue()

        # webrtcvad
        self._vad: Optional[object] = None
        if _VAD_AVAILABLE:
            try:
                self._vad = webrtcvad.Vad(self._vad_aggressiveness)
                logger.debug("webrtcvad initialised (aggressiveness=%d).", vad_aggressiveness)
            except Exception as exc:
                logger.warning("webrtcvad init failed: %s", exc)

        # faster-whisper
        self._whisper_model: Optional[WhisperModel] = None
        if self._use_whisper_fallback:
            self._load_whisper_model()

        # State flags
        self._awake = False          # True after wake-word detected
        self._calibrated = False

        logger.info("STTEngine initialised.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_listening(self) -> None:
        """Start the background listening thread."""
        if self._listen_thread and self._listen_thread.is_alive():
            logger.warning("Already listening – ignoring start_listening().")
            return

        self._stop_flag.clear()
        self._listen_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="STTListenThread",
        )
        self._listen_thread.start()
        logger.info("STT background listening started.")

    def stop_listening(self) -> None:
        """Stop the background listening thread gracefully."""
        self._stop_flag.set()
        self._audio_queue.put(None)   # unblock queue consumer
        if self._listen_thread:
            self._listen_thread.join(timeout=3)
        logger.info("STT listening stopped.")

    def adjust_for_ambient_noise(
        self, duration: float = AMBIENT_CALIBRATION_DURATION
    ) -> None:
        """
        Calibrate the recogniser's energy threshold against ambient noise.

        Call this once before start_listening() for best accuracy.
        """
        try:
            with sr.Microphone() as source:
                logger.info(
                    "Calibrating for ambient noise (%.1f s) …", duration
                )
                self._recogniser.adjust_for_ambient_noise(source, duration=duration)
                self._calibrated = True
                logger.info(
                    "Calibration done. Energy threshold: %.1f",
                    self._recogniser.energy_threshold,
                )
        except Exception as exc:
            logger.error("Ambient noise calibration failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal: background listen loop
    # ------------------------------------------------------------------

    def _listen_loop(self) -> None:
        """Main loop: capture audio and dispatch to recognition worker."""
        # Spawn a recognition worker thread
        recogniser_thread = threading.Thread(
            target=self._recognition_worker,
            daemon=True,
            name="STTRecogniserThread",
        )
        recogniser_thread.start()

        if not self._calibrated:
            self.adjust_for_ambient_noise()

        logger.debug("Entering listen loop …")
        while not self._stop_flag.is_set():
            try:
                with sr.Microphone() as source:
                    self._microphone = source
                    audio = self._recogniser.listen(
                        source,
                        timeout=LISTEN_TIMEOUT,
                        phrase_time_limit=PHRASE_TIME_LIMIT,
                    )
                    self._audio_queue.put(audio)
            except sr.WaitTimeoutError:
                # No speech detected in timeout window – loop back
                continue
            except OSError as exc:
                logger.error("Microphone error: %s", exc)
                time.sleep(1)
            except Exception as exc:
                logger.error("Listen loop error: %s", exc)
                time.sleep(0.5)

        # Signal recognition worker to exit
        self._audio_queue.put(None)
        recogniser_thread.join(timeout=5)
        logger.debug("Listen loop exited.")

    # ------------------------------------------------------------------
    # Internal: recognition worker
    # ------------------------------------------------------------------

    def _recognition_worker(self) -> None:
        """Pull audio from the queue and run STT."""
        while True:
            audio = self._audio_queue.get()
            if audio is None:
                break
            text = self._recognise(audio)
            if text:
                self._handle_recognised_text(text.strip().lower())

    def _recognise(self, audio: sr.AudioData) -> Optional[str]:
        """Try Google STT, fall back to Whisper on failure."""
        # --- Google ---
        try:
            text = self._recogniser.recognize_google(
                audio, language=LANGUAGE_CODE
            )
            logger.debug("Google STT: %r", text)
            return text
        except sr.UnknownValueError:
            logger.debug("Google STT: could not understand audio.")
        except sr.RequestError as exc:
            logger.warning("Google STT request error (%s); trying Whisper.", exc)

        # --- Whisper fallback ---
        if self._use_whisper_fallback and self._whisper_model is not None:
            return self._recognise_whisper(audio)

        return None

    def _recognise_whisper(self, audio: sr.AudioData) -> Optional[str]:
        """Transcribe audio using faster-whisper offline model."""
        import io
        import wave

        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            # Write to in-memory WAV
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(raw)
            buf.seek(0)

            segments, _ = self._whisper_model.transcribe(buf, language="en")
            text = " ".join(seg.text for seg in segments).strip()
            logger.debug("Whisper STT: %r", text)
            return text or None
        except Exception as exc:
            logger.error("Whisper STT failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal: wake-word & command dispatch
    # ------------------------------------------------------------------

    def _handle_recognised_text(self, text: str) -> None:
        """Detect wake word and fire the command callback."""
        if not self._awake:
            if self._contains_wake_word(text):
                self._awake = True
                logger.info("Wake word detected in: %r", text)
                # Extract any inline command after wake word
                command = self._strip_wake_word(text)
                if command:
                    self._dispatch(command)
        else:
            # Already awake – treat everything as a command
            if text:
                self._dispatch(text)
            # Reset wake state after one command (push-to-talk style)
            self._awake = False

    @staticmethod
    def _contains_wake_word(text: str) -> bool:
        for ww in WAKE_WORDS:
            if ww in text:
                return True
        return False

    @staticmethod
    def _strip_wake_word(text: str) -> str:
        """Remove the wake word from the start of recognised text."""
        for ww in sorted(WAKE_WORDS, key=len, reverse=True):
            if text.startswith(ww):
                return text[len(ww):].strip(" ,.")
        return text

    def _dispatch(self, command: str) -> None:
        logger.info("Command dispatched: %r", command)
        try:
            self.on_command(command)
        except Exception as exc:
            logger.error("on_command callback raised: %s", exc)

    # ------------------------------------------------------------------
    # Internal: Whisper model loader
    # ------------------------------------------------------------------

    def _load_whisper_model(self) -> None:
        try:
            logger.info("Loading Whisper model '%s' …", WHISPER_MODEL_SIZE)
            self._whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper model loaded.")
        except Exception as exc:
            logger.error("Failed to load Whisper model: %s", exc)
            self._whisper_model = None
            self._use_whisper_fallback = False


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    def my_handler(text: str) -> None:
        print(f"\n>>> Command received: {text}\n")

    engine = STTEngine(on_command=my_handler)
    engine.adjust_for_ambient_noise()
    engine.start_listening()

    print("Say 'Hey CHOTU <command>' … (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop_listening()
        print("Stopped.")
