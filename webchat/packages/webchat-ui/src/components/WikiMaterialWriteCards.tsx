import { ChatMarkdown, useChatContentHost } from '@bk-lite/chat-content/ui';
import { useEffect, useState } from 'react';

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
const DISPLAY_BODY_LIMIT = 4000;
const OUTCOME_RETRY_MS = 3000;

const PHASE_LABEL: Record<string, string> = {
  writing: '写入中',
  needs_decision: '待确认',
  published: '已发布',
  failed: '写入失败',
};

const PHASE_TONE: Record<string, string> = {
  writing: 'text-[var(--color-primary)]',
  needs_decision: 'text-[var(--color-warning)]',
  published: 'text-[var(--color-success)]',
  failed: 'text-[var(--theme-color-status-error)]',
};

const orderedActions = (actions: string[]) =>
  [...actions].sort((left, right) => {
    const leftRank = ACTION_ORDER.indexOf(left);
    const rightRank = ACTION_ORDER.indexOf(right);
    return (leftRank === -1 ? ACTION_ORDER.length : leftRank) - (rightRank === -1 ? ACTION_ORDER.length : rightRank);
  });

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

function asOutcome(value: unknown): WikiWriteOutcome | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as WikiWriteOutcome;
  return typeof record.phase === 'string' ? record : null;
}

function previewBody(body: string): { text: string; truncated: boolean } {
  if (body.length <= DISPLAY_BODY_LIMIT) return { text: body, truncated: false };
  return { text: body.slice(0, DISPLAY_BODY_LIMIT), truncated: true };
}

function knowledgePane(label: string, body: string) {
  const preview = previewBody(body);
  return (
    <section className="min-w-0 rounded-md bg-[var(--color-fill-1,#f7f8fa)] px-3 py-2">
      <div className="mb-1 text-xs text-[var(--color-text-2,#4e5969)]">{label}</div>
      <div className="max-h-56 overflow-auto">
        {preview.text ? <ChatMarkdown content={preview.text} /> : <span className="text-sm text-[var(--color-text-2,#4e5969)]">无</span>}
      </div>
      {preview.truncated ? <div className="mt-1 text-xs text-[var(--color-text-2,#4e5969)]">还有未展示的全文</div> : null}
    </section>
  );
}

function WriteCard({ seed }: { seed: WikiWriteSeed }) {
  const { post } = useChatContentHost();
  const [outcome, setOutcome] = useState<WikiWriteOutcome | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [outcomeError, setOutcomeError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const phase = outcome?.phase || seed.phase;
  const summary = outcome?.summary || seed.summary;

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const phaseRef = { current: seed.phase };

    const schedule = () => {
      if (stopped || phaseRef.current !== 'writing') return;
      timer = window.setTimeout(() => {
        void load();
      }, OUTCOME_RETRY_MS);
    };

    const fail = (error: unknown) => {
      if (stopped) return;
      setOutcomeError(messageFrom(error, '暂时没有拿到写入结果'));
      if (phaseRef.current === 'writing') schedule();
    };

    const load = async () => {
      try {
        if (!post) throw new Error('当前对话不能执行此操作');
        const data = await post<unknown>(`/opspilot/chat_wiki_material/${seed.material_id}/outcome/`, undefined);
        const next = asOutcome(data);
        if (!next) throw new Error('暂时没有拿到写入结果');
        if (stopped) return;
        phaseRef.current = next.phase;
        setOutcome(next);
        setOutcomeError(null);
        if (next.phase === 'writing') schedule();
      } catch (error) {
        fail(error);
      }
    };

    void load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [post, seed.material_id, seed.phase]);

  const submit = async (checkId: number, action: string, body?: string) => {
    if (submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (!post) throw new Error('当前对话不能执行此操作');
      const payload: Record<string, unknown> = { check_id: checkId, action };
      if (body !== undefined) payload.body = body;
      const data = await post<unknown>(`/opspilot/chat_wiki_material/${seed.material_id}/decide/`, payload);
      const next = asOutcome(data);
      if (!next) throw new Error('确认没有写上，请再试一次');
      setOutcome(next);
      setEditingId(null);
      setDraft('');
    } catch (error) {
      setSubmitError(messageFrom(error, '确认没有写上，请再试一次'));
    } finally {
      setSubmitting(false);
    }
  };

  const openChecks = phase === 'needs_decision'
    ? (outcome?.checks || []).filter((item) => item.status === 'open')
    : [];

  return (
    <div className="w-full rounded-lg border border-[var(--color-border-1,#edeff3)] bg-white px-3 py-3">
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-1,#1d2129)]">
        <span className={`shrink-0 text-xs font-medium ${PHASE_TONE[phase] || ''}`}>{PHASE_LABEL[phase] || phase}</span>
        <span>{summary}</span>
      </div>
      {outcomeError ? (
        <div role="alert" className="mt-2 text-xs text-[var(--theme-color-status-error)]">{outcomeError}</div>
      ) : null}
      {openChecks.map((check) => (
        <div key={check.id} className="mt-3">
          {check.page_title ? <div className="mb-2 text-sm font-medium">{check.page_title}</div> : null}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))] gap-2">
            {knowledgePane('现有内容', check.current_body || '')}
            {knowledgePane('待确认内容', check.incoming_body || '')}
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
      {submitError ? (
        <div role="alert" className="mt-2 text-xs text-[var(--theme-color-status-error)]">{submitError}</div>
      ) : null}
    </div>
  );
}

export function WikiMaterialWriteCards({ writes }: { writes: WikiWriteSeed[] }) {
  if (writes.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {writes.map((write) => (
        <WriteCard key={write.material_id} seed={write} />
      ))}
    </div>
  );
}
