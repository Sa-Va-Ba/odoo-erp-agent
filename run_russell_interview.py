#!/usr/bin/env python3
"""
Voice Interview for Russell's Odoo Setup

Run in VS Code terminal:
    python3 run_russell_interview.py
"""

import warnings
warnings.filterwarnings('ignore')

import time
import sys

def main():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     ODOO DISCOVERY INTERVIEW - Russell's Business             ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    # Import components
    print("Loading components...")

    from src.voice.speech_to_text import SpeechToText, MicrophoneRecorder
    from src.voice.text_to_speech import TextToSpeech
    from src.agents.smart_interview_agent import SmartInterviewAgent
    from src.branching.engine import ActionType

    # Initialize TTS
    print("  ✓ Text-to-speech")
    tts = TextToSpeech(rate=160)

    # Initialize STT
    print("  ✓ Speech-to-text (Whisper)")
    stt = SpeechToText(model_size="base", language="en")

    # Initialize recorder
    print("  ✓ Microphone")
    recorder = MicrophoneRecorder(sample_rate=16000)

    # Initialize interview agent
    print("  ✓ Interview agent")
    agent = SmartInterviewAgent(
        client_name="Russell's Business",
        industry="Consulting",
        use_llm=True
    )

    # Try to set up Ollama
    try:
        from src.llm.ollama_provider import OllamaProvider
        ollama = OllamaProvider(model="mistral:latest")
        if ollama.is_available():
            agent.llm_manager._providers["ollama"] = ollama
            agent.llm_manager._current_provider = "ollama"
            print("  ✓ Ollama LLM")
    except:
        print("  ○ No LLM (rule-based mode)")

    print("\n" + "="*60)
    print("READY! Starting interview...")
    print("="*60)
    print("\nCommands: say 'skip' to skip, 'pause' to stop")
    print("="*60 + "\n")

    # Welcome
    welcome = "Welcome! I'll ask you questions about Russell's business for the Odoo setup. Speak clearly and pause when done."
    print(f"🔊 {welcome}")
    tts.speak(welcome)

    time.sleep(1)

    # Start interview
    agent.start_interview()
    agent.branching_engine.reset_state()

    questions_asked = 0
    max_questions = 15  # Limit for demo

    while agent.session.state.value == "in_progress" and questions_asked < max_questions:
        # Get question
        question_text, question = agent.get_next_question_smart()

        if question_text is None:
            # Domain complete
            domain_name = agent.current_domain.title
            print(f"\n✅ {domain_name} complete!")
            tts.speak(f"{domain_name} section complete. Moving on.")
            agent.complete_current_domain()

            if agent.session.state.value == "completed":
                break

            print(f"\n📋 Next: {agent.current_domain.title}")
            time.sleep(0.5)
            continue

        questions_asked += 1

        # Ask question
        print(f"\n{'─'*60}")
        print(f"Q{questions_asked}: {question_text}")
        print(f"{'─'*60}")
        tts.speak(question_text)

        # Listen for answer
        print("\n🎤 Listening... (speak now, pause when done)")

        try:
            audio = recorder.record_until_silence(
                silence_threshold=0.01,
                silence_duration=1.5,
                max_duration=30.0
            )

            if len(audio) == 0:
                print("   No speech detected, skipping...")
                response = "[skipped]"
            else:
                # Transcribe
                print("   Transcribing...")
                result = stt.transcribe(audio)
                response = result.text
                print(f"   Heard: \"{response}\"")

        except KeyboardInterrupt:
            print("\n\n⏹️ Interview stopped")
            break
        except Exception as e:
            print(f"   Error: {e}")
                response = "[error]"

        if response in ["[skipped]", "[error]"]:
            if question:
                agent.current_domain_progress.current_question_index += 1
            continue

        # Check for commands
        if "skip" in response.lower():
            print("   ⏭️ Skipping...")
            if question:
                agent.current_domain_progress.current_question_index += 1
            continue

        if "pause" in response.lower() or "stop" in response.lower():
            print("   ⏸️ Pausing...")
            break

        # Process response
        if question and response and response not in ["[skipped]", "[error]"]:
            action = agent.handle_response(response, question)

            # Handle follow-ups
            if action.action_type in [ActionType.ASK_FOLLOW_UP, ActionType.PROBE_DEEPER]:
                print(f"\n🔍 Follow-up: {action.question_text}")
                tts.speak(action.question_text)

                print("\n🎤 Listening...")
                try:
                    audio = recorder.record_until_silence(
                        silence_threshold=0.01,
                        silence_duration=1.5,
                        max_duration=30.0
                    )
                    if len(audio) > 0:
                        result = stt.transcribe(audio)
                        print(f"   Heard: \"{result.text}\"")
                        agent.record_follow_up_response(action.question_text, result.text)
                    else:
                        agent.record_follow_up_response(action.question_text, "[SKIPPED]")
                except:
                    agent.record_follow_up_response(action.question_text, "[SKIPPED]")

        time.sleep(0.3)

    # Complete
    print("\n" + "="*60)
    print("INTERVIEW COMPLETE!")
    print("="*60)

    tts.speak("Thank you! The interview is complete.")

    # Save results
    filepath = agent.generate_requirements_json()
    print(f"\n📄 Requirements saved to: {filepath}")

    # Show summary
    summary = agent.branching_engine.get_interview_summary()
    print(f"\n📊 Summary:")
    print(f"   Systems detected: {summary.get('systems_mentioned', [])}")
    print(f"   Pain points: {len(summary.get('pain_points', []))}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
