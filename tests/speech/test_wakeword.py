from openjarvis.speech.wakeword import WakeWordDetector


def test_detect_and_strip_wake_word():
    detector = WakeWordDetector("jarvis")
    assert detector.detect("Jarvis abre calculadora")
    assert detector.strip("Jarvis, abre calculadora") == "abre calculadora"


def test_empty_wake_word_matches_all():
    detector = WakeWordDetector("")
    assert detector.detect("hola")
    assert detector.strip("hola") == "hola"

