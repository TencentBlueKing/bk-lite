'use client';

import React, {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
} from 'react';
import { message } from 'antd';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { useTranslation } from '@/utils/i18n';
import type {
  CheckDecisionRequest,
  CheckItem,
  DecisionListView,
} from '@/app/opspilot/types/wiki';
import WikiDecisionCenter from './WikiDecisionCenter';
import {
  buildDecisionLoadPlan,
  createDecisionScopeState,
  createLatestRequestGuard,
  decisionScopeReducer,
  filterDecisionItems,
  getVisibleDecisionScopeState,
  shouldRefreshDecisionListAfterError,
  type DecisionSubmittingState,
} from './wikiDecisionModel';

const getErrorMessage = (error: unknown) =>
  error instanceof Error ? error.message : String(error);

const CheckTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchDecisionItems, decideCheck, revokeDecisionRule } = useWikiApi();
  const [requestGuard] = useState(createLatestRequestGuard);
  const submittingCheckRef = useRef<number | null>(null);
  const [scopeState, dispatchScope] = useReducer(
    decisionScopeReducer,
    createDecisionScopeState(),
  );
  const [view, setView] = useState<DecisionListView>('pending');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState<DecisionSubmittingState | null>(
    null,
  );
  const [outdatedItemId, setOutdatedItemId] = useState<number | null>(null);
  const { items, loadedScopeKey } = scopeState;
  const scopeKey = `${kbId}:${view}:${page}:${pageSize}`;
  const visibleScopeState = getVisibleDecisionScopeState(scopeState, scopeKey);

  const load = useCallback(async (): Promise<boolean> => {
    const requestId = requestGuard.begin();
    const plan = buildDecisionLoadPlan(view, page, pageSize);
    setLoading(true);
    try {
      const [primary, companion] = await Promise.all([
        fetchDecisionItems(kbId, plan.primary),
        fetchDecisionItems(kbId, plan.companion),
      ]);
      return requestGuard.commitIfCurrent(requestId, () => {
        const countsForScope =
          view === 'pending'
            ? { pending: primary.count, processed: companion.count }
            : { pending: companion.count, processed: primary.count };
        dispatchScope({
          type: 'load_succeeded',
          scopeKey,
          items: filterDecisionItems(primary.items),
          total: primary.count,
          counts: countsForScope,
        });
      });
    } catch (requestError) {
      requestGuard.commitIfCurrent(requestId, () => {
        dispatchScope({
          type: 'load_failed',
          scopeKey,
          error: getErrorMessage(requestError),
        });
      });
      return false;
    } finally {
      requestGuard.commitIfCurrent(requestId, () => setLoading(false));
    }
    // useWikiApi 每次渲染都会返回新函数；请求参数才是加载生命周期的稳定依赖。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize, requestGuard, scopeKey, view]);

  useEffect(() => {
    requestGuard.invalidate();
    dispatchScope({ type: 'reset' });
    setOutdatedItemId(null);
    void load();
    return () => requestGuard.invalidate();
  }, [load, requestGuard]);

  const invalidateVisibleScope = () => {
    requestGuard.invalidate();
    dispatchScope({ type: 'reset' });
    setOutdatedItemId(null);
    setLoading(true);
  };

  const handleViewChange = (nextView: DecisionListView) => {
    invalidateVisibleScope();
    setView(nextView);
    setPage(1);
  };

  const handlePageChange = (nextPage: number) => {
    invalidateVisibleScope();
    setPage(nextPage);
  };

  const ensureCurrentItem = (item: CheckItem) => {
    if (
      loadedScopeKey !== scopeKey ||
      !items.some((current) => current.id === item.id)
    ) {
      throw new Error(t('wiki.decisionContextOutdated'));
    }
  };

  const handleDecide = async (
    item: CheckItem,
    request: CheckDecisionRequest,
  ) => {
    ensureCurrentItem(item);
    if (outdatedItemId === item.id) throw new Error(t('wiki.decisionOutdated'));
    if (submittingCheckRef.current !== null) return;
    const operationRequestId = requestGuard.begin();
    submittingCheckRef.current = item.id;
    setSubmitting({ checkId: item.id, action: request.action });
    try {
      await decideCheck(item.id, request);
      if (requestGuard.isCurrent(operationRequestId)) {
        setOutdatedItemId(null);
        message.success(t('wiki.decisionSaved'));
        await load();
      }
    } catch (requestError) {
      if (requestGuard.isCurrent(operationRequestId)) {
        const requestMessage = getErrorMessage(requestError);
        const shouldRefresh =
          shouldRefreshDecisionListAfterError(requestMessage);
        if (shouldRefresh) {
          setOutdatedItemId(item.id);
        }
        dispatchScope({ type: 'set_error', error: requestMessage });
        if (shouldRefresh) {
          const refreshed = await load();
          if (refreshed) setOutdatedItemId(null);
        }
      }
      throw requestError;
    } finally {
      if (submittingCheckRef.current === item.id) {
        submittingCheckRef.current = null;
        setSubmitting(null);
      }
    }
  };

  const handleRevoke = async (item: CheckItem) => {
    ensureCurrentItem(item);
    if (submittingCheckRef.current !== null) return;
    const operationRequestId = requestGuard.begin();
    submittingCheckRef.current = item.id;
    setSubmitting({ checkId: item.id, action: 'revoke' });
    try {
      await revokeDecisionRule(item.id, {
        rule_id: item.decision_rule?.id,
      });
      if (requestGuard.isCurrent(operationRequestId)) {
        message.success(t('wiki.decisionRevokeSuccess'));
        await load();
      }
    } catch (requestError) {
      if (requestGuard.isCurrent(operationRequestId)) {
        dispatchScope({
          type: 'set_error',
          error: getErrorMessage(requestError),
        });
      }
    } finally {
      if (submittingCheckRef.current === item.id) {
        submittingCheckRef.current = null;
        setSubmitting(null);
      }
    }
  };
  const handleRefresh = async () => {
    const refreshed = await load();
    if (refreshed) setOutdatedItemId(null);
    return refreshed;
  };

  return (
    <WikiDecisionCenter
      key={`${scopeKey}:${outdatedItemId ?? 'current'}`}
      items={visibleScopeState.items}
      view={view}
      total={visibleScopeState.total}
      page={page}
      pageSize={pageSize}
      pendingCount={visibleScopeState.counts.pending}
      processedCount={visibleScopeState.counts.processed}
      activeId={visibleScopeState.activeId}
      loading={loading || loadedScopeKey !== scopeKey}
      error={visibleScopeState.error}
      outdatedItemId={outdatedItemId}
      submitting={submitting}
      onViewChange={handleViewChange}
      onSelect={(item) => dispatchScope({ type: 'select', activeId: item.id })}
      onPageChange={handlePageChange}
      onDecide={handleDecide}
      onRevoke={handleRevoke}
      onRefresh={handleRefresh}
    />
  );
};

export default CheckTab;
