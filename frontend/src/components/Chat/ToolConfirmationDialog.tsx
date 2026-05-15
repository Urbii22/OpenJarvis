import { AlertTriangle, Check, X } from 'lucide-react';
import type { ToolConfirmationRequest } from '../../types';

function prettyArgs(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw || '{}';
  }
}

export function ToolConfirmationDialog({
  request,
  onApprove,
  onDeny,
}: {
  request: ToolConfirmationRequest;
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className="w-[min(520px,calc(100vw-32px))] rounded-lg p-4"
        style={{
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text)',
        }}
      >
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle size={18} style={{ color: 'var(--color-warning, #f59e0b)' }} />
          <div className="font-semibold">Approve computer action</div>
        </div>
        <div className="mb-2 text-sm">
          Tool: <b>{request.tool}</b>
        </div>
        <div className="mb-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          Risk: {request.risk_level}
        </div>
        <pre
          className="max-h-56 overflow-auto rounded p-3 text-xs"
          style={{
            background: 'var(--color-code-bg, rgba(0,0,0,0.25))',
            color: 'var(--color-text-secondary)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {prettyArgs(request.arguments)}
        </pre>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="inline-flex items-center gap-2 rounded px-3 py-2 text-sm" onClick={onDeny}>
            <X size={14} />
            Deny
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded px-3 py-2 text-sm font-medium"
            style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent)' }}
            onClick={onApprove}
          >
            <Check size={14} />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
