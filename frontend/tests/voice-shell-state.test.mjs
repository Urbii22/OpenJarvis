import assert from 'node:assert/strict';

import {
  DEFAULT_VOICE_SHELL_MODE,
  VOICE_SHELL_FLAG_KEY,
  VOICE_SHELL_MODE_KEY,
  getVoiceStatusVisual,
  isVoiceShellEnabled,
  normalizeVoiceEvent,
  readPersistedShellMode,
} from '../src/components/voice-shell/state.ts';

function storage(seed = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
}

assert.equal(DEFAULT_VOICE_SHELL_MODE, 'compact');

assert.equal(
  isVoiceShellEnabled({ env: { VITE_VOICE_SHELL_ENABLED: 'true' }, storage: storage() }),
  true,
);
assert.equal(
  isVoiceShellEnabled({ env: { VITE_VOICE_SHELL_ENABLED: 'true' }, storage: storage({ [VOICE_SHELL_FLAG_KEY]: 'false' }) }),
  false,
);
assert.equal(
  isVoiceShellEnabled({ env: {}, storage: storage({ [VOICE_SHELL_FLAG_KEY]: '1' }) }),
  true,
);

assert.equal(readPersistedShellMode(storage({ [VOICE_SHELL_MODE_KEY]: 'expanded' })), 'expanded');
assert.equal(readPersistedShellMode(storage({ [VOICE_SHELL_MODE_KEY]: 'legacy' })), 'compact');

assert.deepEqual(normalizeVoiceEvent({ type: 'partial_text', text: 'hola' }).status, 'LISTENING');
assert.deepEqual(normalizeVoiceEvent({ type: 'inference_start' }).status, 'THINKING');
assert.deepEqual(normalizeVoiceEvent({ type: 'tts_start', voice_provider: 'cartesia' }).status, 'SPEAKING');
assert.deepEqual(normalizeVoiceEvent({ type: 'interrupted' }).status, 'INTERRUPTED');
assert.deepEqual(normalizeVoiceEvent({ type: 'error', detail: 'boom' }).status, 'ERROR');
assert.deepEqual(normalizeVoiceEvent({ state: 'ACTIVE' }).status, 'ACTIVE');
assert.deepEqual(normalizeVoiceEvent({ state: 'SYNTHESIZING' }).status, 'THINKING');
assert.deepEqual(normalizeVoiceEvent({ state: 'BARGE', mic_rms: 0.42 }).metrics.micEnergy, 0.42);
assert.equal(normalizeVoiceEvent({ state: 'STT', text_final: 'listo', latency_ms: 123 }).transcript, 'listo');
assert.equal(normalizeVoiceEvent({ state: 'STT', latency_ms: 123 }).metrics.ttfsMs, 123);
assert.equal(
  normalizeVoiceEvent({
    kind: 'recognition',
    payload: {
      transcript: 'abre github',
      normalized: 'abrir github',
      route: { intent: 'app.open', confidence: 0.91 },
    },
  }).status,
  'LISTENING',
);
const runtimeEvent = normalizeVoiceEvent({
  kind: 'execution',
  payload: {
    status: 'completed',
    confirmation_state: 'approved',
    route: { intent: 'app.open', confidence: 0.91, corrected_text: 'abre spotify' },
  },
});
assert.equal(runtimeEvent.intent, 'app.open');
assert.equal(runtimeEvent.normalizedText, 'abre spotify');
assert.equal(runtimeEvent.confidence, 0.91);
assert.equal(runtimeEvent.executionStatus, 'completed');
assert.equal(runtimeEvent.confirmationState, 'approved');
assert.equal(
  normalizeVoiceEvent({
    kind: 'confirmation',
    payload: { status: 'pending_confirmation', route: { intent: 'app.open' } },
  }).confirmationState,
  'pending_confirmation',
);
assert.equal(
  normalizeVoiceEvent({
    kind: 'error',
    payload: { error: 'tool failed', route: { error: 'fallback failed' } },
  }).error,
  'tool failed',
);
assert.equal(getVoiceStatusVisual('ACTIVE').label, 'ACTIVE');

assert.equal(getVoiceStatusVisual('READY').accent, '#35d48a');
assert.equal(getVoiceStatusVisual('LISTENING').animation, 'reactive');
assert.equal(getVoiceStatusVisual('THINKING').label, 'THINKING');
assert.equal(getVoiceStatusVisual('SPEAKING').accent, '#48a6ff');
assert.equal(getVoiceStatusVisual('ERROR').tone, 'critical');

console.log('voice-shell state contract ok');
