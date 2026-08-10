'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { SwapOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Modal, Pagination, Popconfirm, Space, Spin, Tag } from 'antd';
import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';
import { useTranslation } from '@/utils/i18n';
import type {
  CheckDecisionAction,
  CheckDecisionRequest,
  CheckItem,
  DecisionListView,
} from '@/app/opspilot/types/wiki';
import {
  buildDecisionViewModel,
  filterDecisionItems,
  getDecisionActions,
  getDecisionInteractionState,
  isDecisionRuleRevocable,
  resolveDecisionRevokedReason,
  resolveSelectedConflictAlternative,
  type WikiDecisionSnapshot,
  type DecisionSubmittingState,
} from './wikiDecisionModel';
import {
  buildConflictListSubtitle,
  buildKnowledgeConflictDiff,
  formatDiffHighlightLabel,
  type DiffSegment,
  type DiffSegmentStatus,
  type KnowledgeConflictDiff,
} from './wikiDecisionDiff';
import ContributionTag from './ContributionTag';
import { formatWikiTime, pageTypeLabelKey } from './wikiFormat';

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
const markdownHtml = (body: string) => ({ __html: DOMPurify.sanitize(markdown.render(body || '')) });
const MARKDOWN_CLASS =
  'break-words text-sm leading-7 text-[var(--color-text-2)] [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[var(--color-primary-bg-active)] [&_code]:px-1';

const splitSnapshotBody = (body: string) => {
  const lines = body.split('\n');
  const differenceIndex = lines.findLastIndex((line) => /^\s*[-*+]\s+/.test(line));
  if (differenceIndex < 0) return { content: body, difference: '' };
  const difference = lines[differenceIndex]
    .replace(/^\s*[-*+]\s+/, '')
    .replace(/\*\*/g, '')
    .trim();
  return {
    content: lines.filter((_, index) => index !== differenceIndex).join('\n').trim(),
    difference,
  };
};


export interface WikiDecisionCenterProps {
  items: CheckItem[];
  view: DecisionListView;
  total: number;
  page?: number;
  pageSize?: number;
  pendingCount?: number;
  processedCount?: number;
  activeId?: number | null;
  loading?: boolean;
  error?: string;
  outdatedItemId?: number | null;
  submitting?: DecisionSubmittingState | null;
  onViewChange: (view: DecisionListView) => void;
  onSelect?: (item: CheckItem) => void;
  onPageChange?: (page: number) => void;
  onDecide: (item: CheckItem, request: CheckDecisionRequest) => void | Promise<void>;
  onRevoke?: (item: CheckItem) => void | Promise<void>;
  onRefresh?: () => boolean | void | Promise<boolean | void>;
}

const SnapshotMeta = ({
  snapshot,
  incoming,
}: {
  snapshot: WikiDecisionSnapshot;
  incoming: boolean;
}) => {
  const { t } = useTranslation();
  const pageTypeKey = pageTypeLabelKey(snapshot.pageType);
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
      {snapshot.sourceLabel && (
        <span
          className="max-w-full truncate rounded-full px-2.5 py-1"
          style={
            incoming
              ? { background: 'var(--color-primary-bg-active)', color: 'var(--color-primary)' }
              : { background: 'var(--color-fill-2)', color: 'var(--color-text-2)' }
          }
          title={snapshot.sourceLabel}
        >
          {snapshot.sourceLabel}
        </span>
      )}
      {snapshot.pageType && (
        <span className="text-[var(--color-text-3)]">
          {pageTypeKey ? t(pageTypeKey) : snapshot.pageType}
        </span>
      )}
      {snapshot.contribution && <ContributionTag value={snapshot.contribution} />}
    </div>
  );
};

const DIFF_SEGMENT_STYLE: Record<
  DiffSegmentStatus,
  { background?: string; color?: string; boxShadow?: string }
> = {
  equal: {},
  changed: {
    background: 'color-mix(in srgb, var(--color-warning) 18%, transparent)',
    boxShadow: 'inset 3px 0 0 var(--color-warning)',
  },
  removed: {
    background: 'color-mix(in srgb, var(--color-fail) 14%, transparent)',
    boxShadow: 'inset 3px 0 0 var(--color-fail)',
  },
  added: {
    background: 'color-mix(in srgb, var(--color-success) 16%, transparent)',
    boxShadow: 'inset 3px 0 0 var(--color-success)',
  },
};

const DiffSegmentList = ({ segments }: { segments: DiffSegment[] }) => {
  if (!segments.length) {
    return <div className="flex min-h-24 items-center justify-center text-sm text-[var(--color-text-3)]">--</div>;
  }
  return (
    <div className="min-h-24 space-y-2 text-sm leading-7 text-[var(--color-text-2)]">
      {segments.map((segment, index) => (
        <p
          key={`${segment.status}-${index}-${segment.text.slice(0, 24)}`}
          className="m-0 whitespace-pre-wrap break-words rounded-md px-2 py-1"
          style={DIFF_SEGMENT_STYLE[segment.status]}
        >
          {segment.text}
        </p>
      ))}
    </div>
  );
};

const DiffSnapshotCard = ({
  snapshot,
  eyebrow,
  incoming,
  segments,
  sourceCountLabel,
  relationCountLabel,
  contentLabel,
}: {
  snapshot: WikiDecisionSnapshot;
  eyebrow: string;
  incoming: boolean;
  segments: DiffSegment[];
  sourceCountLabel: string;
  relationCountLabel: string;
  contentLabel: string;
}) => (
  <section
    className="min-w-0 overflow-hidden rounded-[14px] border"
    style={{
      borderTopWidth: 3,
      borderColor: 'var(--color-border-1)',
      borderTopColor: incoming ? 'var(--color-primary)' : 'var(--color-text-3)',
      background: 'var(--color-bg)',
    }}
  >
    <div className="flex min-h-16 items-start justify-between gap-3 border-b border-[var(--color-border-1)] px-4 py-3">
      <div className="min-w-0">
        <div className="mb-1 text-xs text-[var(--color-text-3)]">{eyebrow}</div>
        <div className="truncate text-base font-bold leading-6 text-[var(--color-text-1)]" title={snapshot.title}>
          {snapshot.title || '--'}
        </div>
      </div>
      {snapshot.versionLabel && (
        <Tag
          bordered={false}
          className="m-0 shrink-0 rounded-md"
          style={
            incoming
              ? { color: 'var(--color-primary)', background: 'var(--color-primary-bg-active)' }
              : { color: 'var(--color-text-2)', background: 'var(--color-fill-2)' }
          }
        >
          {snapshot.versionLabel}
        </Tag>
      )}
    </div>

    <div className="px-4 py-4">
      <SnapshotMeta snapshot={snapshot} incoming={incoming} />

      <div className="mb-2 text-sm font-bold text-[var(--color-text-1)]">{contentLabel}</div>
      <DiffSegmentList segments={segments} />

      {(snapshot.sourceCount !== undefined || snapshot.relationCount !== undefined) && (
        <div className="mt-4 flex flex-wrap gap-5 border-t border-[var(--color-border)] pt-3 text-xs text-[var(--color-text-3)]">
          {snapshot.sourceCount !== undefined && (
            <span>{sourceCountLabel}: <span className="tabular-nums">{snapshot.sourceCount}</span></span>
          )}
          {snapshot.relationCount !== undefined && (
            <span>{relationCountLabel}: <span className="tabular-nums">{snapshot.relationCount}</span></span>
          )}
        </div>
      )}
    </div>
  </section>
);

const SnapshotCard = ({
  snapshot,
  eyebrow,
  incoming,
  sourceCountLabel,
  relationCountLabel,
  contentLabel,
}: {
  snapshot: WikiDecisionSnapshot;
  eyebrow: string;
  incoming: boolean;
  sourceCountLabel: string;
  relationCountLabel: string;
  contentLabel: string;
}) => {
  const { content, difference } = splitSnapshotBody(snapshot.body);
  return (
  <section
    className="min-w-0 overflow-hidden rounded-[14px] border"
    style={{
      borderTopWidth: 3,
      borderColor: 'var(--color-border-1)',
      borderTopColor: incoming ? 'var(--color-primary)' : 'var(--color-text-3)',
      background: 'var(--color-bg)',
    }}
  >
    <div className="flex min-h-16 items-start justify-between gap-3 border-b border-[var(--color-border-1)] px-4 py-3">
      <div className="min-w-0">
        <div className="mb-1 text-xs text-[var(--color-text-3)]">{eyebrow}</div>
        <div className="truncate text-base font-bold leading-6 text-[var(--color-text-1)]" title={snapshot.title}>
          {snapshot.title || '--'}
        </div>
      </div>
      {snapshot.versionLabel && (
        <Tag
          bordered={false}
          className="m-0 shrink-0 rounded-md"
          style={
            incoming
              ? { color: 'var(--color-primary)', background: 'var(--color-primary-bg-active)' }
              : { color: 'var(--color-text-2)', background: 'var(--color-fill-2)' }
          }
        >
          {snapshot.versionLabel}
        </Tag>
      )}
    </div>

    <div className="px-4 py-4">
      <SnapshotMeta snapshot={snapshot} incoming={incoming} />

      <div className="mb-2 text-sm font-bold text-[var(--color-text-1)]">{contentLabel}</div>
      {content ? (
        <div className={`${MARKDOWN_CLASS} min-h-24`} dangerouslySetInnerHTML={markdownHtml(content)} />
      ) : (
        <div className="flex min-h-24 items-center justify-center text-sm text-[var(--color-text-3)]">--</div>
      )}

      {difference && (
        <div
          className="mt-3 flex items-start gap-3 rounded-[9px] px-3 py-2.5 text-sm leading-6"
          style={{
            background: 'var(--color-fill-1)',
            color: 'var(--color-text-2)',
          }}
        >
          <span className="font-bold" style={{ color: incoming ? 'var(--color-success)' : 'var(--color-fail)' }}>
            {incoming ? '+' : '−'}
          </span>
          <span>{difference}</span>
        </div>
      )}

      {(snapshot.sourceCount !== undefined || snapshot.relationCount !== undefined) && (
        <div className="mt-4 flex flex-wrap gap-5 border-t border-[var(--color-border)] pt-3 text-xs text-[var(--color-text-3)]">
          {snapshot.sourceCount !== undefined && (
            <span>{sourceCountLabel}: <span className="tabular-nums">{snapshot.sourceCount}</span></span>
          )}
          {snapshot.relationCount !== undefined && (
            <span>{relationCountLabel}: <span className="tabular-nums">{snapshot.relationCount}</span></span>
          )}
        </div>
      )}
    </div>
  </section>
  );
};

const ComparisonConnector = () => (
  <div className="hidden h-10 w-10 self-center items-center justify-center rounded-full border border-[var(--color-border-2)] bg-[var(--color-primary-bg-active)] text-[var(--color-primary)] xl:flex">
    <SwapOutlined aria-hidden="true" />
  </div>
);

const WikiDecisionCenter: React.FC<WikiDecisionCenterProps> = ({
  items,
  view,
  total,
  page = 1,
  pageSize = 20,
  pendingCount = 0,
  processedCount = 0,
  activeId,
  loading = false,
  error,
  outdatedItemId,
  submitting,
  onViewChange,
  onSelect,
  onPageChange,
  onDecide,
  onRevoke,
  onRefresh,
}) => {
  const { t } = useTranslation();
  const [editingItem, setEditingItem] = useState<CheckItem | null>(null);
  const [editBody, setEditBody] = useState('');
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const currentCount = view === 'pending' ? pendingCount : processedCount;
  const decisionItems = useMemo(() => filterDecisionItems(items), [items]);
  const activeItem = useMemo(
    () => decisionItems.find((item) => item.id === activeId) || decisionItems[0] || null,
    [activeId, decisionItems]
  );
  const model = useMemo(() => (activeItem ? buildDecisionViewModel(activeItem) : null), [activeItem]);
  const candidateAlternatives = useMemo(
    () => (model?.kind === 'knowledge_conflict'
      ? model.alternatives.filter((alt) => alt.kind !== 'current')
      : []),
    [model],
  );
  const selectedAlternative = useMemo(() => {
    if (!activeItem || !model || model.kind !== 'knowledge_conflict') return null;
    return (
      resolveSelectedConflictAlternative(activeItem, selectedMaterialId) ||
      candidateAlternatives[0] ||
      model.incoming
    );
  }, [activeItem, candidateAlternatives, model, selectedMaterialId]);
  const conflictDiff = useMemo<KnowledgeConflictDiff | null>(() => {
    if (!model || model.kind !== 'knowledge_conflict' || !selectedAlternative) return null;
    return buildKnowledgeConflictDiff(model.current.body, selectedAlternative.body);
  }, [model, selectedAlternative]);
  useEffect(() => {
    if (!activeItem || !model || model.kind !== 'knowledge_conflict') {
      setSelectedMaterialId(null);
      return;
    }
    const preferred =
      resolveSelectedConflictAlternative(activeItem, null)?.materialId ??
      candidateAlternatives[0]?.materialId ??
      null;
    setSelectedMaterialId(preferred ?? null);
  }, [activeItem, candidateAlternatives, model]);
  const highlightLabels = useMemo(
    () => ({
      added: t('wiki.decisionDiffAddedPrefix'),
      removed: t('wiki.decisionDiffRemovedPrefix'),
      changed: t('wiki.decisionDiffChangedTemplate'),
    }),
    [t],
  );
  const activeInteraction = useMemo(
    () => activeItem ? getDecisionInteractionState(activeItem, submitting, outdatedItemId) : null,
    [activeItem, outdatedItemId, submitting]
  );
  const editingInteraction = useMemo(
    () => editingItem ? getDecisionInteractionState(editingItem, submitting, outdatedItemId) : null,
    [editingItem, outdatedItemId, submitting]
  );
  const revokedReasonText = useMemo(() => {
    const reason = resolveDecisionRevokedReason(activeItem?.decision_rule?.revoked_reason);
    if (!reason.fallback) return '';
    return reason.translationKey ? t(reason.translationKey) : reason.fallback;
  }, [activeItem, t]);

  const actionLabel = (action?: CheckDecisionAction) => {
    const keys: Partial<Record<CheckDecisionAction, string>> = {
      keep_current: 'wiki.decisionKeepCurrent',
      use_new: 'wiki.decisionUseNew',
      edit_accept: 'wiki.decisionEditAccept',
      keep_separate: 'wiki.decisionKeepSeparate',
      merge: 'wiki.decisionMerge',
    };
    return action && keys[action] ? t(keys[action]) : action || '--';
  };

  const openEditor = (item: CheckItem) => {
    const itemModel = buildDecisionViewModel(item);
    if (!itemModel || !getDecisionInteractionState(item, submitting, outdatedItemId).canEditSubmit) return;
    const selected = resolveSelectedConflictAlternative(item, selectedMaterialId);
    setEditingItem(item);
    setEditBody(selected?.body || item.candidate?.body || itemModel.incoming.body);
  };

  const submitDecision = async (item: CheckItem, request: CheckDecisionRequest) => {
    const interaction = getDecisionInteractionState(item, submitting, outdatedItemId);
    if (!interaction.canDecide) return false;
    try {
      await onDecide(item, request);
      return true;
    } catch {
      return false;
    }
  };

  const buildConflictDecisionRequest = (
    item: CheckItem,
    action: CheckDecisionAction,
    body?: string,
  ): CheckDecisionRequest | null => {
    if (action === 'keep_current') return { action };
    const selected = resolveSelectedConflictAlternative(item, selectedMaterialId);
    const materialId = selected?.materialId;
    const candidates = getDecisionActions(item).includes('use_new')
      ? (buildDecisionViewModel(item)?.alternatives || []).filter((alt) => alt.kind !== 'current')
      : [];
    if (candidates.length > 1 && materialId == null) return null;
    return {
      action,
      ...(body !== undefined ? { body } : {}),
      ...(materialId != null ? { material_id: materialId } : {}),
    };
  };

  const submitEditedBody = async () => {
    if (!editingItem || !editBody.trim() || !editingInteraction?.canEditSubmit) return;
    const request = buildConflictDecisionRequest(editingItem, 'edit_accept', editBody.trim());
    if (!request) return;
    const saved = await submitDecision(editingItem, request);
    if (!saved) return;
    setEditingItem(null);
    setEditBody('');
  };

  const isSubmitting = (item: CheckItem, action: CheckDecisionAction | 'revoke') =>
    submitting?.checkId === item.id && submitting.action === action;

  const renderPendingFooter = (item: CheckItem) => {
    const actions = getDecisionActions(item);
    const interaction = getDecisionInteractionState(item, submitting, outdatedItemId);
    if (interaction.requiresContextRefresh) {
      return (
        <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
          <span className="text-xs leading-5 text-[var(--color-text-3)]">
            {t('wiki.decisionContextOutdated')}
          </span>
          {onRefresh && (
            <Button size="small" loading={loading} onClick={() => void onRefresh()}>
              {t('wiki.decisionRefresh')}
            </Button>
          )}
        </div>
      );
    }
    return (
      <div className="flex min-h-[58px] flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
        <div className="text-xs leading-5 text-[var(--color-text-3)]">
          {model?.kind === 'knowledge_conflict'
            ? t('wiki.decisionKnowledgeEffect')
            : t('wiki.decisionIdentityEffect')}
        </div>
        <Space size={8} wrap>
          {actions.map((action) => (
            <Button
              key={action}
              type={action === 'use_new' || action === 'merge' ? 'primary' : 'default'}
              loading={isSubmitting(item, action)}
              disabled={
                !interaction.canDecide ||
                (model?.kind === 'knowledge_conflict' &&
                  action !== 'keep_current' &&
                  candidateAlternatives.length > 1 &&
                  selectedMaterialId == null)
              }
              onClick={() => {
                if (action === 'edit_accept') {
                  openEditor(item);
                  return;
                }
                const request =
                  model?.kind === 'knowledge_conflict'
                    ? buildConflictDecisionRequest(item, action)
                    : { action };
                if (!request) return;
                void submitDecision(item, request);
              }}
            >
              {actionLabel(action)}
            </Button>
          ))}
        </Space>
      </div>
    );
  };

  const renderProcessedSummary = (item: CheckItem) => {
    const rule = item.decision_rule;
    const ruleActive = rule?.status === 'active';
    const lastReplay = formatWikiTime(rule?.last_replayed_at);
    return (
      <div
        className="mt-4 rounded-xl border px-4 py-3.5"
        style={
          ruleActive
            ? {
              borderColor: 'color-mix(in srgb, var(--color-success) 32%, var(--color-border))',
              background: 'color-mix(in srgb, var(--color-success) 6%, var(--color-bg))',
            }
            : { borderColor: 'var(--color-border)', background: 'var(--color-fill-1)' }
        }
      >
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <div className="min-w-0">
            <div className="mb-1 text-xs text-[var(--color-text-3)]">{t('wiki.decisionAction')}</div>
            <div className="text-sm font-semibold text-[var(--color-text-1)]">
              {actionLabel(item.decision_action || rule?.action)}
            </div>
          </div>
          {(item.decision_operator || item.decision_processed_at) && (
            <div className="min-w-0">
              <div className="mb-1 text-xs text-[var(--color-text-3)]">
                {t('wiki.decisionOperator')} · {t('wiki.decisionProcessedAt')}
              </div>
              <div className="text-sm font-semibold text-[var(--color-text-1)]">
                {[item.decision_operator, formatWikiTime(item.decision_processed_at)].filter(Boolean).join(' · ')}
              </div>
            </div>
          )}
          {rule && (
            <div className="min-w-0">
              <div className="mb-1 text-xs text-[var(--color-text-3)]">{t('wiki.decisionAutoReuse')}</div>
              <div
                className="text-sm font-semibold"
                style={{ color: ruleActive ? 'var(--color-success)' : 'var(--color-text-3)' }}
              >
                {ruleActive
                  ? rule.replay_count > 0 && lastReplay
                    ? t('wiki.decisionReusedSummary').replace('{count}', String(rule.replay_count)).replace('{time}', lastReplay)
                    : t('wiki.decisionRuleActive')
                  : t('wiki.decisionReuseStoppedSummary').replace('{count}', String(rule.replay_count))}
              </div>
            </div>
          )}
          <div className="ml-auto flex items-center">
            {rule && isDecisionRuleRevocable(rule) && onRevoke ? (
              <Popconfirm
                title={t('wiki.decisionRevokeRuleConfirm')}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={() => onRevoke(item)}
              >
                <Button danger size="small" loading={isSubmitting(item, 'revoke')}>
                  {t('wiki.decisionRevokeRule')}
                </Button>
              </Popconfirm>
            ) : rule && !ruleActive ? (
              <Tag
                bordered={false}
                className="m-0 rounded-md"
                style={{ color: 'var(--color-text-3)', background: 'var(--color-fill-2)' }}
              >
                {t('wiki.decisionRuleRevoked')}
              </Tag>
            ) : null}
          </div>
        </div>
      </div>
    );
  };

  const renderProcessedNoteFooter = (item: CheckItem) => (
    <div className="flex min-h-[58px] flex-wrap items-center gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
      <span className="text-xs leading-5 text-[var(--color-text-3)]">
        {item.decision_rule?.status === 'active'
          ? t('wiki.decisionRuleReuseNote')
          : t('wiki.decisionHistoryTraceNote')}
      </span>
    </div>
  );

  return (
    <main className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] lg:h-full">
      <header className="flex min-h-[76px] flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border)] px-5 py-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="m-0 text-xl font-bold leading-6 text-[var(--color-text-1)]">
              {view === 'pending' ? t('wiki.decisionCenterTitle') : t('wiki.decisionRecordTitle')}
            </h2>
            {currentCount > 0 && (
              <span className="inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-md bg-[var(--color-primary-bg-active)] px-1.5 text-xs font-bold tabular-nums text-[var(--color-primary)]">
                {view === 'pending' ? pendingCount : processedCount}
              </span>
            )}
          </div>
          <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">
            {view === 'pending' ? t('wiki.decisionCenterSubtitle') : t('wiki.decisionRecordSubtitle')}
          </p>
        </div>
        <Button onClick={() => onViewChange(view === 'pending' ? 'processed' : 'pending')}>
          {view === 'pending' ? t('wiki.decisionViewHistory') : t('wiki.decisionBackPending')}
        </Button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[330px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col overflow-hidden border-b border-[var(--color-border)] bg-[var(--color-bg)] p-3.5 lg:border-b-0 lg:border-r">
          <div className="flex items-center justify-between px-1 pb-3 pt-0.5">
            <span className="text-[13px] font-bold text-[var(--color-text-1)]">
              {view === 'pending' ? t('wiki.decisionListTitlePending') : t('wiki.decisionListTitleProcessed')}
            </span>
            <span className="text-xs text-[var(--color-text-3)]">
              {t('wiki.decisionListTotal').replace('{count}', String(total))}
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <Spin spinning={loading} className="min-h-48">
              <div className="space-y-2">
                {decisionItems.map((item) => {
                  const itemModel = buildDecisionViewModel(item);
                  if (!itemModel) return null;
                  const active = item.id === activeItem?.id;
                  const itemDiff =
                    itemModel.kind === 'knowledge_conflict'
                      ? buildKnowledgeConflictDiff(
                        itemModel.current.body,
                        itemModel.incoming.body,
                      )
                      : null;
                  const listSummary =
                    itemModel.kind === 'knowledge_conflict'
                      ? buildConflictListSubtitle(
                        itemModel.triggerSource,
                        itemDiff?.highlights[0],
                        highlightLabels,
                      ) ||
                        itemModel.summary ||
                        t('wiki.decisionKnowledgeSummaryFallback')
                      : itemModel.summary || t('wiki.decisionIdentitySummaryFallback');
                  return (
                    <button
                      key={item.id}
                      disabled={Boolean(submitting)}
                      type="button"
                      aria-pressed={active}
                      onClick={() => onSelect?.(item)}
                      className={`w-full rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] ${
                        active
                          ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]'
                          : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-3)]'
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <Tag bordered={false} color={view === 'processed' ? 'success' : itemModel.kind === 'knowledge_conflict' ? 'orange' : 'blue'} className="m-0 rounded-md">
                          {view === 'processed'
                            ? t('wiki.decisionProcessed')
                            : itemModel.kind === 'knowledge_conflict'
                              ? t('wiki.decisionKnowledgeConflict')
                              : t('wiki.decisionPageIdentity')}
                        </Tag>
                        <span className="text-xs tabular-nums text-[var(--color-text-3)]">
                          {formatWikiTime(item.updated_at || item.created_at)}
                        </span>
                      </div>
                      <div className="truncate text-sm font-bold leading-6 text-[var(--color-text-1)]" title={itemModel.title}>
                        {itemModel.title || '--'}
                      </div>
                      <p className="mb-0 mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-3)]" title={listSummary}>
                        {listSummary}
                      </p>
                    </button>
                  );
                })}
                {!loading && items.length === 0 && (
                  <div className="rounded-lg bg-[var(--color-bg)] py-12">
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={view === 'pending' ? t('wiki.decisionEmptyPending') : t('wiki.decisionEmptyProcessed')}
                    />
                  </div>
                )}
              </div>
            </Spin>
          </div>

          {total > pageSize && onPageChange && (
            <Pagination
              disabled={Boolean(submitting)}
              simple
              className="mt-auto pt-3"
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={onPageChange}
            />
          )}
        </aside>

        <section className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--color-bg)]">
          {error && <Alert type="error" showIcon message={error} className="m-4 mb-0" />}
          {activeItem && model ? (
            <>
              <div className="flex-1 overflow-y-auto px-5 py-5">
                <div className="mb-4 min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Tag bordered={false} color={model.kind === 'knowledge_conflict' ? 'orange' : 'blue'} className="m-0 rounded-md">
                      {model.kind === 'knowledge_conflict'
                        ? t('wiki.decisionKnowledgeConflict')
                        : t('wiki.decisionPageIdentity')}
                    </Tag>
                    <Tag bordered={false} color={activeItem.status === 'open' ? 'warning' : 'success'} className="m-0 rounded-md">
                      {activeItem.status === 'open' ? t('wiki.decisionPending') : t('wiki.decisionProcessed')}
                    </Tag>
                  </div>
                  <h3 className="m-0 text-lg font-bold leading-7 text-[var(--color-text-1)]">{model.title || '--'}</h3>
                  <p className="mb-0 mt-1 text-sm leading-6 text-[var(--color-text-2)]">
                    {model.summary || (model.kind === 'knowledge_conflict'
                      ? t('wiki.decisionKnowledgeSummaryFallback')
                      : t('wiki.decisionIdentitySummaryFallback'))}
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-border)] md:grid-cols-2 xl:grid-cols-4">
                  {[
                    { label: t('wiki.decisionWhyNeeded'), value: model.reason || (model.kind === 'knowledge_conflict' ? t('wiki.decisionReasonConflictFallback') : t('wiki.decisionReasonIdentityFallback')), labelColor: 'var(--color-primary)' },
                    { label: t('wiki.decisionTriggerSource'), value: model.triggerSource || t('wiki.decisionSourceUnknown'), labelColor: 'var(--color-primary)' },
                    { label: t('wiki.decisionImpactScope'), value: model.impactScope || (model.kind === 'knowledge_conflict' ? t('wiki.decisionImpactConflictFallback') : t('wiki.decisionImpactIdentityFallback')), labelColor: 'var(--color-primary)' },
                    { label: t('wiki.decisionRecoverability'), value: model.recoverability || (model.kind === 'knowledge_conflict' ? t('wiki.decisionRecoveryConflictFallback') : t('wiki.decisionRecoveryIdentityFallback')), labelColor: 'var(--color-success)' },
                  ].map(({ label, value, labelColor }) => (
                    <div key={label} className="min-w-0 bg-[var(--color-fill-1)] px-4 py-3.5">
                      <div className="mb-1 text-xs font-medium" style={{ color: labelColor }}>{label}</div>
                      <div className="truncate text-sm font-semibold text-[var(--color-text-1)]" title={value}>{value}</div>
                    </div>
                  ))}
                </div>

                {activeItem.status !== 'open' && renderProcessedSummary(activeItem)}

                {(activeInteraction?.isOutdated || activeInteraction?.requiresContextRefresh) && (
                  <Alert
                    type="warning"
                    showIcon
                    className="mt-4"
                    message={activeInteraction.requiresContextRefresh
                      ? t('wiki.decisionContextOutdated')
                      : t('wiki.decisionOutdated')}
                    action={onRefresh ? (
                      <Button size="small" loading={loading} onClick={() => void onRefresh()}>
                        {t('wiki.decisionRefresh')}
                      </Button>
                    ) : undefined}
                  />
                )}

                <div className="mb-2 mt-5 text-sm font-semibold text-[var(--color-text-1)]">
                  {model.kind === 'knowledge_conflict' ? t('wiki.decisionCompareKnowledge') : t('wiki.decisionCompareIdentity')}
                </div>
                {model.kind === 'knowledge_conflict' && candidateAlternatives.length > 1 && (
                  <div className="mb-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                    <div className="mb-2 text-xs font-semibold text-[var(--color-text-1)]">
                      {t('wiki.decisionChooseAlternative')}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {candidateAlternatives.map((alt) => {
                        const active = alt.materialId != null && alt.materialId === selectedMaterialId;
                        return (
                          <Button
                            key={`${alt.materialId ?? 'x'}-${alt.candidateVersionId ?? alt.versionLabel}`}
                            size="small"
                            type={active ? 'primary' : 'default'}
                            disabled={activeItem.status !== 'open' || alt.materialId == null}
                            onClick={() => setSelectedMaterialId(alt.materialId ?? null)}
                          >
                            {alt.sourceLabel || `${t('wiki.decisionNewKnowledge')} #${alt.materialId}`}
                          </Button>
                        );
                      })}
                    </div>
                    <p className="mb-0 mt-2 text-xs leading-5 text-[var(--color-text-3)]">
                      {t('wiki.decisionChooseCandidateHint')}
                    </p>
                  </div>
                )}
                {model.kind === 'knowledge_conflict' && conflictDiff && conflictDiff.highlights.length > 0 && (
                  <div className="mb-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-fill-1)] px-4 py-3">
                    <div className="mb-1.5 text-xs font-semibold text-[var(--color-text-1)]">
                      {t('wiki.decisionDiffPoints')}
                    </div>
                    <ul className="mb-0 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--color-text-2)]">
                      {conflictDiff.highlights.map((highlight, index) => (
                        <li key={`point-${highlight.kind}-${index}`}>
                          {formatDiffHighlightLabel(highlight, highlightLabels)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_40px_minmax(0,1fr)] xl:items-stretch">
                  {model.kind === 'knowledge_conflict' && conflictDiff && selectedAlternative ? (
                    <>
                      <DiffSnapshotCard
                        snapshot={model.current}
                        eyebrow={t('wiki.decisionCurrentKnowledge')}
                        incoming={false}
                        segments={conflictDiff.leftSegments}
                        sourceCountLabel={t('wiki.decisionSourceCount')}
                        relationCountLabel={t('wiki.decisionRelationCount')}
                        contentLabel={t('wiki.decisionKnowledgeContent')}
                      />
                      <ComparisonConnector />
                      <DiffSnapshotCard
                        snapshot={selectedAlternative}
                        eyebrow={t('wiki.decisionNewKnowledge')}
                        incoming
                        segments={conflictDiff.rightSegments}
                        sourceCountLabel={t('wiki.decisionSourceCount')}
                        relationCountLabel={t('wiki.decisionRelationCount')}
                        contentLabel={t('wiki.decisionKnowledgeContent')}
                      />
                    </>
                  ) : (
                    <>
                      <SnapshotCard
                        snapshot={model.current}
                        eyebrow={t('wiki.decisionCurrentKnowledge')}
                        incoming={false}
                        sourceCountLabel={t('wiki.decisionSourceCount')}
                        relationCountLabel={t('wiki.decisionRelationCount')}
                        contentLabel={t('wiki.decisionKnowledgeContent')}
                      />
                      <ComparisonConnector />
                      <SnapshotCard
                        snapshot={selectedAlternative || model.incoming}
                        eyebrow={t('wiki.decisionNewKnowledge')}
                        incoming
                        sourceCountLabel={t('wiki.decisionSourceCount')}
                        relationCountLabel={t('wiki.decisionRelationCount')}
                        contentLabel={t('wiki.decisionKnowledgeContent')}
                      />
                    </>
                  )}
                </div>

                {activeItem.status !== 'open' && revokedReasonText && (
                  <Alert
                    type="warning"
                    showIcon
                    className="mt-3"
                    message={`${t('wiki.decisionRevokedReason')}: ${revokedReasonText}`}
                  />
                )}
              </div>

              {activeItem.status === 'open' ? renderPendingFooter(activeItem) : renderProcessedNoteFooter(activeItem)}
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center p-8">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={view === 'pending' ? t('wiki.decisionEmptyPending') : t('wiki.decisionEmptyProcessed')}
              />
            </div>
          )}
        </section>
      </div>

      <Modal
        title={t('wiki.decisionEditAcceptTitle')}
        open={!!editingItem}
        width={760}
        okText={t('wiki.decisionEditAccept')}
        cancelText={t('common.cancel')}
        onCancel={() => {
          setEditingItem(null);
          setEditBody('');
        }}
        onOk={() => void submitEditedBody()}
        okButtonProps={{
          disabled: !editBody.trim() || !editingInteraction?.canEditSubmit,
          loading: editingItem ? isSubmitting(editingItem, 'edit_accept') : false,
        }}
        styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      >
        {editingInteraction?.isOutdated && (
          <Alert
            type="warning"
            showIcon
            className="mb-4"
            message={t('wiki.decisionOutdated')}
            action={onRefresh ? (
              <Button size="small" loading={loading} onClick={() => void onRefresh()}>
                {t('wiki.decisionRefresh')}
              </Button>
            ) : undefined}
          />
        )}
        <label htmlFor="wiki-decision-edited-body" className="mb-2 block text-sm font-medium text-[var(--color-text-1)]">
          {t('wiki.decisionEditAcceptTip')}
        </label>
        <Input.TextArea
          id="wiki-decision-edited-body"
          value={editBody}
          onChange={(event) => setEditBody(event.target.value)}
          autoSize={{ minRows: 10, maxRows: 20 }}
          maxLength={200000}
          showCount
          placeholder={t('wiki.decisionEditAcceptPlaceholder')}
        />
      </Modal>
    </main>
  );
};

export default WikiDecisionCenter;
