from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import TextIO

from .terminal_theme import get_terminal_theme


@dataclass(frozen=True)
class VoiceUiEvent:
    state: str
    detail: str = ""
    level: str = "info"
    text_partial: str | None = None
    text_final: str | None = None
    latency_ms: float | None = None
    voice_provider: str | None = None
    voice_profile: str | None = None
    ttfs_ms: float | None = None
    total_synthesis_ms: float | None = None
    mic_rms: float | None = None
    mic_peak: float | None = None
    ts: datetime = field(default_factory=datetime.now)


class TerminalVoiceUI:
    def __init__(
        self,
        *,
        mode: str = "plain",
        theme: str = "hacker",
        output: TextIO | None = None,
        max_events: int = 200,
    ) -> None:
        self._mode = mode
        self._theme = get_terminal_theme(theme)
        self._output = output
        self._max_events = max_events
        self._events: list[VoiceUiEvent] = []
        self._queue: Queue[VoiceUiEvent] = Queue()
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._rich = None
        self._live = None
        self._last_state = "READY"
        self._last_detail = "waiting input"
        self._last_you = ""
        self._last_jarvis = ""
        self._last_latency_ms: float | None = None
        self._last_voice_provider: str | None = None
        self._last_voice_profile: str | None = None
        self._last_ttfs_ms: float | None = None
        self._last_total_synthesis_ms: float | None = None
        self._last_mic_rms: float = 0.0
        self._last_mic_peak: float = 0.0
        self._started_at = datetime.now()
        self._pulse_tick = 0
        self._last_live_refresh = 0.0
        self._live_refresh_interval_s = 0.10

        if self._mode == "rich":
            try:
                from rich.console import Console
                from rich.live import Live

                self._rich = Console(file=output)
                self._live = Live(
                    self._build_layout(),
                    console=self._rich,
                    refresh_per_second=8,
                    transient=False,
                )
            except Exception:
                self._mode = "plain"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def events(self) -> list[VoiceUiEvent]:
        with self._lock:
            return list(self._events)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        if self._mode == "rich" and self._live is not None:
            self._live.start()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._mode == "rich" and self._live is not None:
            self._live.stop()

    def emit(self, event: VoiceUiEvent) -> None:
        self._queue.put(event)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=0.1)
            except Empty:
                continue
            self._render(event)
            self._queue.task_done()

    def _render(self, event: VoiceUiEvent) -> None:
        with self._lock:
            # Keep MIC telemetry out of scrolling history to avoid noisy redraw churn.
            if event.state.upper() != "MIC":
                self._events.append(event)
                if len(self._events) > self._max_events:
                    self._events = self._events[-self._max_events :]
        if self._mode == "rich" and self._rich is not None:
            self._update_live_state(event)
            now = time.monotonic()
            should_refresh = (
                event.state.upper() != "MIC"
                or (now - self._last_live_refresh) >= self._live_refresh_interval_s
            )
            if self._live is not None and should_refresh:
                self._live.update(self._build_layout())
                self._last_live_refresh = now
            return
        print(_format_event(event), file=self._output, flush=True)

    def _update_live_state(self, event: VoiceUiEvent) -> None:
        state = event.state.upper()
        # MIC is a high-frequency signal event; keep semantic state stable.
        if state != "MIC":
            self._last_state = state
        if event.detail:
            self._last_detail = event.detail
        if state == "YOU" and event.detail:
            self._last_you = event.detail
        if state == "JARVIS" and event.detail:
            self._last_jarvis = event.detail
        if event.text_partial:
            self._last_you = event.text_partial
        if event.text_final:
            self._last_jarvis = event.text_final
        if event.latency_ms is not None:
            self._last_latency_ms = event.latency_ms
            if event.total_synthesis_ms is None:
                self._last_total_synthesis_ms = event.latency_ms
        if event.voice_provider:
            self._last_voice_provider = event.voice_provider
        if event.voice_profile:
            self._last_voice_profile = event.voice_profile
        if event.ttfs_ms is not None:
            self._last_ttfs_ms = event.ttfs_ms
        if event.total_synthesis_ms is not None:
            self._last_total_synthesis_ms = event.total_synthesis_ms
        if event.mic_rms is not None:
            self._last_mic_rms = event.mic_rms
        if event.mic_peak is not None:
            self._last_mic_peak = event.mic_peak
        self._pulse_tick = (self._pulse_tick + 1) % 10000

    def _state_style(self, state: str) -> str:
        if state in {"LISTENING", "HOTKEY", "READY"}:
            return self._theme.state_listening
        if state in {"THINKING", "TRANSCRIBING", "SYNTHESIZING"}:
            return self._theme.state_thinking
        if state in {"SPEAKING", "JARVIS"}:
            return self._theme.state_speaking
        if state in {"INTERRUPTED"}:
            return self._theme.warning
        if state in {"ERROR"}:
            return self._theme.error
        if state in {"WARN", "WARNING"}:
            return self._theme.warning
        return self._theme.state_idle

    def _build_layout(self):
        from rich.columns import Columns
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        uptime = datetime.now() - self._started_at
        mm = int(uptime.total_seconds() // 60)
        ss = int(uptime.total_seconds() % 60)
        header = Text("OPENJARVIS // COGNITIVE CORE", style=self._theme.title)
        sub = Text(f"UPTIME {mm:02d}:{ss:02d}", style=self._theme.muted)

        state_txt = Text(self._last_state, style=self._state_style(self._last_state))
        detail_txt = Text(self._last_detail, style=self._theme.muted)
        lat_txt = Text(
            f"{self._last_latency_ms:.1f} ms" if self._last_latency_ms is not None else "--",
            style=self._theme.accent,
        )
        timing_txt = Text(self._format_timing_status(), style=self._theme.accent)
        mic_txt = Text(_meter(self._last_mic_peak), style=self._theme.state_listening)
        provider_txt = Text(self._last_voice_provider or "--", style=self._theme.accent)
        profile_txt = Text(self._last_voice_profile or "--", style=self._theme.accent)

        stat = Table.grid(expand=True)
        stat.add_column(justify="left")
        stat.add_column(justify="left")
        stat.add_row("State", state_txt)
        stat.add_row("Detail", detail_txt)
        stat.add_row("Provider", provider_txt)
        stat.add_row("Profile", profile_txt)
        stat.add_row("Timing", timing_txt)
        stat.add_row("Latency", lat_txt)
        stat.add_row("Mic", mic_txt)

        you = Text(self._last_you or "Waiting for your voice...", style=self._theme.accent)
        jarvis = Text(self._last_jarvis or "...", style=self._theme.state_speaking)

        history = Table.grid(expand=True)
        history.add_column(width=10, style=self._theme.muted)
        history.add_column(ratio=1)
        for e in self.events[-8:]:
            style = self._theme.accent
            if e.level == "warning":
                style = self._theme.warning
            elif e.level == "error":
                style = self._theme.error
            history.add_row(e.ts.strftime("%H:%M:%S"), Text(f"[{e.state}] {e.detail}", style=style))

        core_visual = self._render_core()
        core_meta = self._render_core_meta()
        core = Columns([core_visual, core_meta], expand=True, equal=True)
        left = Panel.fit(
            Columns([header, sub], expand=True),
            title="System",
            border_style=self._theme.panel,
        )
        center = Panel(
            core,
            title="JARVIS CORE",
            border_style=self._theme.panel,
        )
        right = Panel(
            stat,
            title="Realtime Status",
            border_style=self._theme.panel,
        )
        log_panel = Panel(
            history,
            title="Telemetry Log",
            border_style=self._theme.panel,
        )
        top = Columns([left, center, right, log_panel], expand=True, equal=True)

        transcript = Table.grid(expand=True)
        transcript.add_column(style=self._theme.accent)
        transcript.add_column(ratio=1)
        transcript.add_row("YOU", you)
        transcript.add_row("JARVIS", jarvis)
        bottom = Panel(
            transcript,
            title="Dialogue Channel",
            border_style=self._theme.panel,
            subtitle="Ctrl+Alt+J talk | Ctrl+Shift+X interrupt | Ctrl+Shift+Q exit",
        )

        shell = Table.grid(expand=True)
        shell.add_row(top)
        shell.add_row(bottom)
        return shell

    def _render_core(self):
        from rich.text import Text

        state = self._last_state
        style = self._state_style(state)
        phase = self._pulse_tick % 8

        if state in {"SPEAKING", "JARVIS"}:
            ring = ["   .-@@@@@-.   ", " .@@@*****@@@. ", "@@**@@@.@@@**@@", "@*@@@***@@@**@@"]
        elif state in {"THINKING", "TRANSCRIBING", "SYNTHESIZING"}:
            ring = ["   .-OOOOO-.   ", " .OOO.....OOO. ", "OO..OOO.OOO..OO", "OO.OOO...OOO.OO"]
        elif state in {"LISTENING", "HOTKEY", "READY"}:
            ring = ["   .-ooooo-.   ", " .ooo.....ooo. ", "oo..ooo.ooo..oo", "oo.ooo...ooo.oo"]
        elif state == "INTERRUPTED":
            ring = ["   .-xxxxx-.   ", " .xxx.....xxx. ", "xx..xxx.xxx..xx", "xx.xxx...xxx.xx"]
        else:
            ring = ["   .-=====-.   ", " .===.....===. ", "==..===.===..==", "==.===...===.=="]

        spinner = "|/-\\"
        spin = spinner[phase % len(spinner)]
        pulse_chars = " .oO@"
        pulse = pulse_chars[(phase % len(pulse_chars))]

        lines = [
            Text("      " + spin + "  COGNITIVE LINK  " + spin, style=self._theme.muted),
            Text("        " + pulse * 3, style=style),
            Text(ring[0], style=style),
            Text(ring[1], style=style),
            Text(ring[2], style=style),
            Text(ring[3], style=style),
            Text(ring[2], style=style),
            Text(ring[1], style=style),
            Text(ring[0], style=style),
            Text("        " + pulse * 3, style=style),
            Text("   MIC " + _meter(self._last_mic_peak), style=self._theme.state_listening),
            Text(f"      STATE: {state}", style=style),
        ]

        block = Text()
        for i, ln in enumerate(lines):
            block.append_text(ln)
            if i != len(lines) - 1:
                block.append("\n")
        return block

    def _render_core_meta(self):
        from rich.table import Table
        from rich.text import Text

        table = Table.grid(expand=True)
        table.add_column(style=self._theme.muted, width=14)
        table.add_column(style=self._theme.accent)

        table.add_row("PROVIDER", Text(self._last_voice_provider or "--", style=self._theme.accent))
        table.add_row("PROFILE", Text(self._last_voice_profile or "--", style=self._theme.accent))
        table.add_row("CHANNEL", Text("VOICE LINK ACTIVE", style=self._theme.state_listening))
        table.add_row("MODE", Text(self._last_state, style=self._state_style(self._last_state)))
        table.add_row("TTFS", Text(
            f"{self._last_ttfs_ms:.1f} ms" if self._last_ttfs_ms is not None else "--",
            style=self._theme.accent,
        ))
        table.add_row("SYNTH", Text(
            f"{self._last_total_synthesis_ms:.1f} ms"
            if self._last_total_synthesis_ms is not None
            else "--",
            style=self._theme.accent,
        ))
        table.add_row("LATENCY", Text(
            f"{self._last_latency_ms:.1f} ms" if self._last_latency_ms is not None else "--",
            style=self._theme.accent,
        ))
        table.add_row("MIC RMS", Text(f"{self._last_mic_rms:.5f}", style=self._theme.state_listening))
        table.add_row("MIC PEAK", Text(f"{self._last_mic_peak:.5f}", style=self._theme.state_listening))
        table.add_row("SIGNAL", Text(_meter(self._last_mic_peak), style=self._theme.state_listening))
        table.add_row("INPUT", Text(self._last_you or "(awaiting speech)", style="bold bright_cyan"))
        table.add_row("OUTPUT", Text(self._last_jarvis or "(standby)", style="bold magenta"))
        table.add_row("HOTKEY", Text("Ctrl+Alt+J", style=self._theme.accent))
        table.add_row("STOP", Text("Ctrl+Shift+X", style=self._theme.warning))
        table.add_row("EXIT", Text("Ctrl+Shift+Q", style=self._theme.error))
        return table

    def _format_timing_status(self) -> str:
        ttfs = f"TTFS {self._last_ttfs_ms:.1f} ms" if self._last_ttfs_ms is not None else "TTFS --"
        total = (
            f"TOTAL {self._last_total_synthesis_ms:.1f} ms"
            if self._last_total_synthesis_ms is not None
            else "TOTAL --"
        )
        return f"{ttfs} | {total}"


def _format_event(event: VoiceUiEvent) -> str:
    ts = event.ts.strftime("%H:%M:%S")
    parts = [f"[{ts}] [{event.state}]"]
    if event.detail:
        parts.append(event.detail)
    if event.text_partial:
        parts.append(f"partial={event.text_partial}")
    if event.text_final:
        parts.append(f"final={event.text_final}")
    if event.latency_ms is not None:
        parts.append(f"latency={event.latency_ms:.1f}ms")
    if event.voice_provider:
        parts.append(f"provider={event.voice_provider}")
    if event.voice_profile:
        parts.append(f"profile={event.voice_profile}")
    if event.ttfs_ms is not None:
        parts.append(f"ttfs={event.ttfs_ms:.1f}ms")
    total_synthesis_ms = event.total_synthesis_ms
    if total_synthesis_ms is None:
        total_synthesis_ms = event.latency_ms
    if total_synthesis_ms is not None:
        parts.append(f"total_synthesis={total_synthesis_ms:.1f}ms")
    if event.mic_peak is not None:
        parts.append(f"mic_peak={event.mic_peak:.5f}")
    return " ".join(parts).rstrip()


def _meter(level: float, width: int = 18) -> str:
    normalized = max(0.0, min(1.0, level / 0.08))
    active = int(round(normalized * width))
    return "|" * active + "." * (width - active)
