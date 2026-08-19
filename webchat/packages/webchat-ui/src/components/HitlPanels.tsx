'use client';

import React, { useState } from 'react';
import type { CustomProtocolEvent } from '../agui';
import { WC } from '../chrome';

interface HitlSubmitContext {
  apiKey?: string;
  credentials?: RequestCredentials;
  headers?: Record<string, string>;
}

export interface ApprovalHitlValue {
  execution_id: string;
  node_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_args?: Record<string, unknown>;
  timeout_seconds?: number;
}

export interface ChoiceHitlValue {
  execution_id: string;
  node_id: string;
  choice_id: string;
  title?: string;
  description?: string;
  options?: Array<{ key: string; label: string; disabled?: boolean }>;
  multiple?: boolean;
}

interface HitlPanelsProps extends HitlSubmitContext {
  event: CustomProtocolEvent | null;
  approvalUrl?: string;
  choiceUrl?: string;
  onResolved: () => void;
}

function authHeaders(ctx: HitlSubmitContext): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(ctx.headers || {}),
  };
  if (ctx.apiKey) {
    headers.Authorization = `Bearer ${ctx.apiKey}`;
  }
  return headers;
}

export function isBlockingHitlEvent(event: CustomProtocolEvent | null): boolean {
  return event?.name === 'approval_request' || event?.name === 'user_choice_request';
}

export function formatDegradedCustomEvent(event: CustomProtocolEvent): string {
  const value = event.value;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const title = typeof record.title === 'string' ? record.title : event.name;
    const description =
      typeof record.description === 'string'
        ? record.description
        : typeof record.content === 'string'
          ? record.content
          : typeof record.markdown === 'string'
            ? record.markdown
            : JSON.stringify(record);
    return `${title}\n${description}`;
  }
  return `${event.name}: ${String(value ?? '')}`;
}

export const HitlPanels: React.FC<HitlPanelsProps> = ({
  event,
  approvalUrl,
  choiceUrl,
  apiKey,
  credentials,
  headers,
  onResolved,
}) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!event || !isBlockingHitlEvent(event)) {
    return null;
  }

  const submit = async (url: string, body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: authHeaders({ apiKey, headers }),
        credentials: credentials ?? 'include',
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      onResolved();
    } catch {
      setError('提交失败，请重试');
    } finally {
      setBusy(false);
    }
  };

  if (event.name === 'approval_request' && approvalUrl) {
    const value = (event.value || {}) as ApprovalHitlValue;
    return (
      <div
        className="mt-2.5 rounded-[10px] p-2.5 text-sm"
        style={{ background: WC.white, border: `1px solid ${WC.botBorder}`, color: WC.botText }}
      >
        <div className="mb-1 text-[13px] font-semibold">需要审批</div>
        <div className="mb-2 text-xs" style={{ color: WC.muted }}>
          {value.tool_name}
        </div>
        {error && <p className="mb-2 text-xs" style={{ color: WC.fail }}>{error}</p>}
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            className="h-7 rounded-lg px-3 text-xs disabled:opacity-50"
            style={{ background: WC.indigo, border: 'none', color: WC.onPrimary }}
            onClick={() =>
              submit(approvalUrl, {
                execution_id: value.execution_id,
                node_id: value.node_id,
                tool_call_id: value.tool_call_id,
                decision: 'approve',
              })
            }
          >
            通过
          </button>
          <button
            type="button"
            disabled={busy}
            className="h-7 rounded-lg px-3 text-xs disabled:opacity-50"
            style={{ background: WC.white, border: `1px solid ${WC.botBorder}`, color: WC.botText }}
            onClick={() =>
              submit(approvalUrl, {
                execution_id: value.execution_id,
                node_id: value.node_id,
                tool_call_id: value.tool_call_id,
                decision: 'reject',
              })
            }
          >
            拒绝
          </button>
        </div>
      </div>
    );
  }

  if (event.name === 'user_choice_request' && choiceUrl) {
    const value = (event.value || {}) as ChoiceHitlValue;
    const options = value.options || [];
    return (
      <div
        className="mt-2.5 rounded-[10px] p-2.5 text-sm"
        style={{ background: WC.white, border: `1px solid ${WC.botBorder}`, color: WC.botText }}
      >
        <div className="text-[13px] font-semibold">{value.title || '请选择'}</div>
        {value.description && (
          <p className="mt-1 text-xs" style={{ color: WC.muted }}>
            {value.description}
          </p>
        )}
        {error && <p className="mt-2 text-xs" style={{ color: WC.fail }}>{error}</p>}
        <div className="mt-2 flex flex-wrap gap-2">
          {options.map((option) => (
            <button
              key={option.key}
              type="button"
              disabled={busy || option.disabled}
              className="h-7 rounded-lg px-3 text-xs disabled:opacity-50"
              style={{ background: WC.white, border: `1px solid ${WC.botBorder}`, color: WC.botText }}
              onClick={() =>
                submit(choiceUrl, {
                  execution_id: value.execution_id,
                  node_id: value.node_id,
                  choice_id: value.choice_id,
                  selected: [option.key],
                })
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return null;
};
