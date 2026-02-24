"""
Voice Interview Agent - Phased Interview via Voice.

Combines speech-to-text and text-to-speech with the Phased Interview Agent
to conduct interviews entirely via voice.

Flow:
1. Scoping questions spoken aloud
2. Domain expert deep-dives
3. Summary spoken at the end
"""

import time
from typing import Optional
from dataclasses import dataclass

from .speech_to_text import SpeechToText, MicrophoneRecorder
from .text_to_speech import TextToSpeech
from ..agents.phased_interview_agent import PhasedInterviewAgent, InterviewPhase


@dataclass
class VoiceConfig:
    """Configuration for voice interview."""
    # Speech-to-text settings
    whisper_model: str = "base"  # tiny, base, small, medium, large-v3
    language: str = "en"

    # Text-to-speech settings
    speech_rate: int = 160  # Words per minute (slower for clarity)
    volume: float = 1.0

    # ElevenLabs settings (set API key via env or here)
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice: Optional[str] = None  # e.g., "rachel", "adam", "sarah"
    elevenlabs_model: Optional[str] = None  # e.g., "eleven_multilingual_v2"

    # Recording settings
    silence_threshold: float = 0.01
    silence_duration: float = 1.5  # Seconds of silence to stop recording
    max_recording_duration: float = 60.0  # Maximum seconds per response

    # Interview settings
    use_llm: bool = True
    confirm_transcription: bool = False  # Ask user to confirm what was heard


class VoiceInterviewAgent:
    """
    Voice-based interview agent for Odoo ERP discovery.

    Conducts the interview entirely via voice:
    1. Speaks questions using text-to-speech
    2. Listens for responses using speech-to-text
    3. Processes responses and moves through phases
    4. Speaks domain expert intros when switching domains
    """

    def __init__(
        self,
        client_name: Optional[str],
        industry: Optional[str],
        config: Optional[VoiceConfig] = None,
        output_dir: str = "./outputs"
    ):
        """
        Initialize the voice interview agent.

        Args:
            client_name: Name of the client company
            industry: Client's industry
            config: Voice configuration options
            output_dir: Directory for output files
        """
        self.config = config or VoiceConfig()

        # Initialize speech components
        print("🎙️ Initializing voice components...")

        print("   Loading speech-to-text (Whisper)...")
        self.stt = SpeechToText(
            model_size=self.config.whisper_model,
            language=self.config.language
        )

        print("   Loading text-to-speech...")
        self.tts = TextToSpeech(
            rate=self.config.speech_rate,
            volume=self.config.volume,
            elevenlabs_api_key=self.config.elevenlabs_api_key,
            elevenlabs_voice=self.config.elevenlabs_voice,
            elevenlabs_model=self.config.elevenlabs_model,
        )

        print("   Setting up microphone...")
        self.recorder = MicrophoneRecorder(sample_rate=16000)

        self.client_name = (client_name or "").strip()
        self.industry = (industry or "").strip()
        self.output_dir = output_dir
        self.agent: Optional[PhasedInterviewAgent] = None

        self._running = False
        self._last_question_text: Optional[str] = None
        self._current_question: Optional[dict] = None
        print("✓ Voice interview agent ready!")

    def speak(self, text: str, prefix: str = ""):
        """
        Speak text with optional visual feedback.

        Args:
            text: Text to speak
            prefix: Prefix emoji for visual display
        """
        if prefix:
            print(f"{prefix} {text}")
        else:
            print(f"🔊 {text}")

        self.tts.speak(text)

    def listen(self) -> str:
        """
        Listen for user speech and transcribe.

        Returns:
            Transcribed text
        """
        # Visual indicator
        print("\n🎤 Listening... (speak now, pause when done)")

        # Record audio
        try:
            audio = self.recorder.record_until_silence(
                silence_threshold=self.config.silence_threshold,
                silence_duration=self.config.silence_duration,
                max_duration=self.config.max_recording_duration
            )
        except Exception as e:
            if "No microphone found" in str(e):
                print("⚠️  No microphone found. Switching to text input.")
                return self._listen_text()
            raise

        if len(audio) == 0:
            print("   No speech detected")
            return ""

        # Transcribe
        print("   Transcribing...")
        result = self.stt.transcribe(audio)

        print(f"   Heard: \"{result.text}\"")

        # Optionally confirm
        if self.config.confirm_transcription and result.text:
            self.speak(f"I heard: {result.text}. Is that correct?", "🔄")

        return result.text

    def _listen_text(self) -> str:
        """Fallback to text input when microphone isn't available."""
        try:
            return input("⌨️  Type your answer and press Enter: ").strip()
        except EOFError:
            return ""

    def run_interview(self):
        """
        Run the complete voice interview.

        This method conducts the full interview via voice,
        handling all phases: scoping → domain experts → summary.
        """
        self._ensure_interview_agent()
        self._running = True

        # Welcome message
        welcome = f"""
        Welcome to the Odoo Implementation Discovery Interview for {self.client_name}.
        I'll ask you questions about your business to understand your requirements.
        Please speak clearly, and pause when you're done with each answer.
        Let's begin!
        """
        self.speak(welcome.strip(), "👋")

        time.sleep(1)

        # Main interview loop
        while self._running:
            # Get next question
            question_data = self.agent.get_next_question()

            if question_data is None or self.agent.is_complete():
                break

            self._current_question = question_data

            # Announce phase/domain changes
            if question_data.get('expert_intro'):
                time.sleep(0.5)
                self.speak(question_data['expert_intro'], "🔀")
                time.sleep(0.5)

            # Speak the question
            question_text = question_data['text']
            self.speak(question_text, "❓")
            self._last_question_text = question_text

            # Show progress
            progress = question_data.get('progress', {})
            phase = progress.get('phase', 'Unknown')
            percent = progress.get('overall_percent', 0)
            print(f"   📊 Progress: {percent}% ({phase})")

            # Listen for response
            response = self.listen()

            if not response:
                self.speak("I didn't catch that. Could you repeat your answer?", "🔄")
                response = self.listen()

            if not response:
                self.speak("Let's skip this question and move on.", "⏭️")
                self.agent.skip_question(question_data)
                continue

            # Handle special voice commands
            if self._check_voice_command(response):
                continue

            # Process the response
            result = self.agent.process_response(response, question_data)

            # Announce detected signals
            signals = result.get('signals_detected', {})
            if signals:
                signal_names = list(signals.keys())[:3]  # Limit to 3
                self.speak(f"Got it. I'm noting: {', '.join(signal_names)}.", "📝")

            time.sleep(0.3)  # Brief pause between questions

        # Interview complete
        self._complete_interview()

    def _ensure_interview_agent(self):
        """Collect client/industry if needed and initialize the interview agent."""
        if not self.client_name:
            self.client_name = self._ask_for_field(
                "What is the client or company name?"
            )

        if not self.industry:
            self.industry = self._ask_for_field(
                "What industry is the company in?"
            )

        if self.agent is None:
            print("   Loading interview agent...")
            self.agent = PhasedInterviewAgent(
                client_name=self.client_name,
                industry=self.industry,
                output_dir=self.output_dir
            )

    def _ask_for_field(self, prompt: str) -> str:
        """Ask a single question via voice and return a non-empty response."""
        attempts = 0
        while True:
            self.speak(prompt, "❓")
            response = self.listen().strip()
            if response:
                return response
            attempts += 1
            if attempts >= 2:
                self.speak("I still didn't catch that. Let's try once more.", "🔄")
            else:
                self.speak("I didn't catch that. Please say it again.", "🔄")

    def _check_voice_command(self, text: str) -> bool:
        """
        Check for voice commands in the response.

        Commands:
        - "skip" / "next question" - skip current question
        - "pause" / "stop" - pause the interview
        - "repeat" - repeat the last question

        Returns:
            True if a command was processed
        """
        text_lower = text.lower()

        if "pause" in text_lower or "stop interview" in text_lower:
            self.speak("Pausing the interview. Say 'continue' when ready.", "⏸️")
            self._running = False
            # Save progress
            filepath = self.agent.save_interview()
            self.speak("Progress saved.", "💾")
            return True

        if "skip" in text_lower or "next question" in text_lower:
            self.speak("Skipping this question.", "⏭️")
            if self._current_question:
                self.agent.skip_question(self._current_question)
            return True

        if "repeat" in text_lower or "say that again" in text_lower:
            if self._last_question_text:
                self.speak(self._last_question_text, "🔁")
            else:
                self.speak("I don't have a question to repeat yet.", "ℹ️")
            return True

        return False

    def _complete_interview(self):
        """Handle interview completion."""
        self.speak(
            "Thank you for completing the discovery interview! "
            "I now have a good understanding of your business requirements.",
            "🎉"
        )

        # Get summary
        summary = self.agent.get_summary()

        # Announce domains covered
        domains_covered = summary.get('domains_covered', [])
        if domains_covered:
            domains_text = ", ".join(domains_covered[:4])
            self.speak(f"We covered these areas: {domains_text}.", "📋")

        # Announce recommended modules
        modules = summary.get('recommended_modules', [])
        if modules:
            modules_text = ", ".join(modules[:5])
            self.speak(f"Based on your answers, I recommend these Odoo modules: {modules_text}.", "✅")

        # Save results
        filepath = self.agent.save_interview()
        self.speak(
            "I've saved all the requirements to a file. "
            "You can share this with your implementation team.",
            "📄"
        )

        print(f"\n📁 Interview saved to: {filepath}")

    def pause(self):
        """Pause the interview."""
        self._running = False

    def resume(self):
        """Resume a paused interview."""
        if self.agent and not self.agent.is_complete():
            self.speak("Resuming the interview.", "▶️")
            self._running = True
            self.run_interview()


def run_voice_interview(
    client_name: Optional[str],
    industry: Optional[str],
    whisper_model: str = "base",
    use_llm: bool = True
):
    """
    Convenience function to run a voice interview.

    Args:
        client_name: Client company name (optional; will ask via voice if missing)
        industry: Client's industry (optional; will ask via voice if missing)
        whisper_model: Whisper model size (tiny, base, small)
        use_llm: Whether to use LLM for enhanced conversation
    """
    config = VoiceConfig(
        whisper_model=whisper_model,
        use_llm=use_llm,
        confirm_transcription=False  # Disable for smoother flow
    )

    agent = VoiceInterviewAgent(
        client_name=client_name,
        industry=industry,
        config=config
    )

    print("\n" + "=" * 60)
    print("VOICE INTERVIEW - ODOO ERP DISCOVERY (Phased)")
    print("=" * 60)
    print(f"Client: {client_name or '[ask via voice]'}")
    print(f"Industry: {industry or '[ask via voice]'}")
    print(f"Whisper Model: {whisper_model}")
    print("=" * 60)
    print("\nVoice Commands:")
    print("  - Say 'skip' to skip a question")
    print("  - Say 'pause' to pause the interview")
    print("  - Say 'repeat' to hear the question again")
    print("=" * 60 + "\n")

    agent.run_interview()
