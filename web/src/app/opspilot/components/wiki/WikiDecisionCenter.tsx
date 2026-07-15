'use client';

import React, { useMemo, useState } from 'react';
import { InfoCircleOutlined, SwapOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Modal, Pagination, Popconfirm, Segmented, Space, Spin, Tag, Tooltip } from 'antd';
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
  type WikiDecisionSnapshot,
  type DecisionSubmittingState,
} from './wikiDecisionModel';

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
const markdownHtml = (body: string) => ({ __html: DOMPurify.sanitize(markdown.render(body || '')) });
const MARKDOWN_CLASS =
  'break-words text-sm leading-7 text-[var(--color-text-2)] [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[var(--color-primary-bg-active)] [&_code]:px-1';


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

const formatTimestamp = (value?: string | null) => value?.replace('T', ' ').slice(0, 16) || '';

const SnapshotCard = ({
  snapshot,
  eyebrow,
  incoming,
  sourceCountLabel,
  relationCountLabel,
}: {
  snapshot: WikiDecisionSnapshot;
  eyebrow: string;
  incoming: boolean;
  sourceCountLabel: string;
  relationCountLabel: string;
}) => (
  <section
    className={`min-w-0 overflow-hidden rounded-xl border ${
      incoming
        ? 'border-[color-mix(in_srgb,var(--color-primary)_42%,var(--color-border))] bg-[var(--color-primary-bg-active)]'
        : 'border-[var(--color-border)] bg-[var(--color-bg)]'
    }`}
  >
    <div className="flex min-h-16 items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3">
      <div className="min-w-0">
        <div className="mb-1 text-xs font-medium text-[var(--color-text-3)]">{eyebrow}</div>
        <div className="truncate text-sm font-semibold text-[var(--color-text-1)]" title={snapshot.title}>
          {snapshot.title || '--'}
        </div>
      </div>
      {snapshot.versionLabel && (
        <Tag color={incoming ? 'processing' : undefined} className="m-0 shrink-0">
          {snapshot.versionLabel}
        </Tag>
      )}
    </div>

    <div className="px-4 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {snapshot.sourceLabel && (
          <Tag className="m-0 max-w-full truncate" title={snapshot.sourceLabel}>
            {snapshot.sourceLabel}
          </Tag>
        )}
        {snapshot.pageType && <Tag className="m-0">{snapshot.pageType}</Tag>}
        {snapshot.contribution && <Tag className="m-0">{snapshot.contribution}</Tag>}
      </div>

      {snapshot.body ? (
        <div className={`${MARKDOWN_CLASS} min-h-36`} dangerouslySetInnerHTML={markdownHtml(snapshot.body)} />
      ) : (
        <div className="flex min-h-36 items-center justify-center text-sm text-[var(--color-text-3)]">--</div>
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

const ComparisonConnector = () => (
  <div className="hidden h-10 w-10 self-center items-center justify-center rounded-full border border-[var(--color-border-strong)] bg-[var(--color-primary-bg-active)] text-[var(--color-primary)] xl:flex">
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
  const decisionItems = useMemo(() => filterDecisionItems(items), [items]);
  const activeItem = useMemo(
    () => decisionItems.find((item) => item.id === activeId) || decisionItems[0] || null,
    [activeId, decisionItems]
  );
  const model = useMemo(() => (activeItem ? buildDecisionViewModel(activeItem) : null), [activeItem]);
  const activeInteraction = useMemo(
    () => activeItem ? getDecisionInteractionState(activeItem, submitting, outdatedItemId) : null,
    [activeItem, outdatedItemId, submitting]
  );
  const editingInteraction = useMemo(
    () => editingItem ? getDecisionInteractionState(editingItem, submitting, outdatedItemId) : null,
    [editingItem, outdatedItemId, submitting]
  );

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
    setEditingItem(item);
    setEditBody(item.candidate?.body || itemModel.incoming.body);
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

  const submitEditedBody = async () => {
    if (!editingItem || !editBody.trim() || !editingInteraction?.canEditSubmit) return;
    const saved = await submitDecision(editingItem, {
      action: 'edit_accept',
      body: editBody.trim(),
    });
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
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
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
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-3">
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
              disabled={!interaction.canDecide}
              onClick={() => {
                if (action === 'edit_accept') openEditor(item);
                else void submitDecision(item, { action });
              }}
            >
              {actionLabel(action)}
            </Button>
          ))}
        </Space>
      </div>
    );
  };

  const renderProcessedFooter = (item: CheckItem) => {
    const rule = item.decision_rule;
    const revokedReason = resolveDecisionRevokedReason(rule?.revoked_reason);
    return (
      <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-[var(--color-text-2)]">
            <span>
              <span className="text-[var(--color-text-3)]">{t('wiki.decisionAction')}: </span>
              {actionLabel(item.decision_action || rule?.action)}
            </span>
            {item.decision_operator && (
              <span>
                <span className="text-[var(--color-text-3)]">{t('wiki.decisionOperator')}: </span>
                {item.decision_operator}
              </span>
            )}
            {item.decision_processed_at && (
              <span>
                <span className="text-[var(--color-text-3)]">{t('wiki.decisionProcessedAt')}: </span>
                {formatTimestamp(item.decision_processed_at)}
              </span>
            )}
            {rule && (
              <>
                <span>
                  <span className="text-[var(--color-text-3)]">{t('wiki.decisionRuleStatus')}: </span>
                  <Tag color={rule.status === 'active' ? 'success' : 'default'} className="m-0">
                    {rule.status === 'active' ? t('wiki.decisionRuleActive') : t('wiki.decisionRuleRevoked')}
                  </Tag>
                </span>
                <span>
                  <span className="text-[var(--color-text-3)]">{t('wiki.decisionReplayCount')}: </span>
                  <span className="tabular-nums">{rule.replay_count}</span>
                </span>
                {rule.last_replayed_at && (
                  <span>
                    <span className="text-[var(--color-text-3)]">{t('wiki.decisionLastReplay')}: </span>
                    {formatTimestamp(rule.last_replayed_at)}
                  </span>
                )}
                {revokedReason.fallback && (
                  <span>
                    <span className="text-[var(--color-text-3)]">{t('wiki.decisionRevokedReason')}: </span>
                    {revokedReason.translationKey
                      ? t(revokedReason.translationKey)
                      : revokedReason.fallback}
                  </span>
                )}
              </>
            )}
          </div>
          {rule && isDecisionRuleRevocable(rule) && onRevoke && (
            <Popconfirm
              title={t('wiki.decisionRevokeRuleConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => onRevoke(item)}
            >
              <Button loading={isSubmitting(item, 'revoke')}>{t('wiki.decisionRevokeRule')}</Button>
            </Popconfirm>
          )}
        </div>
      </div>
    );
  };

  return (
    <main className="flex min-h-[660px] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="m-0 text-base font-semibold text-[var(--color-text-1)]">{t('wiki.decisionCenterTitle')}</h2>
            {pendingCount > 0 && <Tag color="processing" className="m-0 tabular-nums">{pendingCount}</Tag>}
          </div>
          <p className="mb-0 mt-1 text-xs text-[var(--color-text-3)]">{t('wiki.decisionCenterSubtitle')}</p>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-b border-[var(--color-border)] bg-[var(--color-primary-bg-active)] p-3 lg:border-b-0 lg:border-r">
          <Segmented
            disabled={Boolean(submitting)}
            block
            value={view}
            onChange={(value) => onViewChange(String(value) as DecisionListView)}
            options={[
              { value: 'pending', label: `${t('wiki.decisionPending')} ${pendingCount}` },
              { value: 'processed', label: `${t('wiki.decisionProcessed')} ${processedCount}` },
            ]}
          />

          <Spin spinning={loading} className="mt-3 min-h-48">
            <div className="space-y-2">
              {decisionItems.map((item) => {
                const itemModel = buildDecisionViewModel(item);
                if (!itemModel) return null;
                const active = item.id === activeItem?.id;
                return (
                  <button
                    key={item.id}
                    disabled={Boolean(submitting)}
                    type="button"
                    aria-pressed={active}
                    onClick={() => onSelect?.(item)}
                    className={`w-full rounded-xl border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] ${
                      active
                        ? 'border-[var(--color-primary)] bg-[var(--color-bg)]'
                        : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-border-strong)]'
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <Tag color={view === 'processed' ? 'success' : itemModel.kind === 'knowledge_conflict' ? 'orange' : 'blue'} className="m-0">
                        {view === 'processed'
                          ? t('wiki.decisionProcessed')
                          : itemModel.kind === 'knowledge_conflict'
                            ? t('wiki.decisionKnowledgeConflict')
                            : t('wiki.decisionPageIdentity')}
                      </Tag>
                      <span className="text-xs tabular-nums text-[var(--color-text-3)]">
                        {formatTimestamp(item.updated_at || item.created_at)}
                      </span>
                    </div>
                    <div className="truncate text-sm font-medium leading-6 text-[var(--color-text-1)]" title={itemModel.title}>
                      {itemModel.title || '--'}
                    </div>
                    <p className="mb-0 mt-1 line-clamp-2 text-xs leading-5 text-[var(--color-text-3)]">
                      {itemModel.summary || (itemModel.kind === 'knowledge_conflict'
                        ? t('wiki.decisionKnowledgeSummaryFallback')
                        : t('wiki.decisionIdentitySummaryFallback'))}
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

        <section className="flex min-h-0 min-w-0 flex-col bg-[var(--color-bg)]">
          {error && <Alert type="error" showIcon message={error} className="m-4 mb-0" />}
          {activeItem && model ? (
            <>
              <div className="flex-1 overflow-y-auto px-5 py-5">
                <div className="mb-4 min-w-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Tag color={model.kind === 'knowledge_conflict' ? 'orange' : 'blue'} className="m-0">
                      {model.kind === 'knowledge_conflict'
                        ? t('wiki.decisionKnowledgeConflict')
                        : t('wiki.decisionPageIdentity')}
                    </Tag>
                    <Tag className="m-0">
                      {activeItem.status === 'open' ? t('wiki.decisionPending') : t('wiki.decisionProcessed')}
                    </Tag>
                  </div>
                  <h3 className="m-0 text-base font-semibold leading-7 text-[var(--color-text-1)]">{model.title || '--'}</h3>
                  <p className="mb-0 mt-1 text-sm leading-6 text-[var(--color-text-2)]">
                    {model.summary || (model.kind === 'knowledge_conflict'
                      ? t('wiki.decisionKnowledgeSummaryFallback')
                      : t('wiki.decisionIdentitySummaryFallback'))}
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-primary-bg-active)] p-2 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    [t('wiki.decisionWhyNeeded'), model.reason || (model.kind === 'knowledge_conflict' ? t('wiki.decisionReasonConflictFallback') : t('wiki.decisionReasonIdentityFallback'))],
                    [t('wiki.decisionTriggerSource'), model.triggerSource || t('wiki.decisionSourceUnknown')],
                    [t('wiki.decisionImpactScope'), model.impactScope || (model.kind === 'knowledge_conflict' ? t('wiki.decisionImpactConflictFallback') : t('wiki.decisionImpactIdentityFallback'))],
                    [t('wiki.decisionRecoverability'), model.recoverability || (model.kind === 'knowledge_conflict' ? t('wiki.decisionRecoveryConflictFallback') : t('wiki.decisionRecoveryIdentityFallback'))],
                  ].map(([label, value]) => (
                    <div key={label} className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3.5 py-3">
                      <div className="mb-1 text-xs text-[var(--color-text-3)]">{label}</div>
                      <div className="truncate text-sm text-[var(--color-text-1)]" title={value}>{value}</div>
                    </div>
                  ))}
                </div>

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
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_40px_minmax(0,1fr)] xl:items-stretch">
                  <SnapshotCard
                    snapshot={model.current}
                    eyebrow={t('wiki.decisionCurrentKnowledge')}
                    incoming={false}
                    sourceCountLabel={t('wiki.decisionSourceCount')}
                    relationCountLabel={t('wiki.decisionRelationCount')}
                  />
                  <ComparisonConnector />
                  <SnapshotCard
                    snapshot={model.incoming}
                    eyebrow={t('wiki.decisionNewKnowledge')}
                    incoming
                    sourceCountLabel={t('wiki.decisionSourceCount')}
                    relationCountLabel={t('wiki.decisionRelationCount')}
                  />
                </div>
              </div>

              {activeItem.status === 'open' ? renderPendingFooter(activeItem) : renderProcessedFooter(activeItem)}
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
