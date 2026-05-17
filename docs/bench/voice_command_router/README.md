# Voice Command Router Benchmark

Benchmark sencillo de latencia para el pipeline de routing de comandos de voz.

## Qué mide

El script mide estas etapas por muestra:

- `normalization`: `normalize_command()`
- `local_rules`: `route_command()`
- `semantic/ollama`: fallback semántico (`MockSemanticRouter` en mock, `OllamaSemanticRouter` en real)
- `executor`: `CommandExecutor.execute()`
- `total`: suma end-to-end del pipeline medido manualmente
- `runtime_total`: `VoiceCommandRuntime.process_transcript()` completo (parity check)

Salida en tabla con `avg_ms`, `p50_ms`, `p95_ms` para comparar fácil entre corridas.

## Uso

Modo seguro por defecto (`mock`):

```bash
python scripts/benchmark_voice_command_router.py --mock
```

Elegir número de corridas:

```bash
python scripts/benchmark_voice_command_router.py --mock --runs 50
```

Comandos personalizados:

```bash
python scripts/benchmark_voice_command_router.py --mock --command "abre spotify" --command "abre spotifai"
```

Modo real con Ollama (opcional):

```bash
python scripts/benchmark_voice_command_router.py --mode real --model qwen3:4b --json docs/bench/voice_command_router/qwen3_4b_results.json
```

Tambien puedes usar `--mode mock` / `--mode real` si prefieres la forma explicita.

## Notas de contrato

- `mock` es el default para que el benchmark sea reproducible y no dependa de servicios externos.
- En `real`, si Ollama no está disponible, el benchmark no falla: el router semántico degrada a `unknown` y la corrida continúa.
- El benchmark usa un `execute_tool` falso (`ToolResult` exitoso) para no abrir apps reales durante la medición.
