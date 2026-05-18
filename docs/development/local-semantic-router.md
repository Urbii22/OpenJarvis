# Local Semantic Router (Development)

This document describes the current implementation contract for the local semantic voice router and how to extend it safely.

## Architecture (Current Code)

Main modules:

- Normalization: `src/openjarvis/speech/command_normalizer.py`
- Deterministic routing: `src/openjarvis/speech/command_router.py`
- Semantic routing: `src/openjarvis/speech/semantic_router.py`
- Safety policy: `src/openjarvis/speech/command_safety.py`
- Execution adapter: `src/openjarvis/speech/command_executor.py`
- Runtime wiring: `src/openjarvis/speech/voice_runtime.py`
- Wake/follow-up session: `src/openjarvis/speech/realtime_session.py`
- WebSocket bridge endpoint: `src/openjarvis/server/api_routes.py` (`/v1/speech/stream`)

Execution flow:

1. Transcript normalized (`normalize_command`).
2. `route_command` tries local rules first.
3. If `unknown`, `VoiceCommandRuntime` may call semantic router.
4. Safety policy resolves block/confirm/allow.
5. `CommandExecutor` maps intent to tool or stub.
6. Runtime emits structured events for UI/clients.

## Semantic Router Contract

`CommandRouteResult` is the shared typed contract:

- Allowed intents: `app.open`, `system.volume_up`, `system.volume_down`, `system.volume_mute`, `system.volume_set`, `media.play_pause`, `media.next`, `media.previous`, `folder.search`, `folder.open`, `file.search`, `unknown`
- Allowed sources: `local_rule`, `semantic_router`, `unknown`
- Safety downgrade on invalid payloads: force `unknown`, `requires_confirmation=True`, `allow_execution=False`

`OllamaSemanticRouter.route()`:

- Builds strict prompt and requests JSON-only response.
- Handles timeout/network/http/parser failures via safe fallback.
- Fallback error values include:
  - `semantic_router_empty_command`
  - `semantic_router_unavailable`
  - `semantic_router_invalid_json`
  - `semantic_router_invalid_payload`
  - `semantic_router_missing_fields`

## Config Surface

From `SpeechConfig` (`src/openjarvis/core/config.py`):

- `semantic_router_enabled` (default: `true`)
- `semantic_router_model` (default: `qwen3:4b`)
- `semantic_router_timeout_seconds` (default: `2.5`)
- `semantic_router_min_confidence` (default: `0.70`)
- `semantic_router_execute_confidence` (default: `0.90`)

Builder:

- `build_ollama_semantic_router(speech_config, host="", generate=...)`
- Host resolution order:
  1. explicit `host` argument
  2. `OLLAMA_HOST` env var
  3. default `http://localhost:11434`

## Threshold and Safety Policy

From `src/openjarvis/speech/command_safety.py`:

- `LOW_CONFIDENCE_THRESHOLD = 0.70`
- `HIGH_CONFIDENCE_THRESHOLD = 0.90`

Policy contract:

- `< 0.70`: blocked
- `0.70 - 0.89`: confirmation required
- `>= 0.90`: executable only when risk is low and not direct-blocked tool

Direct execution hard-block list:

- `delete_path`
- `move_path`
- `copy_path`
- `shell_exec`

## Current Intent Execution Map

In `CommandExecutor._resolve_action()`:

- `app.open` -> tool `open_application`
- `system.volume_*` -> stub (`set_volume_not_supported`)
- `media.*` -> stub (`media_control_not_supported`)
- `folder.search` / `file.search` -> tool `find_files`
- `folder.open` -> tool `open_path`
- `unknown` -> unknown flow

Do not document or add extra intents unless they are added to `RouteIntent` and fully wired.

## WebSocket / Runtime Integration

`/v1/speech/stream`:

- Accepts `start` / `audio` / `stop` / `interrupt` messages.
- Emits STT messages and, on final text, emits runtime events from `VoiceCommandRuntime`.

Runtime events:

- `recognition`
- `confirmation`
- `execution`
- `unknown`
- `error`

## Extension Points

Safe extension order:

1. Extend local deterministic rules in `command_router.py` when patterns are explicit.
2. Keep semantic router strictly within allowed intent schema.
3. Add/adjust executor mappings in `command_executor.py`.
4. Add/adjust safety classification before enabling auto-exec paths.
5. Update tests first for schema, safety, runtime events, and new mappings.

## Benchmark and Validation (Current State)

Dedicated benchmark assets now exist:

- `scripts/benchmark_voice_command_router.py`
- `docs/bench/voice_command_router/README.md`

The benchmark supports:

- `--mode mock` for deterministic local runs
- `--mode real` for live Ollama fallback measurements when available

Recommended minimal validation:

```bash
PYTHONPATH=src pytest tests/speech/test_command_normalizer.py tests/speech/test_command_router_local_rules.py tests/speech/test_semantic_router_schema.py tests/speech/test_semantic_router_ollama.py tests/speech/test_command_safety.py tests/speech/test_command_executor.py tests/speech/test_voice_runtime_command_router.py tests/speech/test_realtime_session.py
```

For performance benchmarking, add a dedicated benchmark script and dataset before publishing latency/accuracy claims.
