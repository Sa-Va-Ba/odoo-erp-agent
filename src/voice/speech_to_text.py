"""
Speech-to-Text using faster-whisper.

Provides local, offline speech recognition with support for:
- Microphone input (real-time)
- Audio file transcription
- Multiple languages
"""

import os
import tempfile
import wave
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

import numpy as np


@dataclass
class TranscriptionResult:
    """Result from speech-to-text transcription."""
    text: str
    language: str = "en"
    confidence: float = 0.0
    duration: float = 0.0


class SpeechToText:
    """
    Speech-to-Text engine using faster-whisper.

    faster-whisper is a reimplementation of OpenAI's Whisper model
    using CTranslate2, which is up to 4x faster than the original.

    Models (smallest to largest):
    - tiny: ~75MB, fastest, lower accuracy
    - base: ~150MB, good balance
    - small: ~500MB, better accuracy
    - medium: ~1.5GB, high accuracy
    - large-v3: ~3GB, best accuracy
    """

    AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v3"]

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "en"
    ):
        """
        Initialize the speech-to-text engine.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3)
            device: Device to use (auto, cpu, cuda)
            compute_type: Computation type (auto, int8, float16, float32)
            language: Default language for transcription
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            print(f"Loading Whisper model '{self.model_size}'...")
            try:
                from faster_whisper import WhisperModel

                # Auto-detect best settings
                if self.device == "auto":
                    self.device = "cuda" if self._cuda_available() else "cpu"

                if self.compute_type == "auto":
                    self.compute_type = "float16" if self.device == "cuda" else "int8"

                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type
                )
                print(f"✓ Whisper model loaded on {self.device}")

            except Exception as e:
                raise RuntimeError(f"Failed to load Whisper model: {e}")

    def _cuda_available(self) -> bool:
        """Check if CUDA is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def transcribe(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio data to text.

        Args:
            audio_data: Audio samples as numpy array (float32, mono)
            sample_rate: Sample rate of the audio (default 16kHz)
            language: Language code (None for auto-detection)

        Returns:
            TranscriptionResult with transcribed text
        """
        self._load_model()

        # Ensure audio is float32 and normalized
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        if audio_data.max() > 1.0:
            audio_data = audio_data / 32768.0  # Normalize from int16

        # Transcribe
        segments, info = self._model.transcribe(
            audio_data,
            language=language or self.language,
            beam_size=5,
            vad_filter=True,  # Filter out silence
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        # Combine all segments
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = " ".join(text_parts)

        return TranscriptionResult(
            text=full_text,
            language=info.language,
            confidence=info.language_probability,
            duration=info.duration
        )

    def transcribe_file(self, audio_path: str) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to audio file (wav, mp3, etc.)

        Returns:
            TranscriptionResult with transcribed text
        """
        self._load_model()

        segments, info = self._model.transcribe(
            audio_path,
            language=self.language,
            beam_size=5,
            vad_filter=True
        )

        text_parts = [segment.text.strip() for segment in segments]
        full_text = " ".join(text_parts)

        return TranscriptionResult(
            text=full_text,
            language=info.language,
            confidence=info.language_probability,
            duration=info.duration
        )


class MicrophoneRecorder:
    """
    Records audio from the microphone.

    Uses sounddevice for cross-platform audio capture.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "float32"
    ):
        """
        Initialize the microphone recorder.

        Args:
            sample_rate: Audio sample rate (16000 recommended for Whisper)
            channels: Number of audio channels (1 for mono)
            dtype: Audio data type
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self._recording = False
        self._audio_buffer = []

    def _check_microphone(self) -> bool:
        """Check if a microphone is available."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [d for d in devices if d['max_input_channels'] > 0]
            return len(input_devices) > 0
        except Exception:
            return False

    def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 30.0,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable] = None
    ) -> np.ndarray:
        """
        Record audio until silence is detected.

        Args:
            silence_threshold: RMS threshold for silence detection
            silence_duration: Seconds of silence to stop recording
            max_duration: Maximum recording duration
            on_speech_start: Callback when speech starts
            on_speech_end: Callback when speech ends

        Returns:
            Recorded audio as numpy array
        """
        import sounddevice as sd

        if not self._check_microphone():
            raise RuntimeError("No microphone found")

        print("🎤 Listening... (speak now)")

        audio_chunks = []
        silence_chunks = 0
        speech_started = False
        chunks_for_silence = int(silence_duration * self.sample_rate / 1024)
        max_chunks = int(max_duration * self.sample_rate / 1024)

        def callback(indata, frames, time, status):
            nonlocal silence_chunks, speech_started

            if status:
                print(f"Audio status: {status}")

            chunk = indata.copy().flatten()
            rms = np.sqrt(np.mean(chunk**2))

            if rms > silence_threshold:
                if not speech_started:
                    speech_started = True
                    if on_speech_start:
                        on_speech_start()
                silence_chunks = 0
                audio_chunks.append(chunk)
            elif speech_started:
                silence_chunks += 1
                audio_chunks.append(chunk)  # Include some silence

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=1024,
            callback=callback
        ):
            # Wait for speech and silence
            chunk_count = 0
            while chunk_count < max_chunks:
                sd.sleep(100)  # 100ms
                chunk_count += 1

                if speech_started and silence_chunks >= chunks_for_silence:
                    if on_speech_end:
                        on_speech_end()
                    break

        if not audio_chunks:
            return np.array([], dtype=np.float32)

        return np.concatenate(audio_chunks)

    def record_fixed_duration(self, duration: float = 5.0) -> np.ndarray:
        """
        Record audio for a fixed duration.

        Args:
            duration: Recording duration in seconds

        Returns:
            Recorded audio as numpy array
        """
        import sounddevice as sd

        if not self._check_microphone():
            raise RuntimeError("No microphone found")

        print(f"🎤 Recording for {duration} seconds...")

        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype
        )
        sd.wait()

        return audio.flatten()


def transcribe_audio_file(
    file_path: str,
    model_size: str = "base",
    language: str = "en"
) -> str:
    """
    Convenience function to transcribe an audio file.

    Args:
        file_path: Path to audio file
        model_size: Whisper model size
        language: Language code

    Returns:
        Transcribed text
    """
    stt = SpeechToText(model_size=model_size, language=language)
    result = stt.transcribe_file(file_path)
    return result.text
