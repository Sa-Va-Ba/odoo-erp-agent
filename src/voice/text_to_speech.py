"""
Text-to-Speech with ElevenLabs (primary) and pyttsx3 (offline fallback).

ElevenLabs provides natural, high-quality voices via API.
Falls back to pyttsx3 (OS-native) when offline or no API key is set.
"""

import io
import os
import time
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass


def _load_dotenv():
    """Load .env file from project root if present."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass
class Voice:
    """Information about an available voice."""
    id: str
    name: str
    languages: List[str]
    gender: str = "unknown"
    provider: str = "system"  # "elevenlabs" or "system"


# Popular ElevenLabs voices for professional interviews
ELEVENLABS_VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",   # Calm, professional female
    "drew": "29vD33N1CtxCmqQRPOHJ",      # Well-rounded male
    "clyde": "2EiwWnXFnvU5JabPnv8n",     # Deep, authoritative male
    "domi": "AZnzlk1XvdvUeBnXmlld",      # Strong, confident female
    "dave": "CYw3kZ02Hs0563khs1Fj",      # Conversational male
    "fin": "D38z5RcWu1voky8WS1ja",       # Easygoing male
    "sarah": "EXAVITQu4vr4xnSDxMaL",     # Soft, natural female
    "adam": "pNInz6obpgDQGcFmaJgB",       # Deep, narration male
    "jessica": "cgSgspJ2msm6clMCkdW9",   # Expressive female
    "chris": "iP95p4xoKVk53GoZ742B",     # Casual male
}

# Default voice for interviews — professional and clear
DEFAULT_VOICE = "rachel"
DEFAULT_MODEL = "eleven_multilingual_v2"


class TextToSpeech:
    """
    Text-to-Speech engine with ElevenLabs and pyttsx3 fallback.

    Uses ElevenLabs for natural-sounding speech when an API key is available.
    Falls back to pyttsx3 (offline, OS-native) otherwise.
    """

    def __init__(
        self,
        rate: int = 175,
        volume: float = 1.0,
        voice_name: Optional[str] = None,
        # ElevenLabs settings
        elevenlabs_api_key: Optional[str] = None,
        elevenlabs_voice: Optional[str] = None,
        elevenlabs_model: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
    ):
        """
        Initialize the text-to-speech engine.

        Args:
            rate: Speech rate in words per minute (pyttsx3 fallback)
            volume: Volume level from 0.0 to 1.0
            voice_name: Name of pyttsx3 voice (e.g., "Samantha", "Daniel")
            elevenlabs_api_key: ElevenLabs API key (or set ELEVENLABS_API_KEY env var)
            elevenlabs_voice: ElevenLabs voice name or ID (default: "rachel")
            elevenlabs_model: ElevenLabs model ID (default: eleven_multilingual_v2)
            stability: Voice stability 0.0-1.0 (lower = more expressive)
            similarity_boost: Voice clarity 0.0-1.0 (higher = closer to original)
            style: Style exaggeration 0.0-1.0 (higher = more stylistic)
        """
        self.rate = rate
        self.volume = volume
        self.voice_name = voice_name
        self._voice_id = None

        # ElevenLabs configuration
        self._api_key = elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY")
        self._elevenlabs_model = elevenlabs_model or DEFAULT_MODEL
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._style = style

        # Resolve ElevenLabs voice name to ID
        voice_input = elevenlabs_voice or DEFAULT_VOICE
        if voice_input.lower() in ELEVENLABS_VOICES:
            self._elevenlabs_voice_id = ELEVENLABS_VOICES[voice_input.lower()]
        else:
            # Treat as a raw voice ID
            self._elevenlabs_voice_id = voice_input

        # Determine provider
        self._use_elevenlabs = bool(self._api_key)

        if self._use_elevenlabs:
            print(f"   Using ElevenLabs TTS (voice: {voice_input})")
        else:
            print("   Using pyttsx3 TTS (set ELEVENLABS_API_KEY for natural voices)")
            if voice_name:
                self._voice_id = self._find_voice_id(voice_name)

    # ── ElevenLabs ──────────────────────────────────────────────

    def _speak_elevenlabs(self, text: str):
        """Generate and play speech using ElevenLabs API."""
        import requests

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._elevenlabs_voice_id}"

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self._elevenlabs_model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": self._similarity_boost,
                "style": self._style,
                "use_speaker_boost": True,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        self._play_audio(response.content)

    def _speak_elevenlabs_stream(self, text: str):
        """Stream and play speech using ElevenLabs API for lower latency."""
        import requests

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{self._elevenlabs_voice_id}/stream"
        )

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self._elevenlabs_model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": self._similarity_boost,
                "style": self._style,
                "use_speaker_boost": True,
            },
        }

        response = requests.post(
            url, json=payload, headers=headers, stream=True, timeout=30
        )
        response.raise_for_status()

        # Collect streamed chunks and play
        audio_data = b""
        for chunk in response.iter_content(chunk_size=4096):
            if chunk:
                audio_data += chunk

        self._play_audio(audio_data)

    def _play_audio(self, audio_bytes: bytes):
        """Play MP3 audio bytes through the system speakers."""
        try:
            # Try pydub + simpleaudio (best cross-platform)
            from pydub import AudioSegment
            from pydub.playback import play

            audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            play(audio)
        except ImportError:
            # Fallback: write to temp file and use system player
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name

            try:
                # macOS
                subprocess.run(
                    ["afplay", temp_path], check=True, timeout=60,
                    capture_output=True
                )
            except FileNotFoundError:
                try:
                    # Linux
                    subprocess.run(
                        ["mpg123", "-q", temp_path], check=True, timeout=60,
                        capture_output=True
                    )
                except FileNotFoundError:
                    try:
                        # Windows
                        import winsound
                        # Convert to wav first
                        subprocess.run(
                            ["ffmpeg", "-i", temp_path,
                             temp_path.replace(".mp3", ".wav"),
                             "-y", "-loglevel", "quiet"],
                            check=True, timeout=30
                        )
                        winsound.PlaySound(
                            temp_path.replace(".mp3", ".wav"),
                            winsound.SND_FILENAME
                        )
                    except Exception:
                        print("Warning: Could not play audio. "
                              "Install pydub for best results: pip install pydub")
            finally:
                os.unlink(temp_path)

    def generate_audio(self, text: str) -> bytes:
        """
        Generate audio bytes without playing (useful for web/API responses).

        Args:
            text: Text to synthesize

        Returns:
            MP3 audio bytes (ElevenLabs) or empty bytes (pyttsx3 not supported)
        """
        if not self._use_elevenlabs:
            return b""

        import requests

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._elevenlabs_voice_id}"

        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": self._elevenlabs_model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": self._similarity_boost,
                "style": self._style,
                "use_speaker_boost": True,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content

    # ── pyttsx3 fallback ────────────────────────────────────────

    def _create_engine(self):
        """Create a fresh pyttsx3 engine (more reliable than reusing)."""
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', self.rate)
        engine.setProperty('volume', self.volume)

        if self._voice_id:
            engine.setProperty('voice', self._voice_id)

        return engine

    def _find_voice_id(self, name: str) -> Optional[str]:
        """Find voice ID by name."""
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')

        name_lower = name.lower()
        for voice in voices:
            if name_lower in voice.name.lower():
                return voice.id

        return None

    def _speak_pyttsx3(self, text: str):
        """Speak using pyttsx3 (offline fallback)."""
        try:
            engine = self._create_engine()
            engine.say(text)
            engine.runAndWait()
            time.sleep(0.1)
        except Exception as e:
            print(f"TTS Error: {e}")
            # Last-resort fallback: macOS 'say' command
            try:
                import subprocess
                subprocess.run(['say', text], check=True, timeout=30)
            except Exception as fallback_error:
                print(f"TTS Fallback also failed: {fallback_error}")

    # ── Public API ──────────────────────────────────────────────

    def speak(self, text: str):
        """
        Speak the given text. Blocks until complete.

        Uses ElevenLabs if API key is available, otherwise pyttsx3.

        Args:
            text: Text to speak
        """
        if not text or not text.strip():
            return

        if self._use_elevenlabs:
            try:
                self._speak_elevenlabs_stream(text)
            except Exception as e:
                print(f"ElevenLabs error: {e}. Falling back to offline TTS.")
                self._speak_pyttsx3(text)
        else:
            self._speak_pyttsx3(text)

    def speak_with_pause(self, text: str, pause_after: float = 0.5):
        """
        Speak text with a pause after.

        Args:
            text: Text to speak
            pause_after: Seconds to pause after speaking
        """
        self.speak(text)
        time.sleep(pause_after)

    def get_available_voices(self) -> List[Voice]:
        """
        Get list of available voices.

        Returns both ElevenLabs preset voices and system voices.

        Returns:
            List of Voice objects
        """
        voices = []

        # ElevenLabs voices
        if self._use_elevenlabs:
            for name, voice_id in ELEVENLABS_VOICES.items():
                voices.append(Voice(
                    id=voice_id,
                    name=name.title(),
                    languages=["en", "multilingual"],
                    provider="elevenlabs"
                ))

        # System voices (pyttsx3)
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for voice in engine.getProperty('voices'):
                voices.append(Voice(
                    id=voice.id,
                    name=voice.name,
                    languages=voice.languages if hasattr(voice, 'languages') else [],
                    gender=voice.gender if hasattr(voice, 'gender') else "unknown",
                    provider="system"
                ))
        except Exception:
            pass

        return voices

    def set_voice_by_name(self, name: str) -> bool:
        """
        Set voice by name.

        Checks ElevenLabs preset voices first, then system voices.

        Args:
            name: Voice name to search for

        Returns:
            True if voice was found and set
        """
        # Check ElevenLabs voices
        name_lower = name.lower()
        if name_lower in ELEVENLABS_VOICES:
            self._elevenlabs_voice_id = ELEVENLABS_VOICES[name_lower]
            self.voice_name = name
            return True

        # Check system voices
        voice_id = self._find_voice_id(name)
        if voice_id:
            self._voice_id = voice_id
            self.voice_name = name
            return True

        return False

    @property
    def provider(self) -> str:
        """Return the active TTS provider name."""
        return "elevenlabs" if self._use_elevenlabs else "pyttsx3"


def speak(text: str, rate: int = 175):
    """
    Convenience function to speak text.

    Args:
        text: Text to speak
        rate: Speech rate (words per minute, pyttsx3 only)
    """
    tts = TextToSpeech(rate=rate)
    tts.speak(text)


def list_voices() -> List[Voice]:
    """
    List all available voices.

    Returns:
        List of Voice objects
    """
    tts = TextToSpeech()
    return tts.get_available_voices()
