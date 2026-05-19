from __future__ import annotations

import argparse
import io
import subprocess
import threading
import ctypes
import sys
from ctypes import wintypes
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import winsound
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import numpy as np

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None

from openjarvis.core.config import load_config
from openjarvis.sdk import Jarvis
from openjarvis.speech._discovery import get_speech_backend
from openjarvis.speech.realtime_session import RealtimeSessionConfig, RealtimeVoiceSession
from openjarvis.speech.tts import TTSCancelToken, TTSResult
from openjarvis.speech.voice_runtime import resolve_voice_selection, synthesize_with_fallback
from openjarvis.ui import TerminalVoiceUI, VoiceUiEvent

try:
    from voice_pc_tools import handle_pc_command
except ModuleNotFoundError:
    # Support module loading via importlib in tests where scripts/ is not on sys.path.
    _SCRIPT_DIR = Path(__file__).resolve().parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    from voice_pc_tools import handle_pc_command


@dataclass
class VoiceConfig:
    hotkey: str
    sample_rate: int
    max_seconds: float
    min_seconds: float
    language: str | None
    agent: str | None
    stt_model: str
    pc_tools: bool
    continuous_mode_enabled: bool
    wake_word: str
    barge_in_enabled: bool
    memory_context_enabled: bool
    voice_identity_enabled: bool
    voice_user_id: str
    voice_session_id: str
    input_device: int | None


HOTKEY_ID = 0x1001
EXIT_HOTKEY_ID = 0x1002
STOP_SPEAK_HOTKEY_ID = 0x1003
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


_status_lock = threading.Lock()
_last_status = ""
_tts_lock = threading.Lock()
_tts_process: object | None = None
_stt_lock = threading.Lock()
_stt_backend = None
_executor = ThreadPoolExecutor(max_workers=1)
_barge_lock = threading.Lock()
_barge_in_requested = False
_main_hotkey_lock = threading.Lock()
_last_main_hotkey_ts = 0.0
_continuous_stop_event = threading.Event()
_continuous_thread: threading.Thread | None = None
_voice_ui: TerminalVoiceUI | None = None


@dataclass
class _TtsPlaybackHandle:
    cancel_token: TTSCancelToken
    stop_event: threading.Event
    interrupt_cancellation_enabled: bool


def _set_status(state: str, detail: str = "") -> None:
    """Print a concise runtime status line for live debugging."""
    global _last_status
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{state}] {detail}".rstrip()
    with _status_lock:
        _last_status = line
        ui = _voice_ui
        if ui is not None:
            level = "info"
            upper_state = state.upper()
            if upper_state in {"WARN", "WARNING"}:
                level = "warning"
            elif upper_state in {"ERROR"}:
                level = "error"
            ui.emit(VoiceUiEvent(state=upper_state, detail=detail, level=level))
        else:
            print(line, flush=True)


def _set_mic_level(rms: float, peak: float) -> None:
    ui = _voice_ui
    if ui is not None:
        ui.emit(
            VoiceUiEvent(
                state="MIC",
                detail=f"rms={rms:.5f} peak={peak:.5f}",
                mic_rms=rms,
                mic_peak=peak,
            )
        )
    else:
        _set_status("MIC", f"rms={rms:.5f} peak={peak:.5f}")


def _request_barge_in() -> None:
    global _barge_in_requested
    with _barge_lock:
        _barge_in_requested = True


def _consume_barge_in() -> bool:
    global _barge_in_requested
    with _barge_lock:
        val = _barge_in_requested
        _barge_in_requested = False
        return val


def _main_hotkey_debounced(window_s: float = 0.35) -> bool:
    """Return True only once per physical press burst."""
    global _last_main_hotkey_ts
    now = time.perf_counter()
    with _main_hotkey_lock:
        if now - _last_main_hotkey_ts < window_s:
            return False
        _last_main_hotkey_ts = now
        return True


def _get_stt_backend(config, cfg: VoiceConfig):
    global _stt_backend
    with _stt_lock:
        if _stt_backend is not None:
            return _stt_backend
        try:
            # Force lightweight local STT for lower latency.
            from openjarvis.speech.faster_whisper import FasterWhisperBackend

            _stt_backend = FasterWhisperBackend(
                model_size=cfg.stt_model,
                device=config.speech.device,
                compute_type=config.speech.compute_type,
            )
        except Exception:
            _stt_backend = get_speech_backend(config)
        return _stt_backend


def _assert_dependencies() -> None:
    missing: list[str] = []
    if sd is None:
        missing.append("sounddevice")
    if missing:
        pkg_list = " ".join(missing)
        raise RuntimeError(
            "Missing dependencies: "
            f"{', '.join(missing)}.\\n"
            "Install them with: uv pip install "
            f"{pkg_list}"
        )


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)

    with io.BytesIO() as buff:
        with wave.open(buff, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        return buff.getvalue()


def _normalize_voice_audio(audio: np.ndarray, peak: float) -> np.ndarray:
    if peak < 0.001 or peak >= 0.18:
        return audio
    gain = min(18.0, 0.35 / max(peak, 0.001))
    _set_status("GAIN", f"auto voice gain x{gain:.1f}")
    return np.clip(audio * gain, -1.0, 1.0)


def _input_sample_rate(cfg: VoiceConfig) -> int:
    if cfg.input_device is None or sd is None:
        return cfg.sample_rate
    try:
        device = sd.query_devices(cfg.input_device)
        return int(device.get("default_samplerate") or cfg.sample_rate)
    except Exception:
        return cfg.sample_rate


def _input_channels(cfg: VoiceConfig) -> int:
    if cfg.input_device is None or sd is None:
        return 1
    try:
        device = sd.query_devices(cfg.input_device)
        return max(1, min(2, int(device.get("max_input_channels") or 1)))
    except Exception:
        return 1


def _to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1 or data.shape[1] == 1:
        return data.reshape(-1).copy()
    peaks = np.max(np.abs(data), axis=0)
    channel = int(np.argmax(peaks))
    return data[:, channel].copy()


def _audio_level(audio: np.ndarray) -> tuple[float, float]:
    if not audio.size:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak = float(np.max(np.abs(audio)))
    return rms, peak


def _hotkey_parts(hotkey: str) -> tuple[int, int]:
    hk = hotkey.lower()
    if hk == "ctrl+alt+j":
        return MOD_CONTROL | MOD_ALT, ord("J")
    if hk == "ctrl+shift+q":
        return MOD_CONTROL | 0x0004, ord("Q")
    if hk == "ctrl+shift+x":
        return MOD_CONTROL | 0x0004, ord("X")
    raise ValueError(
        "Unsupported hotkey "
        f"'{hotkey}'. Use ctrl+alt+j, ctrl+shift+x or ctrl+shift+q."
    )


def _is_main_hotkey_pressed(cfg: VoiceConfig) -> bool:
    # Currently we only support ctrl+alt+j for push-to-talk hold detection.
    _, vk = _hotkey_parts(cfg.hotkey)
    ctrl = bool(user32.GetAsyncKeyState(0x11) & 0x8000)  # VK_CONTROL
    alt = bool(user32.GetAsyncKeyState(0x12) & 0x8000)  # VK_MENU
    key = bool(user32.GetAsyncKeyState(vk) & 0x8000)
    return ctrl and alt and key


def _record_wav_bytes(cfg: VoiceConfig) -> bytes:
    sr = _input_sample_rate(cfg)
    channels = _input_channels(cfg)
    blocksize = int(sr * 0.05)  # 50ms
    min_blocks = max(1, int((cfg.min_seconds * sr) / blocksize))
    max_blocks = max(1, int((cfg.max_seconds * sr) / blocksize))

    _set_status("LISTENING", "recording while hotkey is held")
    chunks: list[np.ndarray] = []

    try:
        stream_ctx = sd.InputStream(
            samplerate=sr,
            channels=channels,
            dtype="float32",
            blocksize=blocksize,
            device=cfg.input_device,
        )
        with stream_ctx as stream:
            for i in range(max_blocks):
                data, overflowed = stream.read(blocksize)
                if overflowed:
                    _set_status("WARN", "audio overflow detected")
                mono = _to_mono(data)
                rms, peak = _audio_level(mono)
                _set_mic_level(rms, peak)
                chunks.append(mono)

                if i + 1 >= min_blocks and not _is_main_hotkey_pressed(cfg):
                    break
    except Exception as exc:
        if cfg.input_device is not None:
            _set_status("WARN", f"mic device {cfg.input_device} failed ({exc}); retrying with system default")
            with sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                device=None,
            ) as stream:
                for i in range(max_blocks):
                    data, overflowed = stream.read(blocksize)
                    if overflowed:
                        _set_status("WARN", "audio overflow detected")
                    mono = data[:, 0].copy()
                    rms, peak = _audio_level(mono)
                    _set_mic_level(rms, peak)
                    chunks.append(mono)
                    if i + 1 >= min_blocks and not _is_main_hotkey_pressed(cfg):
                        break
        else:
            raise

    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")
    rms, peak = _audio_level(audio)
    _set_mic_level(rms, peak)
    if peak < 0.005:
        _set_status("WARN", "very low mic signal (check selected input device)")
    audio = _normalize_voice_audio(audio, peak)
    return _audio_to_wav_bytes(audio, sr)


def _record_fixed_wav_bytes(cfg: VoiceConfig, seconds: float) -> bytes:
    sr = _input_sample_rate(cfg)
    channels = _input_channels(cfg)
    blocksize = int(sr * 0.05)
    total_blocks = max(1, int((seconds * sr) / blocksize))
    chunks: list[np.ndarray] = []
    try:
        with sd.InputStream(
            samplerate=sr,
            channels=channels,
            dtype="float32",
            blocksize=blocksize,
            device=cfg.input_device,
        ) as stream:
            for _ in range(total_blocks):
                data, _ = stream.read(blocksize)
                mono = _to_mono(data)
                rms, peak = _audio_level(mono)
                _set_mic_level(rms, peak)
                chunks.append(mono)
    except Exception as exc:
        if cfg.input_device is not None:
            _set_status("WARN", f"mic device {cfg.input_device} failed ({exc}); retrying with system default")
            with sd.InputStream(
                samplerate=sr,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                device=None,
            ) as stream:
                for _ in range(total_blocks):
                    data, _ = stream.read(blocksize)
                    mono = data[:, 0].copy()
                    rms, peak = _audio_level(mono)
                    _set_mic_level(rms, peak)
                    chunks.append(mono)
        else:
            raise
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")
    rms, peak = _audio_level(audio)
    _set_mic_level(rms, peak)
    audio = _normalize_voice_audio(audio, peak)
    return _audio_to_wav_bytes(audio, sr)


def _emit_voice_event(
    state: str,
    detail: str,
    *,
    voice_provider: str | None = None,
    voice_profile: str | None = None,
    ttfs_ms: float | None = None,
    total_synthesis_ms: float | None = None,
) -> None:
    ui = _voice_ui
    if ui is not None:
        ui.emit(
            VoiceUiEvent(
                state=state,
                detail=detail,
                voice_provider=voice_provider,
                voice_profile=voice_profile,
                ttfs_ms=ttfs_ms,
                total_synthesis_ms=total_synthesis_ms,
            )
        )
        return
    _set_status(state, detail)


def _speech_cfg_value(speech_cfg, name: str, default):
    return getattr(speech_cfg, name, default) if speech_cfg is not None else default


def _tts_streaming_enabled(speech_cfg) -> bool:
    return bool(
        _speech_cfg_value(
            speech_cfg,
            "tts_streaming_enabled",
            _speech_cfg_value(speech_cfg, "tts_incremental_enabled", False),
        )
    )


def _decode_wav_audio(result: TTSResult) -> tuple[np.ndarray, int]:
    with io.BytesIO(result.audio) as buff:
        with wave.open(buff, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            sample_rate = int(wf.getframerate() or result.sample_rate or 24000)
            channels = max(1, int(wf.getnchannels()))
            sample_width = int(wf.getsampwidth())

    if sample_width == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype=np.float32).astype(np.float32)
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {sample_width}")

    if channels > 1:
        audio = audio.reshape(-1, channels)
    return audio, sample_rate


def _smooth_tts_chunk(audio: np.ndarray, sample_rate: int, fade_ms: float = 8.0) -> np.ndarray:
    fade_samples = int(sample_rate * (fade_ms / 1000.0))
    if fade_samples <= 0:
        return audio
    frame_count = audio.shape[0] if audio.ndim > 1 else len(audio)
    if frame_count < fade_samples * 2:
        return audio

    fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
    fade_out = fade_in[::-1]
    smoothed = np.array(audio, copy=True)
    if smoothed.ndim == 1:
        smoothed[:fade_samples] *= fade_in
        smoothed[-fade_samples:] *= fade_out
    else:
        smoothed[:fade_samples, :] *= fade_in[:, np.newaxis]
        smoothed[-fade_samples:, :] *= fade_out[:, np.newaxis]
    return smoothed


def _play_tts_result(result: TTSResult, stop_event: threading.Event | None = None) -> None:
    if stop_event is not None and stop_event.is_set():
        return
    if result.format.lower() != "wav":
        raise RuntimeError(f"Unsupported playback format: {result.format}")
    audio, sample_rate = _decode_wav_audio(result)
    audio = _smooth_tts_chunk(audio, sample_rate)
    if stop_event is not None and stop_event.is_set():
        return
    if sd is not None and hasattr(sd, "play"):
        sd.play(audio, sample_rate, blocking=True)
        return
    winsound.PlaySound(result.audio, winsound.SND_MEMORY)


def _legacy_speak_windows(text: str) -> None:
    safe = text.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.Speak('{safe}')"
    )
    proc = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    with _tts_lock:
        global _tts_process
        _tts_process = proc
    try:
        proc.wait()
    finally:
        with _tts_lock:
            if _tts_process is proc:
                _tts_process = None


def _speak_windows(text: str, config=None) -> None:
    cfg = config or load_config()
    speech_cfg = getattr(cfg, "speech", None)
    streaming_enabled = _tts_streaming_enabled(speech_cfg)
    chunk_chars = max(1, int(_speech_cfg_value(speech_cfg, "tts_chunk_chars", 220) or 220))
    interrupt_cancellation_enabled = bool(
        _speech_cfg_value(speech_cfg, "tts_interrupt_cancellation_enabled", False)
    )

    try:
        handle = _TtsPlaybackHandle(
            cancel_token=TTSCancelToken(),
            stop_event=threading.Event(),
            interrupt_cancellation_enabled=interrupt_cancellation_enabled,
        )
        selection = resolve_voice_selection(cfg)
        _emit_voice_event(
            "SYNTHESIZING",
            "building audio",
            voice_provider=selection.provider,
            voice_profile=selection.voice_profile,
        )
        started_at = time.perf_counter()
        with _tts_lock:
            global _tts_process
            _tts_process = handle

        execution = synthesize_with_fallback(
            text,
            config=cfg,
            incremental=streaming_enabled,
            max_chunk_chars=chunk_chars,
            cancel_token=handle.cancel_token,
            output_format="wav",
        )
        ttfs_ms = execution.metrics.get("ttfs_ms")

        for result in execution.results:
            if handle.stop_event.is_set():
                break
            if ttfs_ms is not None:
                _emit_voice_event(
                    "SPEAKING",
                    "playing synthesized audio",
                    voice_provider=execution.selection.provider,
                    voice_profile=execution.selection.voice_profile,
                    ttfs_ms=ttfs_ms,
                )
                ttfs_ms = None
            _play_tts_result(result, handle.stop_event)

        total_synthesis_ms = execution.metrics.get("total_synthesis_ms")
        if total_synthesis_ms is None:
            total_synthesis_ms = (time.perf_counter() - started_at) * 1000.0
        _emit_voice_event(
            "SYNTHESIZING",
            "tts metrics",
            voice_provider=execution.selection.provider,
            voice_profile=execution.selection.voice_profile,
            ttfs_ms=execution.metrics.get("ttfs_ms"),
            total_synthesis_ms=total_synthesis_ms,
        )
        _set_status(
            "TTS",
            (
                f"tts.time_to_first_sound_ms={execution.metrics.get('ttfs_ms') or 0.0:.1f} "
                f"tts.total_synthesis_ms={total_synthesis_ms:.1f}"
            ),
        )
    except Exception as exc:
        _set_status("WARN", f"tts backend path failed ({exc}); using Windows fallback")
        _emit_voice_event("SPEAKING", "windows tts fallback")
        _legacy_speak_windows(text)
    finally:
        with _tts_lock:
            if isinstance(_tts_process, _TtsPlaybackHandle):
                _tts_process = None


def _stop_speaking() -> None:
    with _tts_lock:
        proc = _tts_process
    if proc is None:
        _set_status("SPEAK", "nothing to stop")
        return
    stopped = False
    try:
        if isinstance(proc, _TtsPlaybackHandle):
            proc.stop_event.set()
            if proc.interrupt_cancellation_enabled:
                proc.cancel_token.cancel()
            stopped = True
        if sd is not None and hasattr(sd, "stop"):
            sd.stop()
            stopped = True
        winsound.PlaySound(None, 0)
        if hasattr(proc, "terminate"):
            proc.terminate()
            stopped = True
        if stopped:
            _set_status("INTERRUPTED", "speech interrupted")
        else:
            _set_status("WARN", "speech stop requested but no active output hook found")
    except Exception as exc:
        _set_status("ERROR", f"could not stop speech: {exc}")


def _register_hotkey(hotkey: str, hotkey_id: int) -> bool:
    modifiers, vk = _hotkey_parts(hotkey)
    return bool(user32.RegisterHotKey(None, hotkey_id, modifiers, vk))


def _message_loop(cfg: VoiceConfig, lock: threading.Lock) -> None:
    if not _register_hotkey(cfg.hotkey, HOTKEY_ID):
        raise RuntimeError(f"Could not register hotkey: {cfg.hotkey}")
    if not _register_hotkey("ctrl+shift+q", EXIT_HOTKEY_ID):
        raise RuntimeError("Could not register exit hotkey: ctrl+shift+q")
    if not _register_hotkey("ctrl+shift+x", STOP_SPEAK_HOTKEY_ID):
        raise RuntimeError("Could not register speech-stop hotkey: ctrl+shift+x")

    msg = wintypes.MSG()
    try:
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0:
                break
            if result == -1:
                raise ctypes.WinError()
            if msg.message == WM_HOTKEY:
                if msg.wParam == EXIT_HOTKEY_ID:
                    if cfg.continuous_mode_enabled:
                        _stop_continuous_mode()
                    break
                if msg.wParam == STOP_SPEAK_HOTKEY_ID:
                    _stop_speaking()
                    continue
                if msg.wParam == HOTKEY_ID:
                    # Windows repeats WM_HOTKEY while keys are held.
                    # Debounce so push-to-talk starts only once per press.
                    if not _main_hotkey_debounced():
                        continue
                    if cfg.continuous_mode_enabled:
                        _start_continuous_mode(cfg, lock)
                        continue
                    # Natural barge-in: press the main hotkey while speaking.
                    with _tts_lock:
                        speaking = _tts_process is not None
                    if speaking:
                        _request_barge_in()
                        _set_status("BARGE", "interrupt + listen")
                        _stop_speaking()
                        continue
                    # Ignore extra triggers while current request is active.
                    if lock.locked():
                        continue
                    threading.Thread(
                        target=_handle_once,
                        args=(cfg, lock),
                        daemon=True,
                    ).start()
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        user32.UnregisterHotKey(None, EXIT_HOTKEY_ID)
        user32.UnregisterHotKey(None, STOP_SPEAK_HOTKEY_ID)


def _handle_once(cfg: VoiceConfig, lock: threading.Lock) -> None:
    if not lock.acquire(blocking=False):
        _set_status("BUSY", "previous request still running")
        return

    try:
        winsound.MessageBeep()
        _set_status("HOTKEY", "detected")
        config = load_config()
        stt = _get_stt_backend(config, cfg)
        if stt is None:
            _set_status(
                "ERROR",
                "No speech backend available (run: uv sync --extra speech)",
            )
            return

        audio_bytes = _record_wav_bytes(cfg)
        _set_status("TRANSCRIBING", "speech to text")
        future = _executor.submit(
            stt.transcribe,
            audio_bytes,
            format="wav",
            language=cfg.language,
        )
        try:
            tr = future.result(timeout=20)
        except FutureTimeoutError:
            _set_status("ERROR", "transcription timeout (>20s)")
            return
        text = (tr.text or "").strip()

        if not text:
            _set_status("EMPTY", "no speech recognized")
            return

        _run_turn_from_text(cfg, config, text)
    except Exception as exc:
        _set_status("ERROR", str(exc))

    finally:
        barge = _consume_barge_in()
        lock.release()
        if barge:
            threading.Thread(
                target=_handle_once,
                args=(cfg, lock),
                daemon=True,
            ).start()


def _run_turn_from_text(cfg: VoiceConfig, config, text: str) -> None:
    _set_status("YOU", text)
    if cfg.pc_tools:
        outcome = handle_pc_command(text)
        if outcome.handled:
            _set_status("TOOL", outcome.status)
            _set_status("JARVIS", outcome.spoken)
            _speak_windows(outcome.spoken, config=config)
            _set_status("READY", "waiting hotkey")
            return

    _set_status("THINKING", "querying OpenJarvis")
    if cfg.voice_identity_enabled:
        config.sessions.voice_identity_enabled = True
        config.sessions.voice_local_user_id = cfg.voice_user_id
        config.sessions.voice_local_session_id = cfg.voice_session_id
    with Jarvis(config=config) as jarvis:
        answer = jarvis.ask(
            text,
            agent=cfg.agent,
            context=cfg.memory_context_enabled,
        )
    answer = answer.strip()
    _set_status("JARVIS", answer)
    _speak_windows(answer, config=config)
    _set_status("READY", "waiting hotkey")


def _start_continuous_mode(cfg: VoiceConfig, lock: threading.Lock) -> None:
    global _continuous_thread
    if _continuous_thread is not None and _continuous_thread.is_alive():
        _set_status("CONTINUOUS", "already running")
        return
    _continuous_stop_event.clear()
    _continuous_thread = threading.Thread(
        target=_continuous_loop,
        args=(cfg, lock, _continuous_stop_event),
        daemon=True,
    )
    _continuous_thread.start()
    _set_status("CONTINUOUS", f"enabled (wake word: {cfg.wake_word})")


def _stop_continuous_mode() -> None:
    _continuous_stop_event.set()
    _set_status("CONTINUOUS", "stopping")


def _continuous_loop(cfg: VoiceConfig, lock: threading.Lock, stop_event: threading.Event) -> None:
    config = load_config()
    stt = _get_stt_backend(config, cfg)
    if stt is None:
        _set_status("ERROR", "No speech backend available for continuous mode")
        return
    session = RealtimeVoiceSession(RealtimeSessionConfig(wake_word=cfg.wake_word))
    _set_status("LISTENING", "continuous mode active")
    while not stop_event.is_set():
        try:
            audio_bytes = _record_fixed_wav_bytes(cfg, 1.2)
            tr = stt.transcribe(audio_bytes, format="wav", language=cfg.language)
            text = (tr.text or "").strip()
            if not text:
                continue

            with _tts_lock:
                speaking = _tts_process is not None
            if speaking and cfg.barge_in_enabled:
                should_barge, _ = session.consume(text)
                if should_barge:
                    _set_status("BARGE", "wake word detected during speech")
                    _stop_speaking()
                    continue

            should_process, cleaned = session.consume(text)
            if not should_process or not cleaned:
                continue
            if lock.locked() or not lock.acquire(blocking=False):
                continue
            try:
                _run_turn_from_text(cfg, config, cleaned)
            finally:
                lock.release()
        except Exception as exc:
            _set_status("WARN", f"continuous loop: {exc}")
            time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push-to-talk hotkey for local OpenJarvis on Windows"
    )
    parser.add_argument("--hotkey", default="ctrl+alt+j", help="Global hotkey")
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=90.0,
        help="Safety cap for capture duration",
    )
    parser.add_argument(
        "--min-seconds",
        type=float,
        default=0.25,
        help="Minimum capture before release is allowed",
    )
    parser.add_argument("--sample-rate", type=int, default=16000, help="Mic sample rate")
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        help="Input device index from sounddevice (default: system input)",
    )
    parser.add_argument("--language", default="es", help="STT language (es/en/auto)")
    parser.add_argument(
        "--stt-model",
        default="tiny",
        help="faster-whisper model size (tiny/base/small/...)",
    )
    parser.add_argument(
        "--agent",
        default="orchestrator",
        help="OpenJarvis agent to use (empty for direct model)",
    )
    parser.add_argument(
        "--no-pc-tools",
        action="store_true",
        help="Disable fast local PC commands before asking OpenJarvis",
    )
    parser.add_argument(
        "--continuous-mode",
        action="store_true",
        help="Enable wake-word based continuous conversation mode",
    )
    parser.add_argument(
        "--wake-word",
        default="",
        help="Wake word for continuous mode",
    )
    parser.add_argument(
        "--disable-barge-in",
        action="store_true",
        help="Disable barge-in interruption in continuous mode",
    )
    parser.add_argument(
        "--live-ui",
        action="store_true",
        help="Enable event-driven terminal UI",
    )
    parser.add_argument(
        "--plain-ui",
        action="store_true",
        help="Force plain text terminal UI fallback",
    )
    parser.add_argument(
        "--theme",
        choices=("hacker", "plain"),
        default="hacker",
        help="Terminal UI theme",
    )
    args = parser.parse_args()

    _assert_dependencies()

    lang = None if args.language in {"", "auto"} else args.language
    agent = None if args.agent.strip() == "" else args.agent.strip()
    app_cfg = load_config()
    speech_cfg = app_cfg.speech

    cfg = VoiceConfig(
        hotkey=args.hotkey,
        sample_rate=args.sample_rate,
        max_seconds=args.max_seconds,
        min_seconds=args.min_seconds,
        language=lang,
        agent=agent,
        stt_model=args.stt_model,
        pc_tools=not args.no_pc_tools,
        continuous_mode_enabled=args.continuous_mode or speech_cfg.continuous_mode_enabled,
        wake_word=(args.wake_word or speech_cfg.wake_word or "jarvis").strip(),
        barge_in_enabled=(not args.disable_barge_in) and speech_cfg.barge_in_enabled,
        memory_context_enabled=speech_cfg.memory_context_enabled,
        voice_identity_enabled=app_cfg.sessions.voice_identity_enabled,
        voice_user_id=app_cfg.sessions.voice_local_user_id,
        voice_session_id=app_cfg.sessions.voice_local_session_id or "voice-local-session",
        input_device=getattr(args, "input_device", None),
    )

    lock = threading.Lock()
    global _voice_ui
    if args.live_ui:
        ui_mode = "plain" if args.plain_ui else "rich"
        _voice_ui = TerminalVoiceUI(mode=ui_mode, theme=args.theme)
        _voice_ui.start()

    try:
        _set_status("START", "OpenJarvis push-to-talk started")
        _set_status("HOTKEY", cfg.hotkey)
        _set_status("STOP", "Ctrl+Shift+X (interrupt speech)")
        _set_status("EXIT", "Ctrl+Shift+Q")
        _set_status("STT", f"faster-whisper:{cfg.stt_model}")
        try:
            default_in = sd.default.device[0] if sd is not None else None
            chosen = cfg.input_device if cfg.input_device is not None else default_in
            name = sd.query_devices(chosen)["name"] if sd is not None and chosen is not None else "unknown"
            _set_status(
                "MIC",
                f"input_device={chosen} channels={_input_channels(cfg)} sr={_input_sample_rate(cfg)} ({name})",
            )
        except Exception as exc:
            _set_status("WARN", f"mic device info unavailable: {exc}")
        _set_status("TOOLS", "PC commands enabled" if cfg.pc_tools else "disabled")
        _set_status("MODE", "continuous" if cfg.continuous_mode_enabled else "push-to-talk")
        try:
            with Jarvis(config=load_config()) as jarvis:
                models = jarvis.list_models()
            if not models:
                _set_status(
                    "WARN",
                    "no local models detected (responses may fail)",
                )
        except Exception as exc:
            _set_status("WARN", f"engine preflight failed: {exc}")

        # Warm-up once to avoid first-request latency spike.
        try:
            t0 = time.perf_counter()
            with Jarvis(config=load_config()) as jarvis:
                _ = jarvis.ask("Di ok", agent=cfg.agent)
            _set_status("WARMUP", f"jarvis ready in {time.perf_counter() - t0:.1f}s")
        except Exception as exc:
            _set_status("WARN", f"warmup failed: {exc}")

        _set_status("READY", "waiting hotkey")
        if cfg.continuous_mode_enabled:
            _start_continuous_mode(cfg, lock)

        try:
            _message_loop(cfg, lock)
        except KeyboardInterrupt:
            pass

        _set_status("STOP", "bye")
    finally:
        if _voice_ui is not None:
            _voice_ui.stop()
            _voice_ui = None


if __name__ == "__main__":
    main()
