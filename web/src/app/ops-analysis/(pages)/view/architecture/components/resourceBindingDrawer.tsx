'use client';

import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react';
import { Button, Empty, Input, Popconfirm, Select, Spin, Tag, Typography } from 'antd';
import { CheckOutlined, DisconnectOutlined, SearchOutlined } from '@ant-design/icons';
import OperateDrawer from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import type {
  ArchitectureBinding,
  ArchitectureNodeStatusItem,
  BindingSearchHit,
  BindingSearchPage,
  ModelOption,
} from '../binding/model';
import {
  appendBindingHits,
  bindingDisplay,
  bindingModelLabel,
  bindingSearchMode,
} from '../binding/model';
import {
  bindingStatusLoading,
  DEFAULT_ICON_TITLE,
  STATUS_DOT_COLOR,
  STATUS_LABEL_KEY,
} from '../binding/status';

interface ResourceBindingDrawerProps {
  open: boolean;
  binding: ArchitectureBinding | null;
  status: ArchitectureNodeStatusItem | null;
  /** Phase of the edit-mode status request; a failed request stops the loading state. */
  statusPhase: 'idle' | 'ready' | 'failed';
  /** Stored name of the icon being bound. */
  iconName: string;
  modelName: string;
  models: ModelOption[];
  onSearch: (keyword: string, modelId: string, page: number) => Promise<BindingSearchPage>;
  onBind: (hit: BindingSearchHit) => void;
  onUnbind: () => void;
  onClose: () => void;
}

type SearchPhase = 'idle' | 'loading' | 'ready' | 'error';

/** Load the next page when the list is scrolled within this many pixels of its end. */
const LOAD_MORE_THRESHOLD = 48;

const ResourceBindingDrawer = ({
  open,
  binding,
  status,
  statusPhase,
  iconName,
  modelName,
  models,
  onSearch,
  onBind,
  onUnbind,
  onClose,
}: ResourceBindingDrawerProps) => {
  const { t } = useTranslation();
  const [keyword, setKeyword] = useState('');
  const [modelId, setModelId] = useState('');
  const [hits, setHits] = useState<BindingSearchHit[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [phase, setPhase] = useState<SearchPhase>('idle');
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const [selected, setSelected] = useState<BindingSearchHit | null>(null);
  /** Bumped by every new search; a response that carries an older value is stale and dropped. */
  const searchSeqRef = useRef(0);
  const loadingMoreRef = useRef(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const bound = Boolean(binding);
  const statusLoading = bindingStatusLoading(bound, status, statusPhase);
  const boundUuid = binding?.inst_uuid ?? '';
  const boundModelId = binding?.model_id ?? '';

  useEffect(() => {
    if (!open) return;
    setKeyword('');
    setModelId(boundModelId);
    setSelected(null);
  }, [open, boundUuid, boundModelId]);

  useEffect(() => {
    searchSeqRef.current += 1;
    const seq = searchSeqRef.current;
    loadingMoreRef.current = false;
    setHits([]);
    setPage(1);
    setHasMore(false);
    setLoadingMore(false);
    setLoadMoreError(false);
    listRef.current?.scrollTo({ top: 0 });
    if (!open || bindingSearchMode(keyword, modelId) === 'idle') {
      setPhase('idle');
      return undefined;
    }
    setPhase('loading');
    const timer = window.setTimeout(() => {
      onSearch(keyword.trim(), modelId, 1)
        .then((result) => {
          if (seq !== searchSeqRef.current) return;
          setHits(appendBindingHits([], result.hits));
          setHasMore(result.hasMore);
          setPhase('ready');
        })
        .catch(() => {
          if (seq === searchSeqRef.current) setPhase('error');
        });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [keyword, modelId, onSearch, open, retryToken]);

  /** `retry` loads again after a failed page; scrolling alone does not repeat a failure. */
  const loadMore = useCallback((retry = false) => {
    if (phase !== 'ready' || !hasMore || loadingMoreRef.current) return;
    if (loadMoreError && !retry) return;
    setLoadMoreError(false);
    const seq = searchSeqRef.current;
    const nextPage = page + 1;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    onSearch(keyword.trim(), modelId, nextPage)
      .then((result) => {
        if (seq !== searchSeqRef.current) return;
        setHits((current) => appendBindingHits(current, result.hits));
        setPage(nextPage);
        setHasMore(result.hasMore);
      })
      .catch(() => {
        if (seq === searchSeqRef.current) setLoadMoreError(true);
      })
      .finally(() => {
        if (seq !== searchSeqRef.current) return;
        loadingMoreRef.current = false;
        setLoadingMore(false);
      });
  }, [hasMore, keyword, loadMoreError, modelId, onSearch, page, phase]);

  // A first page that does not fill the list cannot be scrolled; keep loading until it can.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (list.scrollHeight - list.clientHeight <= LOAD_MORE_THRESHOLD) loadMore();
  }, [hits, loadMore]);

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    const list = event.currentTarget;
    if (list.scrollHeight - list.scrollTop - list.clientHeight <= LOAD_MORE_THRESHOLD) loadMore();
  };

  const display = bindingDisplay(status, modelName);
  const blockedText = display.blocked === 'invalid'
    ? t('opsAnalysis.architecture.bindingInvalid')
    : display.blocked === 'forbidden'
      ? t('opsAnalysis.architecture.bindingForbidden')
      : t('opsAnalysis.architecture.bindingUnknown');
  const cardType = display.typeName || (binding ? bindingModelLabel(models, binding.model_id) : modelName);
  const statusKey = STATUS_LABEL_KEY[status?.status ?? 'unknown'];
  const statusDot = STATUS_DOT_COLOR[status?.status ?? 'unknown'];
  const shownIconName = iconName.trim() && iconName.trim() !== DEFAULT_ICON_TITLE
    ? iconName.trim()
    : t('opsAnalysis.architecture.unnamedIcon');
  const hitName = (hit: BindingSearchHit) => hit.inst_name || hit.inst_uuid;

  // The name is highlighted inside the localized sentence, so the message is
  // formatted with a marker and split around it.
  const selectedParts = selected
    ? (() => {
      const marker = '\u0000';
      const [before = '', after = ''] = t(
        'opsAnalysis.architecture.bindingSelected',
        undefined,
        { name: marker },
      ).split(marker);
      return { before, name: hitName(selected), after };
    })()
    : null;

  const confirm = () => {
    if (selected) onBind(selected);
  };

  const boundCard = bound ? (
    <section className="shrink-0">
      <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">
        {t('opsAnalysis.architecture.bindingCurrent')}
      </div>
      <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {statusLoading ? (
              <Spin size="small" />
            ) : (
              <span
                className={`truncate text-sm ${display.blocked
                  ? 'text-[var(--color-text-3)]'
                  : 'font-semibold text-[var(--color-text-1)]'}`}
                title={display.blocked ? blockedText : display.name}
              >
                {display.blocked ? blockedText : display.name}
              </span>
            )}
            {cardType ? <Tag color="blue" className="m-0 shrink-0">{cardType}</Tag> : null}
          </div>
          <Popconfirm
            title={t('opsAnalysis.architecture.bindingUnbindConfirm')}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
            onConfirm={onUnbind}
          >
            <Button type="text" danger size="small" icon={<DisconnectOutlined />}>
              {t('opsAnalysis.architecture.bindingUnbind')}
            </Button>
          </Popconfirm>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-[var(--color-text-3)]">
          <span className="flex min-w-0 items-center gap-1 font-mono">
            <span className="shrink-0">{t('opsAnalysis.architecture.bindingCardId')}</span>
            <Typography.Text
              className="min-w-0 font-mono text-xs text-[var(--color-text-3)]"
              ellipsis={{ tooltip: boundUuid }}
              copyable={{ text: boundUuid }}
            >
              {boundUuid}
            </Typography.Text>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-[var(--color-text-2)]">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: statusDot }} />
            {t(statusKey)}
          </span>
        </div>
      </div>
    </section>
  ) : null;

  const listBody = () => {
    if (phase === 'idle') {
      return (
        <div className="flex h-full items-center justify-center px-6 text-center text-xs text-[var(--color-text-3)]">
          {t('opsAnalysis.architecture.bindingIdle')}
        </div>
      );
    }
    if (phase === 'loading') {
      return (
        <div className="flex h-full items-center justify-center">
          <Spin size="small" />
        </div>
      );
    }
    if (phase === 'error') {
      return (
        <div className="flex h-full items-center justify-center gap-2 text-xs text-[var(--color-text-3)]">
          <span>{t('opsAnalysis.architecture.bindingSearchFailed')}</span>
          <Button type="link" size="small" className="h-auto p-0" onClick={() => setRetryToken((current) => current + 1)}>
            {t('opsAnalysis.architecture.bindingSearchRetry')}
          </Button>
        </div>
      );
    }
    if (hits.length === 0) {
      return (
        <div className="flex h-full items-center justify-center">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={(
              <div className="flex flex-col gap-1">
                <span className="text-sm text-[var(--color-text-2)]">{t('opsAnalysis.architecture.bindingEmpty')}</span>
                <span className="text-xs text-[var(--color-text-3)]">{t('opsAnalysis.architecture.bindingEmptyHint')}</span>
              </div>
            )}
          />
        </div>
      );
    }
    return (
      <>
        {hits.map((hit) => {
          const current = bound && hit.inst_uuid === boundUuid;
          const active = !current && selected?.inst_uuid === hit.inst_uuid;
          return (
            <button
              key={hit.inst_uuid}
              type="button"
              disabled={current}
              aria-pressed={active}
              className={`relative flex h-14 w-full shrink-0 items-center justify-between gap-3 border-0 border-b border-solid border-[var(--color-border-1)] px-4 text-left [font:inherit] last:border-b-0 ${current
                ? 'cursor-default bg-[var(--color-fill-1)]'
                : active
                  ? 'cursor-pointer bg-[#e6f4ff]'
                  : 'cursor-pointer bg-transparent hover:bg-[var(--color-fill-1)]'}`}
              onClick={() => setSelected(hit)}
            >
              {active ? <span className="absolute inset-y-0 left-0 w-[3px] bg-[var(--color-primary)]" /> : null}
              <span className="flex min-w-0 flex-col">
                <span
                  className={`truncate text-sm leading-5 ${current
                    ? 'text-[var(--color-text-3)]'
                    : active
                      ? 'font-semibold text-[var(--color-primary)]'
                      : 'text-[var(--color-text-1)]'}`}
                  title={hitName(hit)}
                >
                  {hitName(hit)}
                </span>
                <span className="mt-0.5 truncate text-xs leading-[18px] text-[var(--color-text-3)]">
                  {[bindingModelLabel(models, hit.model_id), hit.ip_addr].filter(Boolean).join(' · ')}
                </span>
              </span>
              {current ? (
                <Tag className="m-0 shrink-0">{t('opsAnalysis.architecture.bindingCurrentTag')}</Tag>
              ) : null}
              {active ? <CheckOutlined className="shrink-0 text-[var(--color-primary)]" /> : null}
            </button>
          );
        })}
        {loadingMore ? (
          <div className="flex shrink-0 justify-center py-3">
            <Spin size="small" />
          </div>
        ) : null}
        {loadMoreError ? (
          <div className="flex shrink-0 items-center justify-center gap-2 py-3 text-xs text-[var(--color-text-3)]">
            <span>{t('opsAnalysis.architecture.bindingSearchFailed')}</span>
            <Button
              type="link"
              size="small"
              className="h-auto p-0"
              onClick={() => loadMore(true)}
            >
              {t('opsAnalysis.architecture.bindingSearchRetry')}
            </Button>
          </div>
        ) : null}
      </>
    );
  };

  return (
    <OperateDrawer
      open={open}
      width={480}
      destroyOnHidden
      title={(
        <span className="flex min-w-0 flex-col">
          <span>{t('opsAnalysis.architecture.bindingDrawerTitle')}</span>
          <span className="mt-0.5 truncate text-xs font-normal text-[var(--color-text-3)]" title={shownIconName}>
            {t('opsAnalysis.architecture.bindingIconName', undefined, { name: shownIconName })}
          </span>
        </span>
      )}
      onClose={onClose}
      classNames={{ body: 'flex min-h-0 flex-col' }}
      styles={{ body: { overflow: 'hidden', padding: '20px 24px' } }}
      footer={(
        <div className="flex w-full items-center justify-between gap-3">
          <span className="min-w-0 truncate text-xs text-[var(--color-text-3)]">
            {selectedParts ? (
              <>
                {selectedParts.before}
                <span className="font-medium text-[var(--color-primary)]">{selectedParts.name}</span>
                {selectedParts.after}
              </>
            ) : null}
          </span>
          <span className="flex shrink-0 gap-2">
            <Button onClick={onClose}>{t('opsAnalysis.architecture.bindingCancel')}</Button>
            <Button type="primary" disabled={!selected} onClick={confirm}>
              {bound
                ? t('opsAnalysis.architecture.bindingConfirmReplace')
                : t('opsAnalysis.architecture.bindingConfirm')}
            </Button>
          </span>
        </div>
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-6" data-testid="architecture-binding-drawer">
        {boundCard}
        <section className="flex min-h-0 flex-1 flex-col">
          <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">
            {bound ? t('opsAnalysis.architecture.bindingReplace') : t('opsAnalysis.architecture.bindingPick')}
          </div>
          <div className="mb-3 flex shrink-0 gap-2">
            <Select
              allowClear
              showSearch
              className="w-[140px] shrink-0"
              optionFilterProp="label"
              placeholder={t('opsAnalysis.architecture.bindingModel')}
              value={modelId || undefined}
              options={models.map((model) => ({
                value: model.model_id,
                label: model.model_name,
              }))}
              onChange={(value) => setModelId(value || '')}
            />
            <Input
              allowClear
              prefix={<SearchOutlined className="text-[var(--color-text-4)]" />}
              placeholder={t('opsAnalysis.architecture.bindingSearch')}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
          </div>
          <div
            ref={listRef}
            className="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-lg border border-solid border-[var(--color-border-1)]"
            onScroll={handleScroll}
            data-testid="architecture-binding-results"
          >
            {listBody()}
          </div>
        </section>
      </div>
    </OperateDrawer>
  );
};

export default ResourceBindingDrawer;
