'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DownOutline, SearchOutline } from 'antd-mobile-icons';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import MobileSegmentTabs from '@/components/mobile-segment-tabs';
import MobileTabShell from '@/components/mobile-tab-shell';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { getFollowedConfig, listAssetCatalog, resolveFollowedAssets } from '@/features/assets/adapter';
import AllAssetsPanel from '@/features/assets/all-assets-panel';
import AssetListCard from '@/features/assets/asset-list-card';
import { type AssetInstance } from '@/features/assets/model';
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

interface AllTabWorkbenchMeta {
  name: string;
  modelCount: number;
}

const initialCatalog = { classifications: [], models: [] } as Awaited<ReturnType<typeof listAssetCatalog>>;

interface AssetsRootViewState {
  activeTab: string;
  catalog: typeof initialCatalog;
  followed: AssetInstance[];
  lastAllQuery: string;
}

function AssetsPageContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const { canAccess } = useMobileAvailability();
  const router = useRouter();
  const params = useSearchParams();
  const classificationId = params.get('classificationId') || '';
  const classificationName = params.get('classificationName') || '';
  const modelId = params.get('modelId') || '';
  const modelName = params.get('modelName') || '';
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const initialSnapshot = useRef(readMobileViewSnapshot<AssetsRootViewState>(cacheScope, 'assets-root'));
  const hasAllContext = Boolean(classificationId || modelId);
  const deepLinkedToAll = useRef(hasAllContext);
  const defaultTab = hasAllContext ? 'all' : (initialSnapshot.current?.data.activeTab || 'followed');
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [catalog, setCatalog] = useState(initialSnapshot.current?.data.catalog || initialCatalog);
  const [followed, setFollowed] = useState<AssetInstance[]>(initialSnapshot.current?.data.followed || []);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(initialSnapshot.current ? 'ready' : 'loading');
  const [categoryPickerOpen, setCategoryPickerOpen] = useState(false);
  const [allTabMeta, setAllTabMeta] = useState<AllTabWorkbenchMeta | null>(null);
  const lastAllQueryRef = useRef(initialSnapshot.current?.data.lastAllQuery || '');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const modelMap = useMemo(() => new Map(catalog.models.map((model) => [model.id, model])), [catalog.models]);
  const inAllWorkbench = activeTab === 'all' && Boolean(classificationId);
  const allTabLabel = inAllWorkbench
    ? (allTabMeta
      ? t('assets.categorySwitchLabel', undefined, {
        name: allTabMeta.name,
        count: allTabMeta.modelCount,
      })
      : (classificationName || t('assets.tabs.all')))
    : t('assets.tabs.all');

  const loadFollowed = useCallback(async (preserveContent = false) => {
    const currentId = ++requestId.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    if (!preserveContent) setStatus('loading');
    try {
      const [nextCatalog, config] = await Promise.all([
        listAssetCatalog(controller.signal),
        getFollowedConfig(controller.signal),
      ]);
      const nextFollowed = await resolveFollowedAssets(config, nextCatalog.models, controller.signal);
      if (currentId !== requestId.current) return;
      setCatalog(nextCatalog);
      setFollowed(nextFollowed);
      setStatus('ready');
    } catch (error) {
      if (controller.signal.aborted || currentId !== requestId.current) return;
      if (!preserveContent) setStatus('error');
      throw error;
    }
  }, []);

  useEffect(() => {
    if (activeTab !== 'followed') return;
    const preserve = Boolean(initialSnapshot.current) || followed.length > 0;
    void loadFollowed(preserve).catch(() => undefined);
    return () => {
      requestId.current += 1;
      requestController.current?.abort();
    };
    // 进入「我关注的」时拉取；followed 变化不重复触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, loadFollowed]);

  useEffect(() => {
    // 仅深链首次进入时落到「全部」；之后用户可自由切换互斥 Tab。
    if (!deepLinkedToAll.current) return;
    deepLinkedToAll.current = false;
    if (activeTab !== 'all') setActiveTab('all');
  }, [activeTab]);

  useEffect(() => {
    if (!classificationId) setAllTabMeta(null);
  }, [classificationId]);

  useEffect(() => {
    if (activeTab !== 'all') setCategoryPickerOpen(false);
  }, [activeTab]);

  const openCategoryPicker = useCallback(() => {
    if (!inAllWorkbench) return;
    setCategoryPickerOpen(true);
  }, [inAllWorkbench]);

  const onTabChange = useCallback((key: string) => {
    if (key === 'followed') {
      const next = new URLSearchParams();
      if (classificationId) next.set('classificationId', classificationId);
      if (classificationName) next.set('classificationName', classificationName);
      if (modelId) next.set('modelId', modelId);
      if (modelName) next.set('modelName', modelName);
      lastAllQueryRef.current = next.toString();
      setCategoryPickerOpen(false);
      setActiveTab(key);
      if (next.toString()) router.replace('/assets');
      return;
    }
    if (key === 'all') {
      // 已在分类工作台时再次点第二 Tab：打开分类下拉，而不是无操作。
      if (activeTab === 'all' && classificationId) {
        setCategoryPickerOpen(true);
        return;
      }
      setActiveTab(key);
      if (!classificationId && !modelId && lastAllQueryRef.current) {
        router.replace(`/assets?${lastAllQueryRef.current}`);
      }
      return;
    }
    setActiveTab(key);
  }, [activeTab, classificationId, classificationName, modelId, modelName, router]);

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (activeTab === 'followed' && status !== 'ready') return;
    writeMobileViewSnapshot<AssetsRootViewState>(cacheScope, 'assets-root', {
      activeTab,
      catalog,
      followed,
      lastAllQuery: lastAllQueryRef.current,
    }, activeTab === 'followed' ? scrollTop : 0);
  }, [activeTab, cacheScope, catalog, followed, status]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    if (activeTab !== 'followed') return;
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, [activeTab]);

  const searchAllowed = canAccess('assets', 'Search');

  return (
    <MobileTabShell activeTab="assets">
      <main className={styles.page}>
        <MobilePageHeader title={t('navigation.assets')} />
        {searchAllowed && (
          <Link className={styles.searchLauncher} href="/assets/search" aria-label={t('assets.search')}>
            <span className={styles.searchField}>
              <SearchOutline className={styles.searchIcon} aria-hidden="true" />
              <span className={styles.searchPlaceholder}>{t('assets.searchPlaceholder')}</span>
            </span>
          </Link>
        )}
        <MobileSegmentTabs className={styles.tabs} activeKey={activeTab} onChange={onTabChange}>
          <MobileSegmentTabs.Tab key="followed" title={t('assets.tabs.followed')} />
          <MobileSegmentTabs.Tab
            key="all"
            title={(
              <span
                className={`${styles.allTabTitle}${inAllWorkbench ? ` ${styles.allTabTitleWorkbench}` : ''}${categoryPickerOpen ? ` ${styles.allTabTitleOpen}` : ''}`}
                onClick={(event) => {
                  // antd Tabs 对已选中项通常不触发 onChange，工作台态靠标题点击打开下拉。
                  if (!inAllWorkbench) return;
                  event.preventDefault();
                  event.stopPropagation();
                  openCategoryPicker();
                }}
              >
                <span className={styles.allTabTitleText}>{allTabLabel}</span>
                {inAllWorkbench ? (
                  <DownOutline className={styles.allTabTitleChevron} aria-hidden="true" />
                ) : null}
              </span>
            )}
          />
        </MobileSegmentTabs>
        {activeTab === 'all' ? (
          <AllAssetsPanel
            classificationId={classificationId}
            modelId={modelId}
            modelName={modelName}
            categoryPickerOpen={categoryPickerOpen}
            onCategoryPickerOpenChange={setCategoryPickerOpen}
            onWorkbenchMetaChange={setAllTabMeta}
          />
        ) : (
          <div className={styles.allPanel}>
            <div
              className={styles.scroll}
              ref={scrollRef}
              onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}
            >
              <MobilePullToRefresh disabled={status === 'loading'} onRefresh={() => loadFollowed(true)}>
                <div className={styles.refreshContent}>
                  {status === 'loading' ? (
                    <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
                  ) : status === 'error' ? (
                    <MobileResult
                      kind="error"
                      title={t('assets.loadFailed')}
                      description={t('assets.retryHint')}
                      actionLabel={t('common.retry')}
                      onAction={() => void loadFollowed().catch(() => undefined)}
                    />
                  ) : followed.length === 0 ? (
                    <MobileResult kind="empty" title={t('assets.noFollowed')} description={t('assets.noFollowedHint')} />
                  ) : (
                    <div className={styles.assetTable}>
                      {followed.map((asset) => (
                        <AssetListCard
                          asset={asset}
                          modelName={modelMap.get(asset.modelId)?.name || asset.modelId}
                          modelIcon={modelMap.get(asset.modelId)?.icon}
                          key={`${asset.modelId}:${asset.id}`}
                        />
                      ))}
                    </div>
                  )}
                </div>
              </MobilePullToRefresh>
            </div>
          </div>
        )}
      </main>
    </MobileTabShell>
  );
}

export default function AssetsPage() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="list" rows={5} />}>
      <AssetsPageContent />
    </Suspense>
  );
}
