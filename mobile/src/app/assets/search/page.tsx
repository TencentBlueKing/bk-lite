'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InfiniteScroll, Switch } from 'antd-mobile';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MobileSearchBar from '@/components/mobile-search-bar';
import { listAssetCatalog, searchAssetsByModel, searchAssetStats } from '@/features/assets/adapter';
import AssetListCard from '@/features/assets/asset-list-card';
import type { AssetInstance, AssetModel, SearchModelStat } from '@/features/assets/model';
import { useMobileAvailability } from '@/platform/availability/context';
import { useAuth } from '@/context/auth';
import {
  readMobileViewSnapshot,
  restoreMobileViewScroll,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/assets/assets.module.css';

interface SearchCriteria {
  keyword: string;
  exact: boolean;
}

interface AssetSearchViewState {
  keyword: string;
  exact: boolean;
  criteria: SearchCriteria | null;
  models: AssetModel[];
  stats: SearchModelStat[];
  selected: string;
  items: AssetInstance[];
  total: number;
  page: number;
  status: 'idle' | 'ready';
}

function AssetSearchContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const { canAccess } = useMobileAvailability();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const initialSnapshot = useRef(readMobileViewSnapshot<AssetSearchViewState>(cacheScope, 'assets-search'));
  const [keyword, setKeyword] = useState(initialSnapshot.current?.data.keyword || '');
  const [exact, setExact] = useState(initialSnapshot.current?.data.exact || false);
  const [criteria, setCriteria] = useState<SearchCriteria | null>(initialSnapshot.current?.data.criteria || null);
  const [models, setModels] = useState<AssetModel[]>(initialSnapshot.current?.data.models || []);
  const [stats, setStats] = useState<SearchModelStat[]>(initialSnapshot.current?.data.stats || []);
  const [selected, setSelected] = useState(initialSnapshot.current?.data.selected || '');
  const [items, setItems] = useState<AssetInstance[]>(initialSnapshot.current?.data.items || []);
  const [total, setTotal] = useState(initialSnapshot.current?.data.total || 0);
  const [page, setPage] = useState(initialSnapshot.current?.data.page || 0);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(initialSnapshot.current?.data.status || 'idle');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const searchRequestId = useRef(0);
  const modelRequestId = useRef(0);
  const searchController = useRef<AbortController | null>(null);
  const modelController = useRef<AbortController | null>(null);
  const modelMap = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);

  useEffect(() => {
    if (initialSnapshot.current?.data.models.length) return;
    const controller = new AbortController();
    void listAssetCatalog(controller.signal)
      .then((catalog) => setModels(catalog.models))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const runModelSearch = useCallback(async (
    modelId: string,
    nextCriteria: SearchCriteria,
    nextPage = 1,
    append = false,
  ) => {
    const requestId = ++modelRequestId.current;
    modelController.current?.abort();
    const controller = new AbortController();
    modelController.current = controller;
    if (!append) setStatus('loading');
    try {
      const result = await searchAssetsByModel(nextCriteria.keyword, modelId, nextCriteria.exact, nextPage, controller.signal);
      if (requestId !== modelRequestId.current) return;
      setItems((current) => append
        ? [...new Map([...current, ...result.items].map((item) => [`${item.modelId}:${String(item.id)}`, item])).values()]
        : result.items);
      setTotal(result.count);
      setPage(nextPage);
      setSelected(modelId);
      setStatus('ready');
    } catch (error) {
      if (controller.signal.aborted || requestId !== modelRequestId.current) return;
      if (!append) setStatus('error');
      throw error;
    }
  }, []);

  const runSearch = useCallback(async (nextKeyword: string, nextExact: boolean) => {
    const normalized = nextKeyword.trim();
    if (!normalized) return;
    const nextCriteria = { keyword: normalized, exact: nextExact };
    const requestId = ++searchRequestId.current;
    searchController.current?.abort();
    modelRequestId.current += 1;
    modelController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setCriteria(nextCriteria);
    setStats([]);
    setSelected('');
    setItems([]);
    setTotal(0);
    setPage(0);
    setStatus('loading');
    try {
      const result = await searchAssetStats(normalized, nextExact, controller.signal);
      if (requestId !== searchRequestId.current) return;
      setStats(result.models);
      const firstModelId = result.models[0]?.modelId || '';
      if (!firstModelId) {
        setStatus('ready');
        return;
      }
      await runModelSearch(firstModelId, nextCriteria);
    } catch (error) {
      if (controller.signal.aborted || requestId !== searchRequestId.current) return;
      setStatus('error');
      throw error;
    }
  }, [runModelSearch]);

  useEffect(() => () => {
    searchRequestId.current += 1;
    modelRequestId.current += 1;
    searchController.current?.abort();
    modelController.current?.abort();
  }, []);

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (status !== 'idle' && status !== 'ready') return;
    writeMobileViewSnapshot<AssetSearchViewState>(cacheScope, 'assets-search', {
      keyword,
      exact,
      criteria,
      models,
      stats,
      selected,
      items,
      total,
      page,
      status,
    }, scrollTop);
  }, [cacheScope, criteria, exact, items, keyword, models, page, selected, stats, status, total]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, []);

  const submit = () => void runSearch(keyword, exact).catch(() => undefined);
  const clear = () => {
    searchRequestId.current += 1;
    modelRequestId.current += 1;
    searchController.current?.abort();
    modelController.current?.abort();
    setKeyword('');
    setCriteria(null);
    setStats([]);
    setSelected('');
    setItems([]);
    setTotal(0);
    setPage(0);
    setStatus('idle');
  };
  const changeExact = (nextExact: boolean) => {
    setExact(nextExact);
    if (criteria) void runSearch(criteria.keyword, nextExact).catch(() => undefined);
  };

  if (!canAccess('assets', 'Search')) {
    return (
      <main className={styles.page}>
        <MobilePageHeader title={t('assets.search')} backHref="/assets" />
        <MobileResult kind="permission" title={t('assets.searchForbidden')} />
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <MobilePageHeader title={t('assets.search')} backHref="/assets" />
      <div className={styles.searchArea}>
        <MobileSearchBar
          size="page"
          value={keyword}
          onChange={setKeyword}
          onSearch={submit}
          onClear={clear}
          placeholder={t('assets.searchPlaceholder')}
          showCancelButton={false}
        />
        <label className={styles.searchOptions}>
          <span>{t('assets.exactMatch')}</span>
          <Switch
            checked={exact}
            onChange={changeExact}
            style={{ '--height': '24px', '--width': '42px' }}
          />
        </label>
      </div>
      {stats.length > 0 && (
        <div className={styles.modelStats} role="group" aria-label={t('assets.searchResultsByModel')}>
          {stats.map((stat) => (
            <button
              type="button"
              className={`${styles.statPill} ${selected === stat.modelId ? styles.statPillActive : ''}`}
              aria-pressed={selected === stat.modelId}
              onClick={() => criteria && void runModelSearch(stat.modelId, criteria).catch(() => undefined)}
              key={stat.modelId}
            >
              {modelMap.get(stat.modelId)?.name || stat.modelId} · {stat.count}
            </button>
          ))}
        </div>
      )}
      <div className={styles.scroll} ref={scrollRef} onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}>
        {status === 'idle' ? (
          <MobileResult kind="empty" title={t('assets.searchHint')} description={t('assets.searchHintDescription')} />
        ) : status === 'loading' ? (
          <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
        ) : status === 'error' ? (
          <MobileResult kind="error" title={t('assets.searchFailed')} description={t('assets.retryHint')} actionLabel={t('common.retry')} onAction={() => criteria && void runSearch(criteria.keyword, criteria.exact).catch(() => undefined)} />
        ) : items.length === 0 ? (
          <MobileResult kind="empty" title={t('assets.noSearchResults')} />
        ) : (
          <div className={styles.assetTable}>
            {items.map((asset) => (
              <AssetListCard
                asset={asset}
                modelName={modelMap.get(asset.modelId)?.name || asset.modelId}
                modelIcon={modelMap.get(asset.modelId)?.icon}
                key={`${asset.modelId}:${asset.id}`}
              />
            ))}
            <InfiniteScroll hasMore={items.length < total} loadMore={() => criteria && selected ? runModelSearch(selected, criteria, page + 1, true).catch(() => undefined) : Promise.resolve()} />
          </div>
        )}
      </div>
    </main>
  );
}

export default function AssetSearchPage() {
  const { t } = useTranslation();
  return <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="list" rows={5} />}><AssetSearchContent /></Suspense>;
}
