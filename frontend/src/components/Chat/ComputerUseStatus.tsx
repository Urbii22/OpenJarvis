import { MonitorCog } from 'lucide-react';

const ENABLED_TOOLS = ['Apps', 'Files', 'Folders', 'Shell'];

export function ComputerUseStatus() {
  return (
    <div
      className="flex items-center gap-2 rounded-md px-2 py-1 text-[11px]"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border)',
        color: 'var(--color-text-secondary)',
      }}
      title="Computer use tools are available with confirmation for risky actions"
    >
      <MonitorCog size={13} style={{ color: 'var(--color-accent)' }} />
      <span>Computer Use</span>
      <span style={{ color: 'var(--color-success)' }}>Enabled</span>
      <span style={{ color: 'var(--color-text-tertiary)' }}>
        {ENABLED_TOOLS.join(' / ')}
      </span>
    </div>
  );
}
