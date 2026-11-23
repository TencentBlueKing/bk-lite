'use client';

import React, { useEffect, useState } from 'react';
import { Button, Input } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { ChatMarkdown } from '@bk-lite/chat-content/ui';
import useApiClient from '@/utils/request';

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
  pages?: Array<{ id: number; title: string }>;
  checks?: WikiWriteCheck[];
}

interface WikiMaterialWriteCardProps {
  materialId: number;
  phase: string;
  summary: string;
  readOnly?: boolean;
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

const previewBody = (body: string) => {
  if (body.length <= DISPLAY_BODY_LIMIT) {
    return { text: body, truncated: false };
  }
  return { text: body.slice(0, DISPLAY_BODY_LIMIT), truncated: true };
};

const orderedActions = (actions: string[]) =>
  [...actions].sort((left, right) => {
    const leftRank = ACTION_ORDER.indexOf(left);
    const rightRank = ACTION_ORDER.indexOf(right);
    return (leftRank === -1 ? ACTION_ORDER.length : leftRank) - (rightRank === -1 ? ACTION_ORDER.length : rightRank);
  });

const WikiMaterialWriteCard: React.FC<WikiMaterialWriteCardProps> = ({
  materialId,
  phase: initialPhase,
  summary: initialSummary,
  readOnly = false,
}) => {
  const { get, post } = useApiClient();
  const [outcome, setOutcome] = useState<WikiWriteOutcome | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [pendingAction, setPendingAction] = useState('');

  const phase = outcome?.phase || initialPhase;
  const summary = outcome?.summary || initialSummary;

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const phaseRef = { current: initialPhase };

    const schedule = () => {
      if (stopped || phaseRef.current !== 'writing') return;
      timer = window.setTimeout(() => {
        void load();
      }, 3000);
    };

    const load = async () => {
      try {
        const data = await get<WikiWriteOutcome>(
          `/opspilot/chat_wiki_material/${materialId}/outcome/`,
          { suppressErrorNotification: true },
        );
        if (stopped || !data || typeof data.phase !== 'string') {
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

    void load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [get, initialPhase, materialId]);

  const submit = async (checkId: number, action: string, body?: string) => {
    if (readOnly || submitting) return;
    setSubmitting(true);
    setPendingAction(action);
    try {
      const data = await post<WikiWriteOutcome>(
        `/opspilot/chat_wiki_material/${materialId}/decide/`,
        { check_id: checkId, action, body },
      );
      if (data && typeof data.phase === 'string') {
        setOutcome(data);
        setEditingId(null);
        setDraft('');
      }
    } catch {
      // 请求层已经提示失败。
    } finally {
      setSubmitting(false);
      setPendingAction('');
    }
  };

  const icon = () => {
    if (phase === 'published') return <CheckCircleOutlined className="text-[var(--color-success)]" />;
    if (phase === 'failed') return <CloseCircleOutlined className="text-[var(--theme-color-status-error)]" />;
    if (phase === 'needs_decision') return <ExclamationCircleOutlined className="text-[var(--color-warning)]" />;
    return <LoadingOutlined className="text-[var(--color-primary)]" />;
  };

  const openChecks = phase === 'needs_decision'
    ? (outcome?.checks || []).filter((item) => item.status === 'open')
    : [];

  const withoutRepeatedTitle = (body: string, title?: string) => {
    const trimmed = body.trim();
    if (!title) return trimmed;
    const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return trimmed.replace(new RegExp(`^#{1,6}\\s+${escaped}\\s*`), '').trim();
  };

  const knowledgePane = (label: string, body: string, title?: string) => {
    const preview = previewBody(body);
    const content = withoutRepeatedTitle(preview.text, title);
    return (
      <section className="min-w-0 rounded-md bg-[var(--color-fill-1)] px-3 py-2">
        <div className="mb-1 text-xs text-[var(--color-text-2)]">{label}</div>
        <div className="max-h-56 overflow-auto [&_.chat-markdown>:first-child]:mt-0">
          {content ? <ChatMarkdown content={content} /> : <span className="text-sm text-[var(--color-text-2)]">无</span>}
        </div>
        {preview.truncated ? <div className="mt-1 text-xs text-[var(--color-text-2)]">还有未展示的全文</div> : null}
      </section>
    );
  };

  return (
    <div className="my-2 w-full rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 py-3">
      <div className="mb-3 flex items-center gap-2 text-sm">
        {icon()}
        <span>{summary}</span>
      </div>
      {openChecks.map((check) => (
        <div key={check.id} className="mb-2">
          {check.page_title ? (
            <div className="mb-2 text-sm font-medium">{check.page_title}</div>
          ) : null}
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {knowledgePane('现有内容', check.current_body || '', check.page_title)}
            {knowledgePane('待确认内容', check.incoming_body || '', check.page_title)}
          </div>
          {!readOnly && (
            <div className="mt-3 flex flex-wrap gap-2">
              {orderedActions(check.actions || []).map((action) => (
                <Button
                  key={action}
                  size="small"
                  type={action === 'use_new' ? 'primary' : 'default'}
                  loading={submitting && pendingAction === action}
                  disabled={submitting && pendingAction !== action}
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
                </Button>
              ))}
            </div>
          )}
          {!readOnly && editingId === check.id && (
            <div className="mt-2">
              <Input.TextArea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                autoSize={{ minRows: 4, maxRows: 10 }}
                className="mb-2"
              />
              <Button
                size="small"
                type="primary"
                loading={submitting && pendingAction === 'edit_accept'}
                disabled={!draft.trim() || submitting}
                onClick={() => void submit(check.id, 'edit_accept', draft)}
              >
                提交
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

export default WikiMaterialWriteCard;
