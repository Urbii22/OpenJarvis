from openjarvis.speech.realtime_session import RealtimeSessionConfig, RealtimeVoiceSession


def test_wake_word_activates_followup_window():
    session = RealtimeVoiceSession(RealtimeSessionConfig(wake_word="jarvis", followup_timeout_s=30))
    should_process, cleaned = session.consume("jarvis que hora es")
    assert should_process is True
    assert cleaned == "que hora es"

    should_process, cleaned = session.consume("y mañana")
    assert should_process is True
    assert cleaned == "y mañana"


def test_ignores_text_without_wake_word_when_idle():
    session = RealtimeVoiceSession(RealtimeSessionConfig(wake_word="jarvis", followup_timeout_s=1))
    should_process, cleaned = session.consume("hola")
    assert should_process is False
    assert cleaned == ""

