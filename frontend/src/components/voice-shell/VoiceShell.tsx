import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import {
  Activity,
  ChevronsDownUp,
  ChevronsUpDown,
  CircleStop,
  ExternalLink,
  Gauge,
  History,
  Keyboard,
  MessageSquareText,
  Mic,
  Send,
  Settings,
  ShieldCheck,
  Volume2,
  Zap,
} from 'lucide-react';
import { useAppStore, generateId } from '../../lib/store';
import { streamChat } from '../../lib/sse';
import { fetchSavings, getBase, subscribeVoiceShellEvents } from '../../lib/api';
import { COMPUTER_USE_TOOLS } from '../../lib/computerTools';
import { withComputerUsePrompt } from '../../lib/computerUsePrompt';
import { MessageBubble } from '../Chat/MessageBubble';
import type {
  ChatMessage,
  MessageTelemetry,
  ServerInfo,
  TokenUsage,
  ToolCallInfo,
  ToolConfirmationRequest,
} from '../../types';
import { useSpeech } from '../../hooks/useSpeech';
import { ToolConfirmationDialog } from '../Chat/ToolConfirmationDialog';
import {
  getVoiceStatusVisual,
  normalizeVoiceEvent,
  persistShellMode,
  readPersistedShellMode,
  type VoiceMetrics,
  type VoiceShellMode,
  type VoiceShellState,
  type VoiceStatus,
} from './state';

interface VoiceShellProps {
  onOpenLegacy: (path?: string) => void;
}

interface VoiceController {
  input: string;
  setInput: (value: string) => void;
  speechState: 'idle' | 'recording' | 'transcribing';
  speechAvailable: boolean;
  speechEnabled: boolean;
  isStreaming: boolean;
  sendMessage: () => Promise<void>;
  stopGeneration: () => void;
  handleMic: () => Promise<void>;
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

export function VoiceShell({ onOpenLegacy }: VoiceShellProps) {
  const [mode, setModeState] = useState<VoiceShellMode>(() =>
    readPersistedShellMode(typeof localStorage === 'undefined' ? null : localStorage),
  );
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('ACTIVE');
  const [lastLine, setLastLine] = useState('Ready for voice or text.');
  const [metrics, setMetrics] = useState<VoiceMetrics>({});
  const [input, setInput] = useState('');
  const [confirmation, setConfirmation] = useState<ToolConfirmationRequest | null>(null);
  const [voiceEventsConnected, setVoiceEventsConnected] = useState(false);
  const [routerState, setRouterState] = useState<Pick<
    VoiceShellState,
    'transcript' | 'normalizedText' | 'intent' | 'confidence' | 'executionStatus' | 'confirmationState' | 'error'
  >>({
    transcript: '',
    normalizedText: '',
    intent: '',
    confidence: undefined,
    executionStatus: '',
    confirmationState: '',
    error: '',
  });
  const messages = useAppStore((s) => s.messages);
  const streamState = useAppStore((s) => s.streamState);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const savings = useAppStore((s) => s.savings);
  const speechEnabled = useAppStore((s) => s.settings.speechEnabled);
  const visual = getVoiceStatusVisual(voiceStatus);
  const lastMessage = messages[messages.length - 1];
  const activeId = useAppStore((s) => s.activeId);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const addMessage = useAppStore((s) => s.addMessage);
  const createConversation = useAppStore((s) => s.createConversation);
  const updateLastAssistant = useAppStore((s) => s.updateLastAssistant);
  const setStreamState = useAppStore((s) => s.setStreamState);
  const resetStream = useAppStore((s) => s.resetStream);
  const maxTokens = useAppStore((s) => s.settings.maxTokens);
  const temperature = useAppStore((s) => s.settings.temperature);
  const {
    state: speechState,
    available: speechAvailable,
    startRecording,
    stopRecording,
    startStreamingRecording,
    stopStreamingRecording,
    interruptSpeech,
  } = useSpeech();
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const applyVoiceUpdate = (
    status: VoiceStatus,
    line?: unknown,
    nextMetrics?: VoiceMetrics,
  ) => {
    setVoiceStatus(status);
    const text = safeText(line);
    if (text) setLastLine(text);
    if (nextMetrics) setMetrics((current) => ({ ...current, ...nextMetrics }));
  };

  const setMode = (next: VoiceShellMode) => {
    setModeState(next);
    persistShellMode(typeof localStorage === 'undefined' ? null : localStorage, next);
  };

  useEffect(() => {
    let active = true;
    let cleanup = () => {};

    void subscribeVoiceShellEvents((event) => {
      const normalized = normalizeVoiceEvent(event);
      if (!active) return;
      applyVoiceUpdate(
        normalized.status,
        normalized.transcript || normalized.lastAction || undefined,
        normalized.metrics,
      );
      setRouterState({
        transcript: normalized.transcript,
        normalizedText: normalized.normalizedText,
        intent: normalized.intent,
        confidence: normalized.confidence,
        executionStatus: normalized.executionStatus,
        confirmationState: normalized.confirmationState,
        error: normalized.error,
      });
    }).then((unsubscribe) => {
      if (!active) {
        unsubscribe();
        return;
      }
      cleanup = unsubscribe;
      setVoiceEventsConnected(true);
    });

    return () => {
      active = false;
      cleanup();
    };
  }, []);

  useEffect(() => {
    if (streamState.isStreaming) {
      setVoiceStatus(streamState.content ? 'SPEAKING' : 'THINKING');
      if (streamState.phase) setLastLine(streamState.phase);
      return;
    }
    if (voiceStatus === 'THINKING' || voiceStatus === 'SPEAKING') {
      setVoiceStatus('ACTIVE');
    }
  }, [streamState.content, streamState.isStreaming, streamState.phase, voiceStatus]);

  useEffect(() => {
    if (lastMessage?.content) {
      setLastLine(safeText(lastMessage.content).slice(0, 160));
    }
  }, [lastMessage?.content]);

  useEffect(() => () => {
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const stopGeneration = () => {
    abortRef.current?.abort();
    interruptSpeech();
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    abortRef.current = null;
    resetStream();
    applyVoiceUpdate('INTERRUPTED', 'Generation interrupted.');
  };

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || streamState.isStreaming) return;
    setInput('');

    let convId = activeId;
    if (!convId) convId = createConversation(selectedModel);

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    };
    addMessage(convId, userMsg);

    const apiMessages = withComputerUsePrompt(
      useAppStore.getState().messages.map((message) => ({
        role: message.role,
        content: safeText(message.content),
      })),
    );

    addMessage(convId, {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    });

    const startTime = Date.now();
    const controller = new AbortController();
    abortRef.current = controller;
    timerRef.current = setInterval(() => {
      setStreamState({ elapsedMs: Date.now() - startTime });
    }, 100);

    let accumulatedContent = '';
    let usage: TokenUsage | undefined;
    let complexity: { score: number; tier: string; suggested_max_tokens: number } | undefined;
    let ttftMs: number | undefined;
    const toolCalls: ToolCallInfo[] = [];

    setStreamState({
      isStreaming: true,
      phase: 'Thinking...',
      elapsedMs: 0,
      activeToolCalls: [],
      content: '',
    });
    applyVoiceUpdate('THINKING', trimmed);

    try {
      for await (const sseEvent of streamChat(
        {
          model: selectedModel,
          messages: apiMessages,
          stream: true,
          temperature,
          max_tokens: maxTokens,
          tools: [...COMPUTER_USE_TOOLS],
        },
        controller.signal,
      )) {
        if (sseEvent.event === 'tool_call_start') {
          const data = JSON.parse(sseEvent.data);
          toolCalls.push({
            id: generateId(),
            tool: data.tool,
            arguments: data.arguments || '',
            status: 'running',
          });
          setStreamState({ phase: `Calling ${data.tool}...`, activeToolCalls: [...toolCalls] });
          applyVoiceUpdate('THINKING', `Calling ${data.tool}...`);
          continue;
        }

        if (sseEvent.event === 'tool_call_end') {
          const data = JSON.parse(sseEvent.data);
          const running = toolCalls.find((tool) => tool.tool === data.tool && tool.status === 'running');
          if (running) {
            running.status = data.success ? 'success' : 'error';
            running.latency = data.latency;
            running.result = data.result;
          }
          setStreamState({ phase: 'Speaking...', activeToolCalls: [...toolCalls] });
          continue;
        }

        if (sseEvent.event === 'tool_confirmation_required') {
          const data = JSON.parse(sseEvent.data);
          setConfirmation(data);
          setStreamState({ phase: `Waiting for approval: ${data.tool}` });
          applyVoiceUpdate('THINKING', `Waiting for approval: ${data.tool}`);
          continue;
        }

        const data = JSON.parse(sseEvent.data);
        if (data.usage) usage = data.usage;
        if (data.complexity) complexity = data.complexity;
        const delta = data.choices?.[0]?.delta?.content || '';
        if (delta) {
          if (!ttftMs) ttftMs = Date.now() - startTime;
          accumulatedContent += delta;
          setStreamState({ content: accumulatedContent, phase: 'Speaking...' });
          updateLastAssistant(convId, accumulatedContent, toolCalls.length > 0 ? [...toolCalls] : undefined);
          applyVoiceUpdate('SPEAKING', accumulatedContent.slice(-160));
        }
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        accumulatedContent ||= '(Generation interrupted)';
      } else {
        accumulatedContent ||= `Error: ${error?.message || String(error)}`;
        applyVoiceUpdate('ERROR', accumulatedContent);
      }
    } finally {
      if (!accumulatedContent) accumulatedContent = 'No response was generated. Please try again.';
      const totalMs = Date.now() - startTime;
      const telemetry: MessageTelemetry = {
        model_id: selectedModel,
        total_ms: totalMs,
        ttft_ms: ttftMs,
        complexity_score: complexity?.score,
        complexity_tier: complexity?.tier,
        suggested_max_tokens: complexity?.suggested_max_tokens,
        tokens_per_sec: usage?.completion_tokens ? usage.completion_tokens / (totalMs / 1000) : undefined,
      };

      updateLastAssistant(
        convId,
        accumulatedContent,
        toolCalls.length > 0 ? toolCalls : undefined,
        usage,
        telemetry,
      );
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      abortRef.current = null;
      resetStream();
      applyVoiceUpdate('ACTIVE', accumulatedContent.slice(0, 160), { ttfsMs: ttftMs });
      fetchSavings().then((data) => useAppStore.getState().setSavings(data)).catch(() => {});
    }
  };

  const respondToConfirmation = async (approved: boolean) => {
    if (!confirmation) return;
    const path = confirmation.agent_id
      ? `${getBase()}/v1/managed-agents/${confirmation.agent_id}/tool-confirmations/${confirmation.confirmation_id}`
      : `${getBase()}/v1/tool-confirmations/${confirmation.confirmation_id}`;
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    });
    setConfirmation(null);
  };

  const handleMic = async () => {
    if (speechState === 'recording') {
      applyVoiceUpdate('THINKING', 'Transcribing...');
      stopStreamingRecording();
      return;
    }

    applyVoiceUpdate('LISTENING', 'Listening...');
    try {
      await startStreamingRecording({
        onPartialText: (text) => applyVoiceUpdate('LISTENING', text || 'Listening...'),
        onFinalText: (text) => {
          applyVoiceUpdate('ACTIVE', text || 'No speech detected.');
          if (text) setInput((current) => (current ? `${current} ${text}` : text));
        },
        onInterrupted: () => applyVoiceUpdate('INTERRUPTED', 'Speech interrupted.'),
      });
    } catch {
      try {
        await startRecording();
      } catch {
        applyVoiceUpdate('ERROR', 'Microphone transcription failed.');
      }
    }
  };

  const controller: VoiceController = {
    input,
    setInput,
    speechState,
    speechAvailable,
    speechEnabled,
    isStreaming: streamState.isStreaming,
    sendMessage,
    stopGeneration,
    handleMic,
  };

  const shellClass = mode === 'expanded' ? 'voice-shell voice-shell--expanded' : 'voice-shell';

  return (
    <>
      {confirmation && (
        <ToolConfirmationDialog
          request={confirmation}
          onApprove={() => void respondToConfirmation(true)}
          onDeny={() => void respondToConfirmation(false)}
        />
      )}
      <div
        className={shellClass}
        style={{
          '--voice-accent': visual.accent,
          '--voice-glow': visual.glow,
        } as CSSProperties}
      >
      <div className="voice-shell__backdrop" aria-hidden="true" />
      <header className="voice-shell__topbar">
        <div className="voice-shell__brand">
          <span className="voice-shell__brand-mark" />
          <span>OpenJarvis</span>
        </div>
        <div className="voice-shell__top-actions">
          <button type="button" className="voice-shell__icon-button" onClick={() => onOpenLegacy('/')} title="Open legacy UI">
            <ExternalLink size={16} />
          </button>
          <button type="button" className="voice-shell__icon-button" onClick={() => useAppStore.getState().setCommandPaletteOpen(true)} title="Command palette">
            <Keyboard size={16} />
          </button>
          <button type="button" className="voice-shell__icon-button" onClick={() => setMode(mode === 'compact' ? 'expanded' : 'compact')} title={mode === 'compact' ? 'Expand workspace' : 'Collapse workspace'}>
            {mode === 'compact' ? <ChevronsUpDown size={17} /> : <ChevronsDownUp size={17} />}
          </button>
        </div>
      </header>

      {mode === 'expanded' ? (
        <ExpandedWorkspace
          controller={controller}
          status={voiceStatus}
          lastLine={lastLine}
          metrics={metrics}
          serverInfo={serverInfo}
          savings={savings}
          voiceEventsConnected={voiceEventsConnected}
          visualLabel={visual.label}
          routerState={routerState}
          onCollapse={() => setMode('compact')}
          onOpenLegacy={onOpenLegacy}
        />
      ) : (
        <CompactWorkspace
          controller={controller}
          status={voiceStatus}
          lastLine={lastLine}
          metrics={metrics}
          visualLabel={visual.label}
          routerState={routerState}
          onExpand={() => setMode('expanded')}
        />
      )}
      </div>
    </>
  );
}

function CompactWorkspace({
  controller,
  status,
  lastLine,
  metrics,
  visualLabel,
  routerState,
  onExpand,
}: {
  controller: VoiceController;
  status: VoiceStatus;
  lastLine: string;
  metrics: VoiceMetrics;
  visualLabel: VoiceStatus;
  routerState: Pick<
    VoiceShellState,
    'intent' | 'confidence' | 'executionStatus' | 'confirmationState' | 'error'
  >;
  onExpand: () => void;
}) {
  return (
    <main className="voice-shell__compact" aria-label="Voice-first compact shell">
      <VoiceOrb status={status} />
      <div className="voice-shell__status">STATUS: {visualLabel}</div>
      <p className="voice-shell__last-line">{lastLine || 'Ready.'}</p>
      <p className="voice-shell__last-line">
        {formatRouterSummary(routerState)}
      </p>
      <RuntimeStrip metrics={metrics} compact />
      <VoiceShellInput controller={controller} />
      <button type="button" className="voice-shell__expand" onClick={onExpand}>
        <ChevronsUpDown size={16} />
        <span>Workspace</span>
      </button>
    </main>
  );
}

function ExpandedWorkspace({
  controller,
  status,
  lastLine,
  metrics,
  serverInfo,
  savings,
  voiceEventsConnected,
  visualLabel,
  routerState,
  onCollapse,
  onOpenLegacy,
}: {
  controller: VoiceController;
  status: VoiceStatus;
  lastLine: string;
  metrics: VoiceMetrics;
  serverInfo: ServerInfo | null;
  savings: { total_calls: number; total_tokens: number; local_cost: number } | null;
  voiceEventsConnected: boolean;
  visualLabel: VoiceStatus;
  routerState: Pick<
    VoiceShellState,
    'transcript' | 'normalizedText' | 'intent' | 'confidence' | 'executionStatus' | 'confirmationState' | 'error'
  >;
  onCollapse: () => void;
  onOpenLegacy: (path?: string) => void;
}) {
  const messages = useAppStore((s) => s.messages);
  const streamState = useAppStore((s) => s.streamState);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, streamState.content]);

  return (
    <main className="voice-shell__expanded-grid" aria-label="Voice-first expanded workspace">
      <section className="voice-shell__conversation">
        <div className="voice-shell__panel-head">
          <MessageSquareText size={16} />
          <span>Conversation</span>
          <button type="button" className="voice-shell__mini-button" onClick={onCollapse}>
            <ChevronsDownUp size={14} />
            <span>Compact</span>
          </button>
        </div>
        <div ref={listRef} className="voice-shell__message-list">
          {messages.length === 0 ? (
            <div className="voice-shell__empty">
              <History size={26} />
              <span>No conversation yet.</span>
            </div>
          ) : (
            messages.map((message) => <MessageBubble key={message.id} message={message} />)
          )}
        </div>
        <VoiceShellInput controller={controller} expanded />
      </section>

      <aside className="voice-shell__side">
        <section className="voice-shell__orb-panel">
          <VoiceOrb status={status} small />
          <div>
            <div className="voice-shell__status voice-shell__status--small">STATUS: {visualLabel}</div>
            <p className="voice-shell__last-line voice-shell__last-line--side">{lastLine}</p>
          </div>
        </section>

        <PanelSection title="Voice Runtime" icon={Mic}>
          <RuntimeStrip metrics={metrics} />
          <MiniRow label="Provider" value={metrics.voiceProvider || (voiceEventsConnected ? 'Awaiting runtime' : 'Bridge offline')} />
          <MiniRow label="Profile" value={metrics.voiceProfile || 'Default'} />
          <MiniRow label="Intent" value={routerState.intent || 'Unknown'} />
          <MiniRow label="Confidence" value={formatConfidence(routerState.confidence)} />
          <MiniRow label="Exec status" value={routerState.executionStatus || 'Pending'} />
          <MiniRow label="Confirm" value={routerState.confirmationState || 'N/A'} />
          <MiniRow label="Transcript" value={routerState.transcript || 'N/A'} />
          <MiniRow label="Normalized" value={routerState.normalizedText || 'N/A'} />
          <MiniRow label="Error" value={routerState.error || 'None'} />
          <MiniRow label="Wake word" value="Optional" />
          <MiniRow label="Interrupt" value="Available while speaking" />
        </PanelSection>

        <PanelSection title="Device Actions" icon={Zap}>
          <ActionButton label="Settings" icon={Settings} onClick={() => onOpenLegacy('/settings')} />
          <ActionButton label="Logs" icon={Activity} onClick={() => onOpenLegacy('/logs')} />
          <ActionButton label="Data Sources" icon={ShieldCheck} onClick={() => onOpenLegacy('/data-sources')} />
        </PanelSection>

        <PanelSection title="Telemetry" icon={Gauge}>
          <MiniRow label="Model" value={serverInfo?.model || 'Detecting'} />
          <MiniRow label="Engine" value={serverInfo?.engine || 'Unknown'} />
          <MiniRow label="Requests" value={String(savings?.total_calls ?? 0)} />
          <MiniRow label="Tokens" value={String(savings?.total_tokens ?? 0)} />
        </PanelSection>
      </aside>
    </main>
  );
}

function VoiceShellInput({
  controller,
  expanded = false,
}: {
  controller: VoiceController;
  expanded?: boolean;
}) {
  const className = expanded ? 'voice-shell__input voice-shell__input--expanded' : 'voice-shell__input';

  return (
    <form
      className={className}
      onSubmit={(event) => {
        event.preventDefault();
        void controller.sendMessage();
      }}
    >
      <button
        type="button"
        className="voice-shell__round-button"
        onClick={() => void controller.handleMic()}
        disabled={!controller.speechEnabled || !controller.speechAvailable || controller.isStreaming}
        title={!controller.speechEnabled ? 'Enable speech in settings' : controller.speechAvailable ? 'Push to talk' : 'Speech backend unavailable'}
      >
        <Mic size={18} />
      </button>
      <input
        value={controller.input}
        onChange={(event) => controller.setInput(event.target.value)}
        placeholder="Type fallback command..."
        aria-label="Text fallback command"
      />
      {controller.isStreaming ? (
        <button type="button" className="voice-shell__round-button voice-shell__round-button--stop" onClick={controller.stopGeneration} title="Interrupt">
          <CircleStop size={18} />
        </button>
      ) : (
        <button type="submit" className="voice-shell__round-button" disabled={!controller.input.trim()} title="Send">
          <Send size={18} />
        </button>
      )}
    </form>
  );
}

function VoiceOrb({ status, small = false }: { status: VoiceStatus; small?: boolean }) {
  const visual = getVoiceStatusVisual(status);
  return (
    <div className={small ? 'voice-orb voice-orb--small' : 'voice-orb'} data-animation={visual.animation} aria-hidden="true">
      <div className="voice-orb__ring voice-orb__ring--outer" />
      <div className="voice-orb__ring voice-orb__ring--middle" />
      <div className="voice-orb__core">
        {status === 'SPEAKING' ? <Volume2 size={small ? 22 : 34} /> : <Activity size={small ? 22 : 34} />}
      </div>
    </div>
  );
}

function RuntimeStrip({ metrics, compact = false }: { metrics: VoiceMetrics; compact?: boolean }) {
  const items = [
    { label: 'Provider', value: metrics.voiceProvider || 'local' },
    { label: 'TTFS', value: metrics.ttfsMs == null ? '--' : `${Math.round(metrics.ttfsMs)}ms` },
    { label: 'Synth', value: metrics.totalSynthesisMs == null ? '--' : `${Math.round(metrics.totalSynthesisMs)}ms` },
    { label: 'Mic', value: metrics.micEnergy == null ? '--' : `${Math.round(metrics.micEnergy * 100)}%` },
  ];

  return (
    <div className={compact ? 'voice-shell__runtime voice-shell__runtime--compact' : 'voice-shell__runtime'}>
      {items.map((item) => (
        <span key={item.label}>
          <b>{item.label}</b>
          {item.value}
        </span>
      ))}
    </div>
  );
}

function formatConfidence(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return `${Math.round(value * 100)}%`;
}

function formatRouterSummary(state: {
  intent: string;
  confidence?: number;
  executionStatus: string;
  confirmationState: string;
  error: string;
}): string {
  if (!state.intent && !state.executionStatus && !state.confirmationState && !state.error) {
    return 'Router: waiting for recognition';
  }
  const intent = state.intent || 'unknown';
  const confidence = formatConfidence(state.confidence);
  const exec = state.executionStatus || 'pending';
  const confirm = state.confirmationState || 'n/a';
  const err = state.error ? ` | err: ${state.error}` : '';
  return `Router: ${intent} (${confidence}) | exec: ${exec} | confirm: ${confirm}${err}`;
}

function PanelSection({ title, icon: Icon, children }: { title: string; icon: typeof Activity; children: ReactNode }) {
  return (
    <section className="voice-shell__panel">
      <div className="voice-shell__panel-head">
        <Icon size={16} />
        <span>{title}</span>
      </div>
      <div className="voice-shell__panel-body">{children}</div>
    </section>
  );
}

function MiniRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="voice-shell__mini-row">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function ActionButton({ label, icon: Icon, onClick }: { label: string; icon: typeof Activity; onClick: () => void }) {
  return (
    <button type="button" className="voice-shell__action" onClick={onClick}>
      <Icon size={15} />
      <span>{label}</span>
    </button>
  );
}
