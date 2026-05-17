# Plan de Implementacion: Router Semantico Local de Voz

## Contexto

Quiero implementar en OpenJarvis un sistema local de comprension de comandos de voz que convierta transcripciones imperfectas en acciones estructuradas y seguras.

La arquitectura objetivo es:

```text
Audio del usuario
-> STT local: faster-whisper
-> Transcripcion imperfecta
-> Normalizador local
-> Router hibrido
   -> reglas locales rapidas
   -> router semantico local con Ollama/qwen3:4b
-> CommandRouteResult JSON
-> Politica de confianza y confirmacion
-> CommandExecutor
-> Tools locales de OpenJarvis
-> Feedback por TTS + Voice Shell
```

## Objetivo

Construir un pipeline local-first para voz que:

1. Normalice transcripciones imperfectas.
2. Resuelva comandos obvios con reglas locales deterministas.
3. Use un router semantico local solo cuando haga falta.
4. Aplique una politica clara de confianza, confirmacion y bloqueo.
5. Ejecute solo acciones seguras.
6. Muestre en la Voice Shell lo que Jarvis entendio.
7. Incluya benchmark y documentacion.

## Principios

- No usar llamadas reales a Ollama en tests unitarios.
- No tocar frontend hasta que el backend este estable.
- No ejecutar acciones peligrosas sin confirmacion.
- Mantener cambios pequenos y modulares.
- Cada subagente debe tener una responsabilidad y un conjunto de archivos propios.

## Plan Por Fases

### Fase 0. Preparacion y contratos

Responsable: agente principal

Tareas:

- Inspeccionar la estructura actual de `src/openjarvis/speech/`, `tools/`, `core/config.py`, `voice_runtime.py` y `realtime_session.py`.
- Crear una rama de trabajo nueva.
- Definir el contrato comun:
  - `CommandRouteResult`
  - intents permitidos
  - umbrales de confianza
  - estados de ejecucion
  - politica de confirmacion
- Confirmar que tools reales existen hoy y cuales seran stubs controlados.

Salida esperada:

- Interfaces y limites claros.
- Lista de archivos cerrada.
- Sin ambiguedad entre capas.

### Fase 1. Nucleo de parsing

Responsables: dos subagentes en paralelo

#### 1. `normalizer-agent`

Archivos:

- `src/openjarvis/speech/command_normalizer.py`
- `tests/speech/test_command_normalizer.py`

Trabajo:

- convertir a minusculas
- eliminar tildes
- quitar wake words
- quitar puntuacion innecesaria
- compactar espacios
- no corregir semantica

#### 2. `semantic-schema-agent`

Archivos:

- `src/openjarvis/speech/semantic_router.py`
- `tests/speech/test_semantic_router_schema.py`

Trabajo:

- definir `CommandRouteResult`
- validar intents
- normalizar `confidence`
- asegurar serializacion JSON

Salida esperada:

- Ya existe una base estable para enrutar comandos.
- Los tests de normalizacion y esquema pasan.
- No hay dependencia con Ollama aun.

### Fase 2. Routing inteligente y seguridad

Responsables: dos tandas de subagentes

#### Tanda 1

##### 3. `local-rules-agent`

Archivos:

- `src/openjarvis/speech/command_router.py`
- `tests/speech/test_command_router_local_rules.py`

Trabajo:

- comandos obvios por reglas
- alta confianza
- salida determinista

##### 4. `ollama-router-agent`

Archivos:

- `src/openjarvis/speech/semantic_router.py`
- `src/openjarvis/core/config.py`
- `tests/speech/test_semantic_router_ollama.py`

Trabajo:

- integracion mockeable con Ollama
- configuracion de modelo y timeouts
- fallback limpio cuando Ollama falla

#### Tanda 2

##### 5. `safety-agent`

Archivos:

- `src/openjarvis/speech/command_safety.py`
- `tests/speech/test_command_safety.py`

Trabajo:

- umbrales de ejecucion
- confirmacion obligatoria
- bloqueo de acciones destructivas

##### 6. `executor-agent`

Archivos:

- `src/openjarvis/speech/command_executor.py`
- `tests/speech/test_command_executor.py`

Trabajo:

- mapear intents a tools existentes
- no ejecutar si hay confirmacion pendiente
- usar stubs controlados para acciones sin tool real

Salida esperada:

- Los comandos simples funcionan sin modelo.
- Los comandos ambiguos pasan por el router semantico.
- Las acciones dudosas no se ejecutan solas.
- Los tests siguen sin necesitar Ollama real.

### Fase 3. Integracion en runtime de voz

Responsables: agente principal + subagente de runtime

#### 7. `voice-runtime-agent`

Archivos:

- `src/openjarvis/speech/voice_runtime.py`
- `src/openjarvis/speech/realtime_session.py`
- tests asociados

Trabajo:

- conectar transcripcion final -> normalizador -> router -> safety -> executor
- emitir eventos claros para la UI
- mantener los estados actuales sin romperlos

#### 8. `frontend-voice-shell-agent`

Archivos:

- `frontend/src/components/voice-shell/state.ts`
- `frontend/src/components/voice-shell/VoiceShell.tsx`
- tests de UI

Trabajo:

- mostrar que entendio Jarvis
- mostrar `intent`, `corrected_text`, `confidence`, `confirmation`, `error`
- cambios minimos, sin rediseño

Salida esperada:

- La voz ya no solo escucha, tambien interpreta y decide.
- La UI muestra el resultado del pipeline.
- No se rompen los estados actuales.

### Fase 4. Validacion, benchmark y docs

Responsables: dos subagentes finales

#### 9. `benchmark-agent`

Archivos:

- `scripts/benchmark_voice_command_router.py`
- `docs/bench/voice_command_router/README.md`

Trabajo:

- medir latencia por etapa
- modo mock
- modo real opcional
- salida en tabla simple o JSON

#### 10. `docs-agent`

Archivos:

- `docs/user-guide/local-voice-command-router.md`
- `docs/development/local-semantic-router.md`

Trabajo:

- uso de la funcion
- arquitectura
- umbrales
- ejemplos
- como anadir intents nuevos

Salida esperada:

- Hay forma de medir si el sistema merece la pena.
- Hay documentacion para usarlo y mantenerlo.

## Orden Recomendado De Subagentes

1. `normalizer-agent`
2. `semantic-schema-agent`
3. `local-rules-agent`
4. `ollama-router-agent`
5. `safety-agent`
6. `executor-agent`
7. `voice-runtime-agent`
8. `frontend-voice-shell-agent`
9. `benchmark-agent`
10. `docs-agent`

## Criterios De Aceptacion

El cambio se considera valido si:

- Los comandos obvios funcionan sin modelo.
- Los comandos flexibles pasan por `qwen3:4b`.
- Las transcripciones erraticas razonables se reparan semanticalmente.
- El sistema no ejecuta acciones dudosas.
- Los tests unitarios no requieren Ollama real.
- Existe benchmark de latencia.
- La Voice Shell muestra que entendio Jarvis.
- El sistema sigue siendo local-first.
- El codigo queda modular y mantenible.

## Lo Que Se Pospone

- routing multimodelo complejo
- aprendizaje automatico del router
- prompts muy elaborados
- acciones peligrosas por voz
- refactors grandes del frontend

## Resumen Corto Para Otro Chat

Quiero implementar un router semantico local de voz en OpenJarvis con este orden:

1. normalizador
2. esquema `CommandRouteResult`
3. reglas locales rapidas
4. router semantico local con Ollama mockeable
5. politica de seguridad
6. executor
7. integracion en runtime de voz
8. actualizacion minima de Voice Shell
9. benchmark
10. documentacion

Cada fase debe poder asignarse a subagentes con archivos propios y tests aislados.
