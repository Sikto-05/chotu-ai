"""
CHOTU AI Voice Authenticator
=============================
Records owner voice samples, extracts MFCC feature vectors, stores a voice
profile, and verifies a speaker by cosine-similarity comparison.

Workflow
--------
1. ``enroll_owner(audio_data_list)``  – build & save profile from raw PCM
2. ``verify_speaker(audio_data)``     – compare against stored profile
3. ``is_enrolled()``                  – check whether a profile exists

Dependencies
------------
Required : numpy, pyaudio, wave, os, json, tempfile, logging
Optional : librosa  (for MFCC; falls back to energy heuristic if absent)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import List, Optional

import numpy as np
import pyaudio

# ---------------------------------------------------------------------------
# Optional librosa import
# ---------------------------------------------------------------------------
try:
    import librosa
    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "librosa not installed – falling back to energy-based voice verification."
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audio recording constants
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16_000        # Hz
CHANNELS = 1                # Mono
SAMPLE_WIDTH = 2            # 16-bit PCM
CHUNK_SIZE = 1_024          # frames per buffer
RECORD_SECONDS = 3          # duration of each enrollment sample

# ---------------------------------------------------------------------------
# Feature / matching constants
# ---------------------------------------------------------------------------
N_MFCC = 40                 # number of MFCC coefficients
SIMILARITY_THRESHOLD = 0.75 # cosine similarity threshold for a positive match
ENERGY_THRESHOLD_RATIO = 0.5  # fallback: fraction of owner energy for match

# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent.parent / "data"
PROFILE_NPY = _DATA_DIR / "voice_profile.npy"
PROFILE_META = _DATA_DIR / "voice_profile_meta.json"


class VoiceAuthenticator:
    """
    Owner-voice enrolment and verification system.

    Parameters
    ----------
    profile_path:
        Path to the .npy file that stores the voice profile.
        Defaults to ``data/voice_profile.npy`` in the project root.
    threshold:
        Cosine-similarity threshold (0.0–1.0) above which a speaker is
        considered to be the owner.
    """

    def __init__(
        self,
        profile_path: Optional[str] = None,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self._profile_path = Path(profile_path) if profile_path else PROFILE_NPY
        self._meta_path = self._profile_path.with_suffix(".json")
        self._threshold = threshold
        self._profile: Optional[np.ndarray] = None

        # Ensure data directory exists
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing profile if present
        self._load_profile()
        logger.info(
            "VoiceAuthenticator ready. Enrolled: %s | librosa: %s",
            self.is_enrolled(),
            _LIBROSA_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_enrolled(self) -> bool:
        """Return True if a voice profile is stored on disk."""
        return self._profile is not None and self._profile_path.exists()

    def enroll_owner(self, audio_data_list: Optional[List[bytes]] = None) -> bool:
        """
        Enrol the owner by recording (or accepting pre-recorded) audio samples.

        Parameters
        ----------
        audio_data_list:
            List of raw 16-bit PCM byte strings.  If None or empty, the method
            records ``RECORD_SECONDS``-second samples from the default microphone.
            Expects at least 3 samples; records 5 if none are provided.

        Returns
        -------
        bool
            True if enrolment succeeded.
        """
        if not audio_data_list:
            print("Enrolling owner voice – please speak clearly when prompted.")
            audio_data_list = []
            for i in range(5):
                print(f"  Recording sample {i + 1} / 5 … speak now.")
                raw = self._record_sample()
                if raw:
                    audio_data_list.append(raw)
                else:
                    logger.warning("Sample %d recording failed, skipping.", i + 1)

        if len(audio_data_list) < 3:
            logger.error(
                "Need at least 3 valid samples; got %d.", len(audio_data_list)
            )
            return False

        feature_vectors: List[np.ndarray] = []
        for idx, raw in enumerate(audio_data_list):
            vec = self._extract_features(raw)
            if vec is not None:
                feature_vectors.append(vec)
            else:
                logger.warning("Feature extraction failed for sample %d.", idx)

        if not feature_vectors:
            logger.error("All feature extractions failed – enrolment aborted.")
            return False

        # Average across samples for a robust profile
        profile = np.mean(np.stack(feature_vectors, axis=0), axis=0)
        self._profile = profile

        # Persist
        np.save(str(self._profile_path), profile)
        meta = {
            "sample_rate": SAMPLE_RATE,
            "n_mfcc": N_MFCC,
            "n_samples": len(feature_vectors),
            "librosa": _LIBROSA_AVAILABLE,
        }
        with open(self._meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

        logger.info(
            "Voice profile saved to '%s' (%d samples averaged).",
            self._profile_path,
            len(feature_vectors),
        )
        return True

    def verify_speaker(self, audio_data: bytes) -> float:
        """
        Verify whether *audio_data* matches the enrolled owner.

        Parameters
        ----------
        audio_data:
            Raw 16-bit PCM bytes (mono, 16 kHz).

        Returns
        -------
        float
            Confidence score in [0.0, 1.0].  Values ≥ threshold indicate a
            positive match.
        """
        if not self.is_enrolled():
            logger.warning("verify_speaker called but no voice profile is enrolled.")
            return 0.0

        probe = self._extract_features(audio_data)
        if probe is None:
            logger.warning("Feature extraction failed for probe audio.")
            return 0.0

        score = self._cosine_similarity(self._profile, probe)
        logger.debug("Speaker verification score: %.4f (threshold: %.2f)", score, self._threshold)
        return float(score)

    def is_owner(self, audio_data: bytes) -> bool:
        """
        Convenience wrapper that returns True when ``verify_speaker`` score
        meets or exceeds the configured threshold.
        """
        return self.verify_speaker(audio_data) >= self._threshold

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def _record_sample(self) -> Optional[bytes]:
        """
        Record a single audio sample from the default microphone.

        Returns raw 16-bit PCM bytes or None on failure.
        """
        pa = pyaudio.PyAudio()
        frames: List[bytes] = []
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
            n_chunks = int(SAMPLE_RATE / CHUNK_SIZE * RECORD_SECONDS)
            for _ in range(n_chunks):
                chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                frames.append(chunk)
            stream.stop_stream()
            stream.close()
            return b"".join(frames)
        except Exception as exc:
            logger.error("Recording failed: %s", exc)
            return None
        finally:
            pa.terminate()

    @staticmethod
    def _raw_to_wav_file(raw: bytes, path: str) -> None:
        """Write raw PCM bytes to a WAV file at *path*."""
        with wave.open(path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw)

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_features(self, raw: bytes) -> Optional[np.ndarray]:
        """
        Extract a feature vector from raw PCM audio.

        Uses MFCC via librosa when available; otherwise falls back to a
        simple energy-based feature vector.

        Returns a 1-D numpy array or None on failure.
        """
        if not raw:
            return None

        if _LIBROSA_AVAILABLE:
            return self._extract_mfcc(raw)
        return self._extract_energy_features(raw)

    def _extract_mfcc(self, raw: bytes) -> Optional[np.ndarray]:
        """Return mean MFCC vector (shape: [N_MFCC]) via librosa."""
        try:
            # Write to a temp WAV so librosa can load it
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, prefix="chotu_auth_"
            ) as tmp:
                tmp_path = tmp.name

            self._raw_to_wav_file(raw, tmp_path)
            y, sr_ = librosa.load(tmp_path, sr=SAMPLE_RATE, mono=True)
            mfcc = librosa.feature.mfcc(y=y, sr=sr_, n_mfcc=N_MFCC)
            # Mean over time → 1-D vector
            return np.mean(mfcc, axis=1)
        except Exception as exc:
            logger.error("MFCC extraction failed: %s", exc)
            return None
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _extract_energy_features(raw: bytes) -> Optional[np.ndarray]:
        """
        Fallback feature extractor: compute short-time energy in frames and
        return a normalised energy histogram as a fixed-length feature vector.
        """
        try:
            audio_i16 = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            # Normalise
            max_val = np.abs(audio_i16).max()
            if max_val < 1e-6:
                return None
            audio_norm = audio_i16 / max_val

            frame_len = CHUNK_SIZE
            n_frames = len(audio_norm) // frame_len
            energies = np.array([
                np.sum(audio_norm[i * frame_len:(i + 1) * frame_len] ** 2)
                for i in range(n_frames)
            ])
            # Return energy histogram (40 bins to match N_MFCC length)
            hist, _ = np.histogram(energies, bins=N_MFCC, density=True)
            return hist.astype(np.float32)
        except Exception as exc:
            logger.error("Energy feature extraction failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Similarity metric
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two 1-D vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-9 or norm_b < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # ------------------------------------------------------------------
    # Profile persistence
    # ------------------------------------------------------------------

    def _load_profile(self) -> None:
        """Load an existing voice profile from disk if present."""
        if self._profile_path.exists():
            try:
                self._profile = np.load(str(self._profile_path))
                logger.info(
                    "Voice profile loaded from '%s' (shape %s).",
                    self._profile_path,
                    self._profile.shape,
                )
            except Exception as exc:
                logger.error("Failed to load voice profile: %s", exc)
                self._profile = None
        else:
            logger.debug("No voice profile found at '%s'.", self._profile_path)

    def delete_profile(self) -> bool:
        """
        Remove the stored voice profile from disk.

        Returns True if deleted, False if nothing to delete.
        """
        deleted = False
        for path in (self._profile_path, self._meta_path):
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except OSError as exc:
                    logger.error("Could not delete '%s': %s", path, exc)
        if deleted:
            self._profile = None
            logger.info("Voice profile deleted.")
        return deleted


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    auth = VoiceAuthenticator()

    if len(sys.argv) > 1 and sys.argv[1] == "enroll":
        success = auth.enroll_owner()
        print("Enrollment", "succeeded." if success else "FAILED.")
    else:
        if not auth.is_enrolled():
            print("No profile found. Run:  python voice_auth.py enroll")
            sys.exit(1)

        print("Recording verification sample …")
        raw = auth._record_sample()  # noqa: SLF001
        if raw:
            score = auth.verify_speaker(raw)
            match = score >= SIMILARITY_THRESHOLD
            print(f"Score: {score:.4f}  |  Match: {match}  (threshold: {SIMILARITY_THRESHOLD})")
        else:
            print("Recording failed.")
