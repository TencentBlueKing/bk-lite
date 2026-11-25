import { ChatMarkdown } from '@bk-lite/chat-content/ui';
import React, { useEffect, useRef, useState } from 'react';
import { unwrapPlatformPayload } from '@webchat/core';

interface WikiWriteSeed {
  material_id: number;
  phase: string;
  summary: string;
}

interface WikiWriteCheck {
  id: number;
  page_title?: string;
  current_body?: string;
  incoming_body?: string;
  actions?: string[];
  status?: string;
}

interface WikiWriteOutcome {
  material_id: number;
  phase: string;
  summary: string;
  checks?: WikiWriteCheck[];
}

const ACTION_LABELS: Record<string, string> = {
  keep_current: '保留当前',
  keep_all: '全部保留',
  use_new: '使用新知识',
  edit_accept: '编辑后采用',
  keep_separate: '保持独立',
  merge: '确认合并',
};

const ACTION_ORDER = ['keep_current', 'use_new', 'keep_all', 'keep_separate', 'merge', 'edit_accept'];

const orderedActions = (actions: string[]) =>
  [...actions].sort((left, right) => {
    const leftRank = ACTION_ORDER.indexOf(left);
    const rightRank = ACTION_ORDER.indexOf(right);
    return (leftRank === -1 ? ACTION_ORDER.length : leftRank) - (rightRank === -1 ? ACTION_ORDER.length : rightRank);
  });

async function readOutcome(
  materialId: number,
  headers: Record<string, string>,
  credentials: RequestCredentials,
): Promise<WikiWriteOutcome | null> {
  const response = await fetch(`/api/proxy/opspilot/chat_wiki_material/${materialId}/outcome/`, {
    credentials,
    headers,
  });
  if (!response.ok) return null;
  const payload = unwrapPlatformPayload(await response.json());
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const record = payload as WikiWriteOutcome;
  return typeof record.phase === 'string' ? record : null;
}

async function submitDecision(
  materialId: number,
  body: Record<string, unknown>,
  headers: Record<string, string>,
  credentials: RequestCredentials,
): Promise<WikiWriteOutcome | null> {
  const response = await fetch(`/api/proxy/opspilot/chat_wiki_material/${materialId}/decide/`, {
    method: 'POST',
    credentials,
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) return null;
  const payload = unwrapPlatformPayload(await response.json());
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const record = payload as WikiWriteOutcome;
  return typeof record.phase === 'string' ? record : null;
}

function WriteCard({
  seed,
  headers,
  credentials,
}: {
  seed: WikiWriteSeed;
  headers: Record<string, string>;
  credentials: RequestCredentials;
}) {
  const [outcome, setOutcome] = useState<WikiWriteOutcome | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const phase = outcome?.phase || seed.phase;
  const summary = outcome?.summary || seed.summary;
  const headersRef = useRef(headers);
  headersRef.current = headers;

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const phaseRef = { current: seed.phase };
    const load = async () => {
      try {
        const data = await readOutcome(seed.material_id, headersRef.current, credentials);
        if (stopped || !data) {
          schedule();
          return;
        }
        phaseRef.current = data.phase;
        setOutcome(data);
        if (data.phase === 'writing') schedule();
      } catch {
        schedule();
      }
    };
    const schedule = () => {
      if (stopped || phaseRef.current !== 'writing') return;
      timer = window.setTimeout(() => {
        void load();
      }, 3000);
    };
    void load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [credentials, seed.material_id, seed.phase]);

  const submit = async (checkId: number, action: string, body?: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const data = await submitDecision(
        seed.material_id,
        { check_id: checkId, action, body },
        headers,
        credentials,
      );
      if (data) {
        setOutcome(data);
        setEditingId(null);
        setDraft('');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const openChecks = phase === 'needs_decision'
    ? (outcome?.checks || []).filter((item) => item.status === 'open')
    : [];

  return (
    <div className="w-full rounded-lg border border-[var(--color-border-1,#edeff3)] bg-white px-3 py-3">
      <div className="text-sm text-[var(--color-text-1,#1d2129)]">{summary}</div>
      {openChecks.map((check) => (
        <div key={check.id} className="mt-3">
          {check.page_title ? <div className="mb-2 text-sm font-medium">{check.page_title}</div> : null}
          <div className="grid grid-cols-2 gap-2">
            <section className="min-w-0 rounded-md bg-[var(--color-fill-1,#f7f8fa)] px-3 py-2">
              <div className="mb-1 text-xs text-[var(--color-text-2,#4e5969)]">现有内容</div>
              <div className="max-h-56 overflow-auto">
                {check.current_body ? <ChatMarkdown content={check.current_body} /> : <span className="text-sm text-[var(--color-text-2,#4e5969)]">无</span>}
              </div>
            </section>
            <section className="min-w-0 rounded-md bg-[var(--color-fill-1,#f7f8fa)] px-3 py-2">
              <div className="mb-1 text-xs text-[var(--color-text-2,#4e5969)]">待确认内容</div>
              <div className="max-h-56 overflow-auto">
                {check.incoming_body ? <ChatMarkdown content={check.incoming_body} /> : <span className="text-sm text-[var(--color-text-2,#4e5969)]">无</span>}
              </div>
            </section>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {orderedActions(check.actions || []).map((action) => (
              <button
                key={action}
                type="button"
                disabled={submitting}
                className={`rounded-md px-3 py-1 text-xs ${action === 'use_new' ? 'bg-[var(--color-primary,#155AEF)] text-white' : 'border border-[var(--color-border-1,#edeff3)] bg-white'}`}
                onClick={() => {
                  if (action === 'edit_accept') {
                    setEditingId(check.id);
                    setDraft(check.incoming_body || '');
                    return;
                  }
                  void submit(check.id, action);
                }}
              >
                {ACTION_LABELS[action] || action}
              </button>
            ))}
          </div>
          {editingId === check.id ? (
            <div className="mt-2">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="mb-2 w-full rounded-md border border-[var(--color-border-1,#edeff3)] px-2 py-1 text-sm"
                rows={4}
              />
              <button
                type="button"
                disabled={!draft.trim() || submitting}
                className="rounded-md bg-[var(--color-primary,#155AEF)] px-3 py-1 text-xs text-white disabled:opacity-50"
                onClick={() => void submit(check.id, 'edit_accept', draft)}
              >
                提交
              </button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function WikiMaterialWriteCards({
  writes,
  headers,
  credentials,
}: {
  writes: WikiWriteSeed[];
  headers: Record<string, string>;
  credentials: RequestCredentials;
}) {
  if (writes.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {writes.map((write) => (
        <WriteCard key={write.material_id} seed={write} headers={headers} credentials={credentials} />
      ))}
    </div>
  );
}
