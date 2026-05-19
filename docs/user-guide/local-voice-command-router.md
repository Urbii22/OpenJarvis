# Local Voice Command Router

This guide explains how OpenJarvis routes voice commands locally today, including safety gates and current limitations.

## What It Does Today

The local voice command pipeline runs in this order:

1. Normalize transcript in `src/openjarvis/speech/command_normalizer.py`.
2. Match deterministic intents in `src/openjarvis/speech/command_router.py`.
3. If no local rule matches, optionally try semantic fallback (`Ollama`) in `src/openjarvis/speech/semantic_router.py`.
4. Apply safety policy in `src/openjarvis/speech/command_safety.py`.
5. Execute or hold command in `src/openjarvis/speech/command_executor.py`.

Runtime integration is in:

- `src/openjarvis/speech/voice_runtime.py`
- `src/openjarvis/speech/realtime_session.py`
- Speech websocket route: `src/openjarvis/server/api_routes.py` (`/v1/speech/stream`)

## Enable It

In your `config.toml`:

```toml
[speech]
partial_streaming_enabled = true
semantic_router_ollama_model = "qwen3:4b"
semantic_router_ollama_timeout_s = 3.0
semantic_router_enabled = true
semantic_router_model = "qwen3:4b"
semantic_router_timeout_seconds = 2.5
semantic_router_min_confidence = 0.70
semantic_router_execute_confidence = 0.90
```

Notes:

- `partial_streaming_enabled` must be `true` for `/v1/speech/stream`.
- Semantic fallback uses local Ollama by default (`http://localhost:11434`, or `OLLAMA_HOST` env var).
- If Ollama is down or returns invalid JSON, routing degrades safely to `unknown`.

## Confidence and Safety Thresholds

`src/openjarvis/speech/command_safety.py` enforces:

- `< 0.70`: blocked (`low_confidence`)
- `0.70 - 0.89`: confirmation required
- `>= 0.90`: auto-exec only for low-risk commands

Additional safety:

- Direct execution is blocked for `delete_path`, `move_path`, `copy_path`, `shell_exec`.
- High confidence is still confirmation-gated if risk is not low.

## Supported Intents (Current)

Current route intent schema:

- `app.open`
- `system.volume_up`
- `system.volume_down`
- `system.volume_mute`
- `system.volume_set`
- `media.play_pause`
- `media.next`
- `media.previous`
- `folder.search`
- `folder.open`
- `file.search`
- `unknown`

Important current limitation:

- `app.open` can execute through `open_application`.
- `system.volume_*` and `media.*` are currently controlled stubs (`set_volume_not_supported`, `media_control_not_supported`), so they produce confirmation/stub flows instead of direct device control.

## Voice Shell and WebSocket Events

`/v1/speech/stream` emits both STT and router/runtime events:

- STT: `partial_text`, `final_text`, `error`, `interrupted`
- Runtime: `recognition`, `confirmation`, `execution`, `unknown`, `error`

The Voice Shell frontend consumes these events (including route metadata) from:

- `frontend/src/lib/api.ts`
- `frontend/src/components/voice-shell/state.ts`

## Benchmark

A dedicated benchmark script now exists:

- `scripts/benchmark_voice_command_router.py`
- `docs/bench/voice_command_router/README.md`

Example:

```bash
python scripts/benchmark_voice_command_router.py --mock --runs 20
```

Use `--mode real` to include the live Ollama semantic router when available.

## Known Limits

- Semantic routing is fallback-only; deterministic rules run first.
- Semantic routing accepts only the existing intent set above.
- There is no native OS volume/media executor yet.
