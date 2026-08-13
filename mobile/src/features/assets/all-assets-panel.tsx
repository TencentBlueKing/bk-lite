'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InfiniteScroll, Popup } from 'antd-mobile';
import { AppstoreOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MobileSearchBar from '@/components/mobile-search-bar';
import { useAuth } from '@/context/auth';
import { listAssetCatalog, listAssetInstances } from '@/features/assets/adapter';
import AssetListCard from '@/features/assets/asset-list-card';
import { resolveAssetModelIconUrl } from '@/features/assets/model-icon';
import { useFollowedAssets } from '@/features/assets/use-followed-assets';
import {
  classificationIdForModel,
  groupAssetModels,
  modelsInClassification,
  resolveDefaultAssetModel,
  ASSET_PAGE_SIZE,
  type AssetClassification,
  type AssetInstance,
  type AssetModel,
} from '@/features/assets/model';
import {
  readMobileViewSnapshot,
  restoreMobileViewScroll,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { shouldShowListPagination } from '@/utils/listPagination';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/assets/assets.module.css';

interface ModelListCache {
  keyword: string;
  instances: AssetInstance[];
  count: number;
  page: number;
  scrollTop: number;
}

interface AllAssetsPanelState {
  classifications: AssetClassification[];
  models: AssetModel[];
  selectedClassificationId: string;
  selectedModelId: string;
  keyword: string;
  instances: AssetInstance[];
  count: number;
  page: number;
  modelCaches: Record<string, ModelListCache>;
  landingScrollTop: number;
}

interface AllAssetsPanelProps {
  classificationId?: string;
  modelId?: string;
  modelName?: string;
  categoryPickerOpen?: boolean;
  onCategoryPickerOpenChange?: (open: boolean) => void;
  onWorkbenchMetaChange?: (meta: { name: string; modelCount: number } | null) => void;
}

function CategoryModelIcon({ model }: { model: AssetModel }) {
  const src = resolveAssetModelIconUrl(model.icon, model.id);
  const [failed, setFailed] = useState(false);

  return (
    <span className={styles.categoryModelIcon} aria-hidden="true">
      {src && !failed ? (
        <img
          className={styles.categoryModelImage}
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : <AppstoreOutline className={styles.categoryModelFallback} />}
    </span>
  );
}

export default function AllAssetsPanel({
  classificationId = '',
  modelId = '',
  modelName = '',
  categoryPickerOpen,
  onCategoryPickerOpenChange,
  onWorkbenchMetaChange,
}: AllAssetsPanelProps) {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const router = useRouter();
  const follow = useFollowedAssets();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const cacheView = 'assets-all-panel';
  const initialSnapshot = useRef(readMobileViewSnapshot<AllAssetsPanelState>(cacheScope, cacheView));
  const [classifications, setClassifications] = useState<AssetClassification[]>(
    initialSnapshot.current?.data.classifications || [],
  );
  const [models, setModels] = useState<AssetModel[]>(initialSnapshot.current?.data.models || []);
  const snapshotMatchesUrl = Boolean(
    initialSnapshot.current
    && (classificationId || modelId)
    && (!classificationId
      || initialSnapshot.current.data.selectedClassificationId === classificationId)
    && (!modelId || initialSnapshot.current.data.selectedModelId === modelId),
  );
  const [selectedClassificationId, setSelectedClassificationId] = useState(classificationId || '');
  const [selectedModelId, setSelectedModelId] = useState(
    snapshotMatchesUrl ? (initialSnapshot.current?.data.selectedModelId || modelId || '') : (modelId || ''),
  );
  const [catalogStatus, setCatalogStatus] = useState<'loading' | 'ready' | 'missing' | 'error'>(
    initialSnapshot.current ? 'ready' : 'loading',
  );
  const initialKeyword = snapshotMatchesUrl ? (initialSnapshot.current?.data.keyword || '') : '';
  const [input, setInput] = useState(initialKeyword);
  const [keyword, setKeyword] = useState(initialKeyword);
  const [instances, setInstances] = useState<AssetInstance[]>(
    snapshotMatchesUrl ? (initialSnapshot.current?.data.instances || []) : [],
  );
  const [count, setCount] = useState(
    snapshotMatchesUrl ? (initialSnapshot.current?.data.count || 0) : 0,
  );
  const [page, setPage] = useState(
    snapshotMatchesUrl ? (initialSnapshot.current?.data.page || 0) : 0,
  );
  const [listStatus, setListStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    snapshotMatchesUrl ? 'ready' : 'idle',
  );
  const [modelCaches, setModelCaches] = useState<Record<string, ModelListCache>>(
    initialSnapshot.current?.data.modelCaches || {},
  );
  const [internalPickerOpen, setInternalPickerOpen] = useState(false);
  const pickerOpen = categoryPickerOpen ?? internalPickerOpen;
  const setPickerOpen = useCallback((open: boolean) => {
    if (onCategoryPickerOpenChange) onCategoryPickerOpenChange(open);
    else setInternalPickerOpen(open);
  }, [onCategoryPickerOpenChange]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const selectedClassificationIdRef = useRef(selectedClassificationId);
  const selectedModelIdRef = useRef(selectedModelId);
  const keywordRef = useRef(keyword);
  const instancesRef = useRef(instances);
  const countRef = useRef(count);
  const pageRef = useRef(page);
  const modelCachesRef = useRef(modelCaches);
  const lastRequestedKey = useRef<string | null>(
    snapshotMatchesUrl && initialSnapshot.current?.data.selectedModelId
      ? `${initialSnapshot.current.data.selectedModelId}:${initialSnapshot.current.data.keyword}`
      : null,
  );
  const catalogRequestId = useRef(0);
  const listRequestId = useRef(0);
  const catalogController = useRef<AbortController | null>(null);
  const listController = useRef<AbortController | null>(null);
  // 点击轨上模型会先改本地再 replace URL；URL 未追上前忽略旧 modelId，避免选中被打回。
  const optimisticModelIdRef = useRef<string | null>(null);

  selectedClassificationIdRef.current = selectedClassificationId;
  selectedModelIdRef.current = selectedModelId;
  keywordRef.current = keyword;
  instancesRef.current = instances;
  countRef.current = count;
  pageRef.current = page;
  modelCachesRef.current = modelCaches;

  const modelGroups = useMemo(
    () => groupAssetModels(classifications, models),
    [classifications, models],
  );
  const selectedClassification = useMemo(
    () => modelGroups.find((group) => group.classification.id === selectedClassificationId)?.classification || null,
    [modelGroups, selectedClassificationId],
  );
  const classificationModels = useMemo(
    () => (selectedClassificationId ? modelsInClassification(models, selectedClassificationId) : []),
    [models, selectedClassificationId],
  );
  const selectedModel = useMemo(
    () => classificationModels.find((model) => model.id === selectedModelId) || null,
    [classificationModels, selectedModelId],
  );
  const inWorkbench = Boolean(selectedClassificationId);

  useEffect(() => {
    if (!onWorkbenchMetaChange) return;
    if (!inWorkbench || !selectedClassification) {
      onWorkbenchMetaChange(null);
      return;
    }
    onWorkbenchMetaChange({
      name: selectedClassification.name,
      modelCount: classificationModels.length,
    });
  }, [classificationModels.length, inWorkbench, onWorkbenchMetaChange, selectedClassification]);

  const syncUrl = useCallback((nextClassificationId: string, nextModel?: AssetModel | null) => {
    const nextParams = new URLSearchParams();
    if (nextClassificationId) {
      nextParams.set('classificationId', nextClassificationId);
      const name = classifications.find((item) => item.id === nextClassificationId)?.name || '';
      if (name) nextParams.set('classificationName', name);
    }
    if (nextModel) {
      nextParams.set('modelId', nextModel.id);
      nextParams.set('modelName', nextModel.name);
    }
    const query = nextParams.toString();
    router.replace(query ? `/assets?${query}` : '/assets');
  }, [classifications, router]);

  const captureCurrentCache = useCallback((): Record<string, ModelListCache> => {
    const currentId = selectedModelIdRef.current;
    if (!currentId) return modelCachesRef.current;
    return {
      ...modelCachesRef.current,
      [currentId]: {
        keyword: keywordRef.current,
        instances: instancesRef.current,
        count: countRef.current,
        page: pageRef.current,
        scrollTop: scrollRef.current?.scrollTop || 0,
      },
    };
  }, []);

  const restoreModelState = useCallback((next: AssetModel, caches: Record<string, ModelListCache>) => {
    const cached = caches[next.id];
    setSelectedClassificationId(next.classificationId);
    setSelectedModelId(next.id);
    const cachedKeyword = cached?.keyword || '';
    setInput(cachedKeyword);
    setKeyword(cachedKeyword);
    setInstances(cached?.instances || []);
    setCount(cached?.count || 0);
    setPage(cached?.page || 0);
    setListStatus(cached ? 'ready' : 'idle');
    lastRequestedKey.current = null;
    setModelCaches(caches);
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = cached?.scrollTop || 0;
    });
  }, []);

  const applyModel = useCallback((next: AssetModel, replaceUrl = true) => {
    if (selectedModelIdRef.current === next.id && selectedClassificationIdRef.current === next.classificationId) {
      return;
    }
    const caches = captureCurrentCache();
    optimisticModelIdRef.current = next.id;
    restoreModelState(next, caches);
    if (replaceUrl) syncUrl(next.classificationId, next);
  }, [captureCurrentCache, restoreModelState, syncUrl]);

  const openClassification = useCallback((nextClassificationId: string, preferredModelId = '') => {
    const scoped = modelsInClassification(models, nextClassificationId);
    const preferred = resolveDefaultAssetModel(
      scoped,
      preferredModelId || (selectedClassificationIdRef.current === nextClassificationId ? selectedModelIdRef.current : ''),
    );
    if (!preferred) {
      setSelectedClassificationId(nextClassificationId);
      setSelectedModelId('');
      setInstances([]);
      setCount(0);
      setPage(0);
      setInput('');
      setKeyword('');
      setListStatus('idle');
      syncUrl(nextClassificationId, null);
      return;
    }
    applyModel(preferred, true);
  }, [applyModel, models, syncUrl]);

  const backToLanding = useCallback(() => {
    captureCurrentCache();
    setPickerOpen(false);
    setSelectedClassificationId('');
    setSelectedModelId('');
    setInput('');
    setKeyword('');
    setInstances([]);
    setCount(0);
    setPage(0);
    setListStatus('idle');
    lastRequestedKey.current = null;
    syncUrl('', null);
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = initialSnapshot.current?.data.landingScrollTop || 0;
      }
    });
  }, [captureCurrentCache, syncUrl]);

  const pickClassification = useCallback((nextClassificationId: string) => {
    setPickerOpen(false);
    if (nextClassificationId === selectedClassificationIdRef.current) return;
    openClassification(nextClassificationId);
  }, [openClassification]);

  const loadCatalog = useCallback(async () => {
    const currentId = ++catalogRequestId.current;
    catalogController.current?.abort();
    const controller = new AbortController();
    catalogController.current = controller;
    setCatalogStatus('loading');
    try {
      const catalog = await listAssetCatalog(controller.signal);
      if (currentId !== catalogRequestId.current) return;
      setClassifications(catalog.classifications);
      setModels(catalog.models);
      const groups = groupAssetModels(catalog.classifications, catalog.models);
      if (!groups.length) {
        setSelectedClassificationId('');
        setSelectedModelId('');
        setCatalogStatus('missing');
        return;
      }
      setCatalogStatus('ready');

      const urlModelId = modelId || '';
      const urlClassificationId = classificationId
        || classificationIdForModel(catalog.models, urlModelId);
      if (!urlClassificationId && !urlModelId) {
        setSelectedClassificationId('');
        setSelectedModelId('');
        setListStatus('idle');
        return;
      }
      const scoped = modelsInClassification(catalog.models, urlClassificationId);
      const preferred = resolveDefaultAssetModel(scoped, urlModelId || selectedModelIdRef.current);
      if (preferred) {
        const caches = captureCurrentCache();
        restoreModelState(preferred, caches);
        if (preferred.classificationId !== classificationId || preferred.id !== modelId) {
          syncUrl(preferred.classificationId, preferred);
        }
      } else if (urlClassificationId) {
        setSelectedClassificationId(urlClassificationId);
        setSelectedModelId('');
        setListStatus('idle');
        if (urlClassificationId !== classificationId) syncUrl(urlClassificationId, null);
      } else {
        setSelectedClassificationId('');
        setSelectedModelId('');
      }
    } catch (error) {
      if (controller.signal.aborted || currentId !== catalogRequestId.current) return;
      setCatalogStatus('error');
      throw error;
    }
  }, [captureCurrentCache, classificationId, modelId, restoreModelState, syncUrl]);

  const loadInstances = useCallback(async (
    targetModelId: string,
    targetPage = 1,
    append = false,
    preserveContent = false,
  ) => {
    const currentId = ++listRequestId.current;
    listController.current?.abort();
    const controller = new AbortController();
    listController.current = controller;
    if (!append && !preserveContent) setListStatus('loading');
    try {
      const result = await listAssetInstances(
        targetModelId,
        targetPage,
        keywordRef.current.trim(),
        controller.signal,
      );
      if (currentId !== listRequestId.current) return;
      setInstances((current) => append
        ? [...new Map([...current, ...result.items].map((item) => [String(item.id), item])).values()]
        : result.items);
      setCount(result.count);
      setPage(targetPage);
      setListStatus('ready');
    } catch (error) {
      if (controller.signal.aborted || currentId !== listRequestId.current) return;
      if (!append && !preserveContent) setListStatus('error');
      throw error;
    }
  }, []);

  useEffect(() => {
    if (initialSnapshot.current) return;
    void loadCatalog().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (catalogStatus !== 'ready' || !models.length) return;
    const resolvedClassificationId = classificationId
      || classificationIdForModel(models, modelId);
    if (!resolvedClassificationId && !modelId) {
      optimisticModelIdRef.current = null;
      if (selectedClassificationIdRef.current) {
        setSelectedClassificationId('');
        setSelectedModelId('');
        setListStatus('idle');
      }
      return;
    }
    const scoped = modelsInClassification(models, resolvedClassificationId);

    if (optimisticModelIdRef.current && modelId !== optimisticModelIdRef.current) {
      const optimistic = scoped.find((item) => item.id === optimisticModelIdRef.current) || null;
      if (optimistic) {
        if (
          selectedModelIdRef.current !== optimistic.id
          || selectedClassificationIdRef.current !== optimistic.classificationId
        ) {
          restoreModelState(optimistic, captureCurrentCache());
        }
        return;
      }
      optimisticModelIdRef.current = null;
    }
    if (optimisticModelIdRef.current && modelId === optimisticModelIdRef.current) {
      optimisticModelIdRef.current = null;
    }

    const nextModel = resolveDefaultAssetModel(scoped, modelId || selectedModelIdRef.current);
    if (!nextModel) {
      if (selectedClassificationIdRef.current !== resolvedClassificationId) {
        setSelectedClassificationId(resolvedClassificationId);
        setSelectedModelId('');
      }
      return;
    }
    if (
      selectedModelIdRef.current === nextModel.id
      && selectedClassificationIdRef.current === nextModel.classificationId
    ) {
      if (nextModel.classificationId !== classificationId || nextModel.id !== modelId) {
        syncUrl(nextModel.classificationId, nextModel);
      }
      return;
    }
    const caches = captureCurrentCache();
    restoreModelState(nextModel, caches);
    if (nextModel.classificationId !== classificationId || nextModel.id !== modelId) {
      syncUrl(nextModel.classificationId, nextModel);
    }
  }, [
    captureCurrentCache,
    catalogStatus,
    classificationId,
    modelId,
    models,
    restoreModelState,
    syncUrl,
  ]);

  useEffect(() => {
    if (!selectedModel || !inWorkbench) return;
    const requestKey = `${selectedModel.id}:${keyword}`;
    if (lastRequestedKey.current === requestKey) return;
    const hasContent = instancesRef.current.length > 0
      && selectedModelIdRef.current === selectedModel.id;
    lastRequestedKey.current = requestKey;
    void loadInstances(selectedModel.id, 1, false, hasContent).catch(() => undefined);
  }, [inWorkbench, keyword, loadInstances, selectedModel]);

  const submitSearch = (value: string) => {
    const next = value.trim();
    setInput(value);
    setKeyword(next);
  };

  const clearSearch = () => {
    setInput('');
    setKeyword('');
  };

  useEffect(() => () => {
    catalogRequestId.current += 1;
    listRequestId.current += 1;
    catalogController.current?.abort();
    listController.current?.abort();
  }, []);

  useEffect(() => {
    const rail = railRef.current;
    const active = rail?.querySelector<HTMLElement>(`[data-model-id="${selectedModel?.id || ''}"]`);
    if (!rail || !active) return;
    const railRect = rail.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    if (activeRect.left >= railRect.left && activeRect.right <= railRect.right) return;
    active.scrollIntoView({ behavior: 'auto', inline: 'nearest', block: 'nearest' });
  }, [selectedModel?.id]);

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (catalogStatus !== 'ready') return;
    const nextCaches = selectedModelId
      ? {
        ...modelCaches,
        [selectedModelId]: {
          keyword,
          instances,
          count,
          page,
          scrollTop: inWorkbench ? scrollTop : (modelCaches[selectedModelId]?.scrollTop || 0),
        },
      }
      : modelCaches;
    writeMobileViewSnapshot<AllAssetsPanelState>(cacheScope, cacheView, {
      classifications,
      models,
      selectedClassificationId,
      selectedModelId,
      keyword,
      instances,
      count,
      page,
      modelCaches: nextCaches,
      landingScrollTop: inWorkbench
        ? (initialSnapshot.current?.data.landingScrollTop || 0)
        : scrollTop,
    }, scrollTop);
  }, [
    cacheScope,
    catalogStatus,
    classifications,
    count,
    inWorkbench,
    instances,
    keyword,
    modelCaches,
    models,
    page,
    selectedClassificationId,
    selectedModelId,
  ]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    restoreMobileViewScroll(
      scrollRef.current,
      inWorkbench
        ? initialSnapshot.current?.scrollTop
        : initialSnapshot.current?.data.landingScrollTop,
    );
  }, [inWorkbench]);

  const displayName = selectedModel?.name || modelName || selectedModelId;

  return (
    <div className={styles.allPanel}>
      {catalogStatus === 'ready' && inWorkbench && selectedClassification && (
        <div className={styles.listChrome}>
          {classificationModels.length > 0 ? (
            <div className={styles.modelRail}>
              <div className={styles.neighborRail} ref={railRef}>
                {classificationModels.map((model) => {
                  const active = model.id === selectedModel?.id;
                  return (
                    <button
                      type="button"
                      key={model.id}
                      data-model-id={model.id}
                      aria-pressed={active}
                      className={`${styles.neighborChip} ${active ? styles.neighborChipActive : ''}`}
                      onClick={() => applyModel(model)}
                    >
                      <span>{model.name}</span>
                      {model.count > 0 ? (
                        <span className={styles.neighborChipCount}>·{model.count}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}
          {selectedModel ? (
            <div className={styles.instanceSearch}>
              <MobileSearchBar
                value={input}
                onChange={setInput}
                onSearch={submitSearch}
                onClear={clearSearch}
                placeholder={t('assets.searchModel', undefined, { name: displayName })}
              />
            </div>
          ) : null}
        </div>
      )}

      <div
        className={styles.scroll}
        ref={scrollRef}
        onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}
      >
        {catalogStatus === 'loading' ? (
          <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
        ) : catalogStatus === 'error' ? (
          <MobileResult
            kind="error"
            title={t('assets.loadFailed')}
            description={t('assets.retryHint')}
            actionLabel={t('common.retry')}
            onAction={() => void loadCatalog().catch(() => undefined)}
          />
        ) : catalogStatus === 'missing' || modelGroups.length === 0 ? (
          <MobileResult kind="empty" title={t('assets.noClassifications')} />
        ) : !inWorkbench ? (
          <MobilePullToRefresh
            disabled={catalogStatus !== 'ready'}
            onRefresh={() => loadCatalog()}
          >
            <div className={styles.refreshContent}>
              <div className={styles.landingBody}>
                <div className={styles.categoryList}>
                  {modelGroups.map((group) => {
                    const assetTotal = group.models.reduce((sum, model) => sum + model.count, 0);
                    return (
                      <button
                        type="button"
                        className={styles.categoryRow}
                        key={group.classification.id}
                        onClick={() => openClassification(group.classification.id)}
                      >
                        <span className={styles.categoryModelIcons} aria-hidden="true">
                          {group.models.slice(0, 3).map((model) => (
                            <CategoryModelIcon key={model.id} model={model} />
                          ))}
                        </span>
                        <span className={styles.categoryRowCopy}>
                          <span className={styles.categoryRowName}>{group.classification.name}</span>
                          <span className={styles.categoryRowMeta}>
                            {t('assets.categoryModelCount', undefined, { count: group.models.length })}
                          </span>
                        </span>
                        <span
                          className={`${styles.categoryRowCount}${assetTotal === 0 ? ` ${styles.categoryRowCountEmpty}` : ''}`}
                        >
                          {assetTotal}
                        </span>
                        <span className={styles.categoryRowChevron} aria-hidden="true">›</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </MobilePullToRefresh>
        ) : !selectedModel ? (
          <MobileResult
            kind="empty"
            title={t('assets.noModels')}
            actionLabel={t('assets.backToCategories')}
            onAction={backToLanding}
          />
        ) : (
          <MobilePullToRefresh
            disabled={listStatus === 'loading'}
            onRefresh={() => loadInstances(selectedModel.id, 1, false, true)}
          >
            <div className={styles.refreshContent}>
              {listStatus === 'loading' || listStatus === 'idle' ? (
                <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
              ) : listStatus === 'error' ? (
                <MobileResult
                  kind="error"
                  title={t('assets.instanceLoadFailed')}
                  description={t('assets.retryHint')}
                  actionLabel={t('common.retry')}
                  onAction={() => void loadInstances(selectedModel.id).catch(() => undefined)}
                />
              ) : instances.length === 0 ? (
                <MobileResult
                  kind="empty"
                  title={keyword ? t('assets.noSearchResults') : t('assets.noInstances')}
                  description={!keyword ? t('assets.noInstancesHint') : undefined}
                />
              ) : (
                <div className={styles.assetTable}>
                  {instances.map((asset) => (
                    <AssetListCard
                      asset={asset}
                      modelName={displayName}
                      modelIcon={selectedModel.icon}
                      classificationId={selectedClassificationId}
                      classificationName={selectedClassification?.name || ''}
                      showModel={false}
                      followed={follow.isFollowed(selectedModel.id, asset.id)}
                      followPending={follow.isPending(selectedModel.id, asset.id)}
                      followStatus={follow.status}
                      onToggleFollow={(target) => { void follow.toggleFollow(target, selectedModel.id); }}
                      key={String(asset.id)}
                    />
                  ))}
                  {shouldShowListPagination(count, instances.length, ASSET_PAGE_SIZE) && (
                    <InfiniteScroll
                      hasMore={instances.length < count}
                      loadMore={() => loadInstances(selectedModel.id, page + 1, true).catch(() => undefined)}
                    />
                  )}
                </div>
              )}
            </div>
          </MobilePullToRefresh>
        )}
      </div>

      <Popup
        visible={pickerOpen}
        onMaskClick={() => setPickerOpen(false)}
        bodyStyle={{
          height: '70vh',
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div className={styles.picker}>
          <div className={styles.pickerHeader}>
            <strong className={styles.pickerTitle}>{t('assets.selectClassificationTitle')}</strong>
            <button
              type="button"
              className={styles.pickerClose}
              onClick={() => setPickerOpen(false)}
            >
              {t('common.cancel')}
            </button>
          </div>
          <div className={styles.pickerBody}>
            <button
              type="button"
              className={`${styles.pickerRow} ${!selectedClassificationId ? styles.pickerRowActive : ''}`}
              onClick={backToLanding}
            >
              <span className={styles.pickerRowCopy}>
                <span className={styles.pickerRowName}>{t('assets.tabs.all')}</span>
                <span className={styles.pickerRowMeta}>{t('assets.browseByCategory')}</span>
              </span>
              <span className={styles.pickerRowAction}>
                {!selectedClassificationId ? t('assets.currentClassification') : t('assets.selectClassificationAction')}
              </span>
            </button>
            {modelGroups.map((group) => {
              const active = group.classification.id === selectedClassificationId;
              const assetTotal = group.models.reduce((sum, model) => sum + model.count, 0);
              return (
                <button
                  type="button"
                  key={group.classification.id}
                  className={`${styles.pickerRow} ${active ? styles.pickerRowActive : ''}`}
                  onClick={() => pickClassification(group.classification.id)}
                >
                  <span className={styles.pickerRowCopy}>
                    <span className={styles.pickerRowName}>{group.classification.name}</span>
                    <span className={styles.pickerRowMeta}>
                      {t('assets.categoryRowMeta', undefined, {
                        models: group.models.length,
                        assets: assetTotal,
                      })}
                    </span>
                  </span>
                  <span className={styles.pickerRowAction}>
                    {active ? t('assets.currentClassification') : t('assets.selectClassificationAction')}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </Popup>
    </div>
  );
}
