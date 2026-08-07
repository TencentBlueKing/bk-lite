'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DownOutline, SearchOutline } from 'antd-mobile-icons';
import { useRouter, useSearchParams } from 'next/navigation';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import MobileSegmentTabs from '@/components/mobile-segment-tabs';
import MobileTabShell from '@/components/mobile-tab-shell';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { getFollowedConfig, listAssetCatalog, resolveFollowedAssets } from '@/features/assets/adapter';
import AllAssetsPanel from '@/features/assets/all-assets-panel';
import AssetListCard from '@/features/assets/asset-list-card';
import { useFollowedAssets } from '@/features/assets/use-followed-assets';
import { type AssetInstance } from '@/features/assets/model';
import { useMobileAvailability } from '@/platform/availability/context';
import { useAuth } from '@/context/auth';
import {
  clearMobileViewStale,
  isMobileViewStale,
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

interface StashedAllWorkbench {
  query: string;
  name: string;
  modelCount: number;
}

const initialCatalog = { classifications: [], models: [] } as Awaited<ReturnType<typeof listAssetCatalog>>;

interface AssetsRootViewState {
  activeTab: string;
  catalog: typeof initialCatalog;
  followed: AssetInstance[];
  lastAllQuery: string;
  stashedAll: StashedAllWorkbench | null;
}

function parseStashedAll(query: string, fallbackName = ''): StashedAllWorkbench | null {
  if (!query) return null;
  const params = new URLSearchParams(query);
  if (!params.get('classificationId') && !params.get('modelId')) return null;
  return {
    query,
    name: params.get('classificationName') || fallbackName,
    modelCount: 0,
  };
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
  const shouldRevalidate = useRef(
    Boolean(initialSnapshot.current) && isMobileViewStale(cacheScope, 'assets-root'),
  );
  const hasAllContext = Boolean(classificationId || modelId);
  // 分类查询串在「我关注的」时也保留在 URL，避免切回「全部」时先闪落地页。
  // 深链仅在无本地快照时强制落到全部；有快照则尊重上次 Tab。
  const deepLinkedToAll = useRef(hasAllContext && !initialSnapshot.current);
  const defaultTab = initialSnapshot.current?.data.activeTab
    || (hasAllContext ? 'all' : 'followed');
  const [activeTab, setActiveTab] = useState(defaultTab);
  const [catalog, setCatalog] = useState(initialSnapshot.current?.data.catalog || initialCatalog);
  const [followed, setFollowed] = useState<AssetInstance[]>(initialSnapshot.current?.data.followed || []);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(initialSnapshot.current ? 'ready' : 'loading');
  const [categoryPickerOpen, setCategoryPickerOpen] = useState(false);
  const [allTabMeta, setAllTabMeta] = useState<AllTabWorkbenchMeta | null>(null);
  const [stashedAll, setStashedAll] = useState<StashedAllWorkbench | null>(
    () => initialSnapshot.current?.data.stashedAll
      || parseStashedAll(initialSnapshot.current?.data.lastAllQuery || ''),
  );
  const follow = useFollowedAssets();
  const lastAllQueryRef = useRef(initialSnapshot.current?.data.lastAllQuery || '');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestId = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const modelMap = useMemo(() => new Map(catalog.models.map((model) => [model.id, model])), [catalog.models]);
  const inAllWorkbench = activeTab === 'all' && Boolean(classificationId);
  // 切到「我关注的」时 URL/暂存仍带分类，第二 Tab 继续显示分类名。
  const workbenchLabelMeta = (() => {
    if (classificationId) {
      if (allTabMeta?.name) return allTabMeta;
      if (classificationName) {
        return { name: classificationName, modelCount: stashedAll?.modelCount || 0 };
      }
    }
    if (stashedAll?.name) return { name: stashedAll.name, modelCount: stashedAll.modelCount };
    return null;
  })();
  const allTabLabel = workbenchLabelMeta
    ? (workbenchLabelMeta.modelCount > 0
      ? t('assets.categorySwitchLabel', undefined, {
        name: workbenchLabelMeta.name,
        count: workbenchLabelMeta.modelCount,
      })
      : workbenchLabelMeta.name)
    : t('assets.tabs.all');
  const showAllTabWorkbenchChrome = Boolean(workbenchLabelMeta);

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
    const silent = shouldRevalidate.current;
    if (silent) shouldRevalidate.current = false;
    void loadFollowed(preserve || silent).then(() => {
      if (silent || isMobileViewStale(cacheScope, 'assets-root')) {
        clearMobileViewStale(cacheScope, 'assets-root');
      }
    }).catch(() => undefined);
    // 星标配置与列表同机刷新：在「全部」/详情页产生的关注变更，回到本 Tab 时星态不失真
    void follow.reload().catch(() => undefined);
    return () => {
      requestId.current += 1;
      requestController.current?.abort();
    };
    // 进入「我关注的」时拉取；followed 变化不重复触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, cacheScope, loadFollowed, follow.reload]);

  useEffect(() => {
    // 无可用 snapshot 时本身会重新拉数，清掉遗留失效标记。
    if (!initialSnapshot.current && isMobileViewStale(cacheScope, 'assets-root')) {
      clearMobileViewStale(cacheScope, 'assets-root');
    }
  }, [cacheScope]);

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

  // 在分类工作台时同步暂存，供切到「我关注的」后第二 Tab 继续显示分类名。
  useEffect(() => {
    if (activeTab !== 'all' || !classificationId) return;
    const next = new URLSearchParams();
    next.set('classificationId', classificationId);
    if (classificationName) next.set('classificationName', classificationName);
    if (modelId) next.set('modelId', modelId);
    if (modelName) next.set('modelName', modelName);
    const query = next.toString();
    lastAllQueryRef.current = query;
    setStashedAll({
      query,
      name: allTabMeta?.name || classificationName,
      modelCount: allTabMeta?.modelCount || 0,
    });
  }, [activeTab, allTabMeta, classificationId, classificationName, modelId, modelName]);

  // 主动回到分类落地页时清掉暂存，避免之后点「全部」又跳回旧分类。
  useEffect(() => {
    if (activeTab !== 'all' || classificationId || modelId) return;
    lastAllQueryRef.current = '';
    setStashedAll(null);
  }, [activeTab, classificationId, modelId]);

  const openCategoryPicker = useCallback(() => {
    if (!inAllWorkbench) return;
    setCategoryPickerOpen(true);
  }, [inAllWorkbench]);

  const onTabChange = useCallback((key: string) => {
    if (key === 'followed') {
      // 不清理分类 URL：内容只由 activeTab 切换，切回「全部」时可直接进工作台，避免闪落地页。
      if (classificationId || modelId) {
        const next = new URLSearchParams();
        if (classificationId) next.set('classificationId', classificationId);
        if (classificationName) next.set('classificationName', classificationName);
        if (modelId) next.set('modelId', modelId);
        if (modelName) next.set('modelName', modelName);
        const query = next.toString();
        lastAllQueryRef.current = query;
        setStashedAll({
          query,
          name: allTabMeta?.name || classificationName,
          modelCount: allTabMeta?.modelCount || 0,
        });
      }
      setCategoryPickerOpen(false);
      setActiveTab(key);
      return;
    }
    if (key === 'all') {
      // 已在分类工作台时再次点第二 Tab：打开分类下拉，而不是无操作。
      if (activeTab === 'all' && classificationId) {
        setCategoryPickerOpen(true);
        return;
      }
      // URL 已带分类时直接切 Tab；仅在无 URL 时用暂存恢复。
      const restoreQuery = lastAllQueryRef.current || stashedAll?.query || '';
      if (!classificationId && !modelId && restoreQuery) {
        router.replace(`/assets?${restoreQuery}`);
      }
      setActiveTab(key);
      return;
    }
    setActiveTab(key);
  }, [
    activeTab,
    allTabMeta,
    classificationId,
    classificationName,
    modelId,
    modelName,
    router,
    stashedAll?.query,
  ]);

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (activeTab === 'followed' && status !== 'ready') return;
    writeMobileViewSnapshot<AssetsRootViewState>(cacheScope, 'assets-root', {
      activeTab,
      catalog,
      followed,
      lastAllQuery: lastAllQueryRef.current,
      stashedAll,
    }, activeTab === 'followed' ? scrollTop : 0);
  }, [activeTab, cacheScope, catalog, followed, stashedAll, status]);

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
        <MobilePageHeader
          title={t('navigation.assets')}
          actions={searchAllowed ? [{
            href: '/assets/search',
            icon: <SearchOutline aria-hidden="true" />,
            label: t('assets.search'),
          }] : []}
        />
        <MobileSegmentTabs activeKey={activeTab} onChange={onTabChange}>
          <MobileSegmentTabs.Tab key="followed" title={t('assets.tabs.followed')} />
          <MobileSegmentTabs.Tab
            key="all"
            title={(
              <span
                className={`${styles.allTabTitle}${showAllTabWorkbenchChrome ? ` ${styles.allTabTitleWorkbench}` : ''}${categoryPickerOpen ? ` ${styles.allTabTitleOpen}` : ''}`}
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
                        // 与 Web 关注面板一致：取消关注只就地翻星，行保留，
                        // 下拉刷新或重新进入重新解析后才消失
                        <AssetListCard
                          asset={asset}
                          modelName={modelMap.get(asset.modelId)?.name || asset.modelId}
                          modelIcon={modelMap.get(asset.modelId)?.icon}
                          followed={follow.isFollowed(asset.modelId, asset.id) || follow.status !== 'ready'}
                          followPending={follow.isPending(asset.modelId, asset.id)}
                          followStatus={follow.status}
                          onToggleFollow={(target) => { void follow.toggleFollow(target); }}
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
