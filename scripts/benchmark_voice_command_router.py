"""Latency benchmark for voice command routing pipeline."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from openjarvis.core.config import SpeechConfig
from openjarvis.core.types import ToolResult
from openjarvis.speech.command_executor import CommandExecutor
from openjarvis.speech.command_normalizer import normalize_command
from openjarvis.speech.command_router import route_command
from openjarvis.speech.semantic_router import (
    CommandRouteResult,
    build_ollama_semantic_router,
)
from openjarvis.speech.voice_runtime import VoiceCommandRuntime

DEFAULT_COMMANDS: tuple[str, ...] = (
    "abre spotify",
    "abre spotifai",
    "sube el volumen",
    "abre el volumen",
    "incrementa el volumen",
    "se oye bajo",
    "baja el volumen",
    "pausa la musica",
    "siguiente cancion",
    "abre la carpeta descargas",
)


@dataclass(frozen=True, slots=True)
class RunSample:
    normalization_ms: float
    local_rules_ms: float
    semantic_ms: float
    executor_ms: float
    total_ms: float
    runtime_total_ms: float


class MockSemanticRouter:
    """Predictable semantic router for safe local benchmarking."""

    def __init__(self, *, latency_ms: float = 12.0) -> None:
        self._latency_s = max(0.0, latency_ms / 1000.0)

    def route(self, command: str) -> CommandRouteResult:
        if self._latency_s > 0:
            time.sleep(self._latency_s)
        if "spotifai" in command:
            target = "spotify"
            confidence = 0.86
            requires_confirmation = True
        elif "volumen" in command or "bajo" in command:
            return CommandRouteResult(
                intent="system.volume_up",
                confidence=0.82,
                corrected_text=command,
                arguments={},
                requires_confirmation=True,
                source="semantic_router",
                allow_execution=False,
            )
        else:
            target = "spotify"
            confidence = 0.96
            requires_confirmation = False
        return CommandRouteResult(
            intent="app.open",
            confidence=confidence,
            corrected_text=command,
            arguments={"target": target},
            requires_confirmation=requires_confirmation,
            source="semantic_router",
            allow_execution=not requires_confirmation,
        )


def _ok_tool(tool_name: str, params: dict[str, object]) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        content=f"ok:{params}",
        success=True,
        latency_seconds=0.0,
    )


def _to_ms(seconds: float) -> float:
    return seconds * 1000.0


def _measure_once(
    transcript: str,
    *,
    semantic_router: object | None,
    executor: CommandExecutor,
    runtime: VoiceCommandRuntime,
) -> RunSample:
    started = time.perf_counter()

    t0 = time.perf_counter()
    normalized = normalize_command(transcript)
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    route = route_command(normalized)
    t3 = time.perf_counter()

    semantic_ms = 0.0
    if route.intent == "unknown" and semantic_router is not None:
        t4 = time.perf_counter()
        semantic_route = semantic_router.route(normalized)
        t5 = time.perf_counter()
        semantic_ms = _to_ms(t5 - t4)
        if semantic_route.intent != "unknown":
            route = semantic_route

    t6 = time.perf_counter()
    executor.execute(route)
    t7 = time.perf_counter()
    finished = time.perf_counter()

    runtime_started = time.perf_counter()
    runtime.process_transcript(transcript)
    runtime_finished = time.perf_counter()

    return RunSample(
        normalization_ms=_to_ms(t1 - t0),
        local_rules_ms=_to_ms(t3 - t2),
        semantic_ms=semantic_ms,
        executor_ms=_to_ms(t7 - t6),
        total_ms=_to_ms(finished - started),
        runtime_total_ms=_to_ms(runtime_finished - runtime_started),
    )


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def _format_row(label: str, values: list[float]) -> str:
    avg = statistics.mean(values) if values else 0.0
    p50 = statistics.median(values) if values else 0.0
    p95 = _p95(values)
    return f"{label:<17} {avg:>9.2f} {p50:>9.2f} {p95:>9.2f}"


def _build_semantic_router(mode: str, model: str, timeout_s: float) -> object | None:
    if mode == "mock":
        return MockSemanticRouter()
    cfg = SpeechConfig(
        semantic_router_ollama_model=model,
        semantic_router_ollama_timeout_s=timeout_s,
    )
    return build_ollama_semantic_router(cfg)


def _print_report(*, mode: str, runs: int, commands: Sequence[str], samples: list[RunSample]) -> None:
    normalization = [s.normalization_ms for s in samples]
    local_rules = [s.local_rules_ms for s in samples]
    semantic = [s.semantic_ms for s in samples]
    executor = [s.executor_ms for s in samples]
    total = [s.total_ms for s in samples]
    runtime_total = [s.runtime_total_ms for s in samples]

    print("Voice Command Router Benchmark")
    print(f"mode={mode} runs={runs} commands={len(commands)} total_samples={len(samples)}")
    print("commands:")
    for cmd in commands:
        print(f"  - {cmd}")
    print("")
    print(f"{'stage':<17} {'avg_ms':>9} {'p50_ms':>9} {'p95_ms':>9}")
    print("-" * 48)
    print(_format_row("normalization", normalization))
    print(_format_row("local_rules", local_rules))
    print(_format_row("semantic/ollama", semantic))
    print(_format_row("executor", executor))
    print(_format_row("total", total))
    print(_format_row("runtime_total", runtime_total))
    print("")
    print("note: runtime_total re-runs process_transcript end-to-end as a parity check.")


def _write_json_report(path: Path, *, mode: str, runs: int, commands: Sequence[str], samples: list[RunSample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode,
        "runs": runs,
        "commands": list(commands),
        "samples": [
            {
                "normalization_ms": sample.normalization_ms,
                "local_rules_ms": sample.local_rules_ms,
                "semantic_ms": sample.semantic_ms,
                "executor_ms": sample.executor_ms,
                "total_ms": sample.total_ms,
                "runtime_total_ms": sample.runtime_total_ms,
            }
            for sample in samples
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark voice command routing latency.")
    parser.add_argument(
        "--mode",
        choices=("mock", "real"),
        default="mock",
        help="mock is deterministic and safe; real uses Ollama semantic router.",
    )
    parser.add_argument("--mock", action="store_true", help="Alias for --mode mock.")
    parser.add_argument("--real", action="store_true", help="Alias for --mode real.")
    parser.add_argument("--runs", type=int, default=20, help="Benchmark repetitions per command.")
    parser.add_argument(
        "--command",
        dest="commands",
        action="append",
        default=[],
        help="Transcript to benchmark. Repeat flag to add more commands.",
    )
    parser.add_argument(
        "--ollama-model",
        default="qwen3:4b",
        help="Used only with --mode real.",
    )
    parser.add_argument("--model", dest="ollama_model", default=argparse.SUPPRESS, help="Alias for --ollama-model.")
    parser.add_argument(
        "--ollama-timeout-s",
        type=float,
        default=3.0,
        help="Used only with --mode real.",
    )
    parser.add_argument("--json", dest="json_path", default="", help="Write raw benchmark samples as JSON.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.mock:
        args.mode = "mock"
    if args.real:
        args.mode = "real"

    runs = max(1, args.runs)
    commands = tuple(args.commands) if args.commands else DEFAULT_COMMANDS
    semantic_router = _build_semantic_router(args.mode, args.ollama_model, args.ollama_timeout_s)

    executor = CommandExecutor(execute_tool=_ok_tool)
    runtime = VoiceCommandRuntime(semantic_router=semantic_router, execute_tool=_ok_tool)

    samples: list[RunSample] = []
    for _ in range(runs):
        for transcript in commands:
            samples.append(
                _measure_once(
                    transcript,
                    semantic_router=semantic_router,
                    executor=executor,
                    runtime=runtime,
                )
            )

    _print_report(mode=args.mode, runs=runs, commands=commands, samples=samples)
    if args.json_path:
        _write_json_report(Path(args.json_path), mode=args.mode, runs=runs, commands=commands, samples=samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
