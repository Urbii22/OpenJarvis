export const VOICE_SHELL_FLAG_KEY = 'openjarvis-desktop-voice-shell-enabled';
export const VOICE_SHELL_MODE_KEY = 'openjarvis-desktop-voice-shell-mode';
export const DEFAULT_VOICE_SHELL_MODE = 'compact' as const;

export type VoiceShellMode = 'compact' | 'expanded';
export type VoiceStatus =
  | 'ACTIVE'
  | 'READY'
  | 'LISTENING'
  | 'THINKING'
  | 'SPEAKING'
  | 'INTERRUPTED'
  | 'ERROR';

export interface VoiceMetrics {
  voiceProvider?: string;
  voiceProfile?: string;
  ttfsMs?: number;
  totalSynthesisMs?: number;
  micEnergy?: number;
}

export interface VoiceShellState {
  status: VoiceStatus;
  transcript: string;
  normalizedText: string;
  intent: string;
  confidence?: number;
  executionStatus: string;
  confirmationState: string;
  error: string;
  lastAction: string;
  metrics: VoiceMetrics;
}

export interface VoiceRuntimeEvent {
  kind?: string;
  payload?: Record<string, unknown>;
  type?: string;
  event?: string;
  state?: string;
  status?: string;
  text?: string;
  text_partial?: string;
  text_final?: string;
  transcript?: string;
  detail?: string;
  message?: string;
  voice_provider?: string;
  voice_profile?: string;
  ttfs_ms?: number;
  latency_ms?: number;
  total_synthesis_ms?: number;
  mic_energy?: number;
  mic_rms?: number;
  mic_peak?: number;
  route?: Record<string, unknown>;
  error?: unknown;
}

function safeText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value == null) return '';
  if (Array.isArray(value)) return value.map((item) => safeText(item)).join('\n').trim();
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const preferred = obj.content ?? obj.text ?? obj.message ?? obj.detail ?? obj.thought;
    if (typeof preferred === 'string') return preferred;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

interface FlagContext {
  env?: Record<string, string | boolean | undefined>;
  storage?: Pick<Storage, 'getItem'> | null;
}

function readFlag(value: string | boolean | null | undefined): boolean | null {
  if (typeof value === 'boolean') return value;
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on', 'enabled'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off', 'disabled'].includes(normalized)) return false;
  return null;
}

export function isVoiceShellEnabled(context: FlagContext = {}): boolean {
  const localFlag = readFlag(context.storage?.getItem(VOICE_SHELL_FLAG_KEY));
  if (localFlag !== null) return localFlag;
  const envFlag = readFlag(context.env?.VITE_VOICE_SHELL_ENABLED);
  return envFlag ?? false;
}

export function isVoiceShellEnabledFromRuntime(): boolean {
  return isVoiceShellEnabled({
    env: import.meta.env,
    storage: typeof localStorage === 'undefined' ? null : localStorage,
  });
}

export function readPersistedShellMode(
  storage: Pick<Storage, 'getItem'> | null | undefined,
): VoiceShellMode {
  const raw = storage?.getItem(VOICE_SHELL_MODE_KEY);
  return raw === 'expanded' || raw === 'compact' ? raw : DEFAULT_VOICE_SHELL_MODE;
}

export function persistShellMode(
  storage: Pick<Storage, 'setItem'> | null | undefined,
  mode: VoiceShellMode,
): void {
  storage?.setItem(VOICE_SHELL_MODE_KEY, mode);
}

export function normalizeVoiceEvent(event: VoiceRuntimeEvent): VoiceShellState {
  const payload = (event.payload && typeof event.payload === 'object'
    ? event.payload
    : {}) as Record<string, unknown>;
  const route =
    (payload.route && typeof payload.route === 'object' ? payload.route : event.route) || {};
  const eventType = (event.kind || event.type || event.event || event.state || event.status || '').toLowerCase();
  const payloadStatus = safeText(payload.status || payload.state).toLowerCase();
  let status: VoiceStatus = 'READY';

  if (['hotkey', 'recording', 'listening', 'partial_text', 'wake_word_detected'].includes(eventType)) {
    status = 'LISTENING';
  } else if (eventType === 'recognition') {
    status = 'LISTENING';
  } else if (eventType === 'confirmation') {
    status = 'THINKING';
  } else if (eventType === 'execution') {
    status = payloadStatus.includes('error') || payloadStatus.includes('failed') ? 'ERROR' : 'THINKING';
  } else if (['active'].includes(eventType)) {
    status = 'ACTIVE';
  } else if (['transcribing', 'thinking', 'synthesizing', 'inference_start', 'agent_turn_start'].includes(eventType)) {
    status = 'THINKING';
  } else if (['speaking', 'speak', 'jarvis', 'tts_start', 'audio_start', 'speech_start'].includes(eventType)) {
    status = 'SPEAKING';
  } else if (['interrupted', 'barge', 'barge_in', 'speech_interrupted'].includes(eventType)) {
    status = 'INTERRUPTED';
  } else if (['error', 'failed', 'exception'].includes(eventType)) {
    status = 'ERROR';
  }

  return {
    status,
    transcript: safeText(payload.transcript || event.transcript || event.text_final || event.text_partial || event.text || ''),
    normalizedText: safeText(payload.normalized || payload.corrected_text || (route as Record<string, unknown>).corrected_text || ''),
    intent: safeText((route as Record<string, unknown>).intent || ''),
    confidence:
      typeof (route as Record<string, unknown>).confidence === 'number'
        ? ((route as Record<string, unknown>).confidence as number)
        : undefined,
    executionStatus: safeText(payload.status || ''),
    confirmationState: safeText(payload.confirmation_state || payload.state || (eventType === 'confirmation' ? payload.status : '')),
    error: safeText(payload.error || (route as Record<string, unknown>).error || event.error || ''),
    lastAction: safeText(payload.reason || payload.tool_name || event.detail || event.message || payload.status || ''),
    metrics: {
      voiceProvider: event.voice_provider,
      voiceProfile: event.voice_profile,
      ttfsMs: event.ttfs_ms ?? event.latency_ms,
      totalSynthesisMs: event.total_synthesis_ms,
      micEnergy: event.mic_energy ?? event.mic_rms ?? event.mic_peak,
    },
  };
}

export function getVoiceStatusVisual(status: VoiceStatus): {
  label: VoiceStatus;
  accent: string;
  glow: string;
  tone: 'idle' | 'active' | 'busy' | 'critical';
  animation: 'steady' | 'reactive' | 'thinking' | 'speaking' | 'alert';
} {
  switch (status) {
    case 'LISTENING':
      return {
        label: status,
        accent: '#ffb33c',
        glow: 'rgba(255, 179, 60, 0.34)',
        tone: 'active',
        animation: 'reactive',
      };
    case 'THINKING':
      return {
        label: status,
        accent: '#39d5ff',
        glow: 'rgba(57, 213, 255, 0.3)',
        tone: 'busy',
        animation: 'thinking',
      };
    case 'SPEAKING':
      return {
        label: status,
        accent: '#48a6ff',
        glow: 'rgba(72, 166, 255, 0.38)',
        tone: 'active',
        animation: 'speaking',
      };
    case 'INTERRUPTED':
    case 'ERROR':
      return {
        label: status,
        accent: '#ff6767',
        glow: 'rgba(255, 103, 103, 0.28)',
        tone: 'critical',
        animation: 'alert',
      };
    case 'READY':
    case 'ACTIVE':
    default:
      return {
        label: status === 'ACTIVE' ? 'ACTIVE' : 'READY',
        accent: '#35d48a',
        glow: 'rgba(53, 212, 138, 0.28)',
        tone: 'idle',
        animation: 'steady',
      };
  }
}
