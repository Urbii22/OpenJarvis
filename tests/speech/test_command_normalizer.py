from openjarvis.speech.command_normalizer import normalize_command


def test_normalize_command_lowercase_and_remove_accents():
    assert normalize_command("PÓN Música") == "pon musica"


def test_normalize_command_strips_wake_word_variants():
    assert normalize_command("hola jarvis, abre spotify") == "abre spotify"
    assert normalize_command("oye jarvis pon musica") == "pon musica"
    assert normalize_command("hey jarvis que hora es") == "que hora es"
    assert normalize_command("jarvis, luces salon") == "luces salon"


def test_normalize_command_removes_punctuation_and_compacts_spaces():
    assert normalize_command("  Oye  Jarvis...   pon,  timer!!! 5 min  ") == "pon timer 5 min"


def test_normalize_command_keeps_semantic_typos():
    assert normalize_command("jarvis prendhe la luzz") == "prendhe la luzz"


def test_normalize_command_empty_after_wake_word():
    assert normalize_command("hola jarvis!!!") == ""
