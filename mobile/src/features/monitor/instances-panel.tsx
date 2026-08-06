'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type TouchEvent } from 'react';
import { InfiniteScroll, Popup } from 'antd-mobile';
import MobileSearchBar from '@/components/mobile-search-bar';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { useAuth } from '@/context/auth';
import { listMonitorInstances, listMonitorObjects } from '@/features/monitor/adapter';
import {
  INSTANCE_LIST_SUMMARY_LIMIT,
  MONITOR_PAGE_SIZE,
  groupMonitorObjects,
  instanceListSummaryEntries,
  instanceSummaryEntries,
  orderedMonitorObjects,
  sortMonitorInstances,
  type MonitorInstance,
  type MonitorObject,
} from '@/features/monitor/model';
import MonitorObjectIcon from '@/features/monitor/object-icon-image';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import {
  readMobileViewSnapshot,
  restoreMobileViewScroll,
  writeMobileViewSnapshot,
} from '@/navigation/mobile-view-cache';
import { shouldShowListPagination } from '@/utils/listPagination';
import { getCurrentTeamCookie } from '@/utils/teamCookie';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/monitor/monitor.module.css';

type ListMode = 'all' | 'loaded_issue';

interface MonitorInstancesViewState {
  monitorObject: MonitorObject | null;
  objects: MonitorObject[];
  keyword: string;
  mode: ListMode;
  instances: MonitorInstance[];
  count: number;
  page: number;
}

interface MonitorInstancesPanelProps {
  objectId?: number;
  objectName?: string;
}

export default function MonitorInstancesPanel({ objectId = 0 }: MonitorInstancesPanelProps) {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const router = useRouter();
  const cacheScope = `${userInfo?.id || 0}:${getCurrentTeamCookie() || 'none'}`;
  const cacheView = 'monitor-instances-panel';
  const initialSnapshot = useRef(readMobileViewSnapshot<MonitorInstancesViewState>(cacheScope, cacheView));
  const [objects, setObjects] = useState<MonitorObject[]>(initialSnapshot.current?.data.objects || []);
  const [monitorObject, setMonitorObject] = useState<MonitorObject | null>(initialSnapshot.current?.data.monitorObject || null);
  const [objectStatus, setObjectStatus] = useState<'loading' | 'ready' | 'missing' | 'error'>(initialSnapshot.current ? 'ready' : 'loading');
  const [keyword, setKeyword] = useState(initialSnapshot.current?.data.keyword || '');
  const [mode, setMode] = useState<ListMode>(initialSnapshot.current?.data.mode || 'all');
  const [instances, setInstances] = useState<MonitorInstance[]>(initialSnapshot.current?.data.instances || []);
  const [count, setCount] = useState(initialSnapshot.current?.data.count || 0);
  const [page, setPage] = useState(initialSnapshot.current?.data.page || 0);
  const [listStatus, setListStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(initialSnapshot.current ? 'ready' : 'idle');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerKeyword, setPickerKeyword] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const touchStart = useRef<{ x: number; y: number; edge: boolean; onTable: boolean } | null>(null);
  const lastRequestedKey = useRef<string | null>(
    initialSnapshot.current?.data.monitorObject
      ? `${initialSnapshot.current.data.monitorObject.id}:${initialSnapshot.current.data.keyword}`
      : null,
  );
  const objectRequestId = useRef(0);
  const listRequestId = useRef(0);
  const objectController = useRef<AbortController | null>(null);
  const listController = useRef<AbortController | null>(null);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };

  const orderedObjects = useMemo(() => orderedMonitorObjects(objects), [objects]);
  const objectGroups = useMemo(() => groupMonitorObjects(objects), [objects]);
  const currentIndex = useMemo(
    () => orderedObjects.findIndex((item) => item.id === monitorObject?.id),
    [monitorObject?.id, orderedObjects],
  );
  const sortedInstances = useMemo(() => sortMonitorInstances(instances), [instances]);
  const visibleInstances = useMemo(
    () => (mode === 'loaded_issue'
      ? sortedInstances.filter((item) => item.status !== 'normal')
      : sortedInstances),
    [mode, sortedInstances],
  );
  const loadedIssueCount = useMemo(
    () => sortedInstances.filter((item) => item.status !== 'normal').length,
    [sortedInstances],
  );
  const pickerGroups = useMemo(() => {
    const needle = pickerKeyword.trim().toLowerCase();
    if (!needle) return objectGroups;
    return objectGroups
      .map((group) => ({
        ...group,
        objects: group.objects.filter((item) => item.displayName.toLowerCase().includes(needle)
          || item.name.toLowerCase().includes(needle)),
      }))
      .filter((group) => group.objects.length > 0);
  }, [objectGroups, pickerKeyword]);

  const syncUrl = useCallback((next: MonitorObject) => {
    const nextParams = new URLSearchParams({
      objectId: String(next.id),
      objectName: next.displayName,
    });
    router.replace(`/monitor?${nextParams.toString()}`);
  }, [router]);

  const applyObject = useCallback((next: MonitorObject, replaceUrl = true) => {
    if (monitorObject?.id === next.id) {
      setPickerOpen(false);
      return;
    }
    setMonitorObject(next);
    setKeyword('');
    lastRequestedKey.current = null;
    setMode('all');
    setInstances([]);
    setCount(0);
    setPage(0);
    setListStatus('idle');
    setPickerOpen(false);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    if (replaceUrl) syncUrl(next);
  }, [monitorObject?.id, syncUrl]);

  const loadObjects = useCallback(async () => {
    const currentId = ++objectRequestId.current;
    objectController.current?.abort();
    const controller = new AbortController();
    objectController.current = controller;
    setObjectStatus('loading');
    try {
      const nextObjects = await listMonitorObjects(controller.signal);
      if (currentId !== objectRequestId.current) return;
      setObjects(nextObjects);
      const ordered = orderedMonitorObjects(nextObjects);
      const preferred = (objectId && ordered.find((item) => item.id === objectId)) || ordered[0] || null;
      setMonitorObject(preferred);
      setObjectStatus(preferred ? 'ready' : 'missing');
      if (preferred && preferred.id !== objectId) syncUrl(preferred);
    } catch (error) {
      if (controller.signal.aborted || currentId !== objectRequestId.current) return;
      setObjectStatus('error');
      throw error;
    }
  }, [objectId, syncUrl]);

  const loadInstances = useCallback(async (
    object: MonitorObject,
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
      const result = await listMonitorInstances(object.id, targetPage, keyword.trim(), controller.signal);
      if (currentId !== listRequestId.current) return;
      setInstances((current) => append
        ? [...new Map([...current, ...result.items].map((item) => [item.id, item])).values()]
        : result.items);
      setCount(result.count);
      setPage(targetPage);
      setListStatus('ready');
    } catch (error) {
      if (controller.signal.aborted || currentId !== listRequestId.current) return;
      if (!append && !preserveContent) setListStatus('error');
      throw error;
    }
  }, [keyword]);

  useEffect(() => {
    if (initialSnapshot.current) return;
    void loadObjects().catch(() => undefined);
    // 仅首屏拉对象树；切换 objectId 由下方 effect 处理，避免重复请求。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!objects.length) return;
    const ordered = orderedMonitorObjects(objects);
    const nextObject = (objectId && ordered.find((item) => item.id === objectId))
      || ordered.find((item) => item.id === monitorObject?.id)
      || ordered[0]
      || null;
    if (!nextObject) {
      setMonitorObject(null);
      setObjectStatus('missing');
      return;
    }
    setObjectStatus('ready');
    if (monitorObject?.id === nextObject.id) return;
    setMonitorObject(nextObject);
    setKeyword('');
    lastRequestedKey.current = null;
    setMode('all');
    setInstances([]);
    setCount(0);
    setPage(0);
    setListStatus('idle');
    if (nextObject.id !== objectId) syncUrl(nextObject);
  }, [monitorObject?.id, objectId, objects, syncUrl]);

  useEffect(() => {
    if (!monitorObject) return;
    const requestKey = `${monitorObject.id}:${keyword}`;
    if (lastRequestedKey.current === requestKey) return;
    const timer = window.setTimeout(() => {
      lastRequestedKey.current = requestKey;
      void loadInstances(monitorObject).catch(() => undefined);
    }, 280);
    return () => window.clearTimeout(timer);
  }, [keyword, loadInstances, monitorObject]);

  useEffect(() => () => {
    objectRequestId.current += 1;
    listRequestId.current += 1;
    objectController.current?.abort();
    listController.current?.abort();
  }, []);

  useEffect(() => {
    const active = railRef.current?.querySelector<HTMLElement>(`[data-object-id="${monitorObject?.id || ''}"]`);
    active?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [monitorObject?.id]);

  const saveSnapshot = useCallback((scrollTop = scrollRef.current?.scrollTop || 0) => {
    if (objectStatus !== 'ready' || listStatus !== 'ready' || !monitorObject) return;
    writeMobileViewSnapshot<MonitorInstancesViewState>(cacheScope, cacheView, {
      monitorObject,
      objects,
      keyword,
      mode,
      instances,
      count,
      page,
    }, scrollTop);
  }, [cacheScope, count, instances, keyword, listStatus, mode, monitorObject, objectStatus, objects, page]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, []);

  const shiftObject = useCallback((delta: number) => {
    if (currentIndex < 0) return;
    const next = orderedObjects[currentIndex + delta];
    if (next) applyObject(next);
  }, [applyObject, currentIndex, orderedObjects]);

  const onTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    const touch = event.changedTouches[0];
    if (!touch || !scrollRef.current) return;
    const edge = touch.clientX - scrollRef.current.getBoundingClientRect().left < scrollRef.current.clientWidth * 0.18;
    const onTable = Boolean((event.target as Element | null)?.closest?.(`[data-instance-table-scroll]`));
    touchStart.current = { x: touch.clientX, y: touch.clientY, edge, onTable };
  };

  const onTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    const start = touchStart.current;
    touchStart.current = null;
    const touch = event.changedTouches[0];
    if (!start || start.edge || start.onTable || !touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < 72 || Math.abs(dx) < Math.abs(dy) * 1.4) return;
    if (dx < 0) shiftObject(1);
    else shiftObject(-1);
  };

  const hasMore = mode === 'all' && listStatus === 'ready' && instances.length < count;
  const resultCount = listStatus === 'ready' ? count : monitorObject?.instanceCount || 0;
  const summaryFields = (monitorObject?.displayFields || []).slice(0, INSTANCE_LIST_SUMMARY_LIMIT);
  const tableGridColumns = [
    'minmax(160px, 1.4fr)',
    '48px',
    '78px',
    ...summaryFields.map(() => 'minmax(68px, 84px)'),
  ].join(' ');

  return (
    <div className={styles.instancesPanel}>
      {objectStatus === 'ready' && monitorObject && (
        <div className={styles.listChrome}>
          <div className={styles.objectRail}>
            <div
              className={styles.objectChips}
              ref={railRef}
              role="tablist"
              aria-label={t('monitor.selectObjectTitle')}
            >
              {orderedObjects.map((object) => {
                const active = object.id === monitorObject.id;
                return (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={active}
                    key={object.id}
                    data-object-id={object.id}
                    className={`${styles.objectChip} ${active ? styles.objectChipActive : ''}`}
                    onClick={() => applyObject(object)}
                  >
                    <span>{object.displayName}</span>
                    <span className={styles.objectChipCount}>{object.instanceCount}</span>
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              className={styles.objectRailAll}
              onClick={() => { setPickerKeyword(''); setPickerOpen(true); }}
              aria-label={t('monitor.selectObjectTitle')}
            >
              <span className={styles.objectRailAllLabel}>{t('monitor.allObjects')}</span>
              <span className={styles.objectRailAllChevron} aria-hidden>›</span>
            </button>
          </div>
          <div className={styles.instanceSearch}>
            <MobileSearchBar
              value={keyword}
              onChange={setKeyword}
              placeholder={t('monitor.searchInstances')}
            />
          </div>
          <div className={styles.listToolbar}>
            <div className={styles.listModeGroup} role="tablist" aria-label={t('monitor.listModes')}>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'all'}
                className={`${styles.listMode} ${mode === 'all' ? styles.listModeActive : ''}`}
                onClick={() => setMode('all')}
              >
                {t('monitor.modeAll')}
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'loaded_issue'}
                className={`${styles.listMode} ${mode === 'loaded_issue' ? styles.listModeActive : ''}`}
                onClick={() => setMode('loaded_issue')}
              >
                {t('monitor.modeLoadedIssue')}
              </button>
            </div>
            <span className={styles.listCount}>
              {mode === 'loaded_issue'
                ? t('monitor.loadedIssueCount', undefined, { issue: loadedIssueCount, loaded: instances.length })
                : t('monitor.shortCount', undefined, { count: resultCount })}
            </span>
          </div>
        </div>
      )}
      <div
        className={styles.scroll}
        ref={scrollRef}
        onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        {objectStatus === 'loading' ? (
          <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
        ) : objectStatus !== 'ready' || !monitorObject ? (
          <MobileResult
            kind={objectStatus === 'missing' ? 'empty' : 'error'}
            title={objectStatus === 'missing' ? t('monitor.noObjects') : t('monitor.objectLoadFailed')}
            description={objectStatus === 'error' ? t('monitor.retryHint') : ''}
            actionLabel={objectStatus === 'error' ? t('common.retry') : undefined}
            onAction={objectStatus === 'error' ? () => void loadObjects().catch(() => undefined) : undefined}
          />
        ) : (
          <MobilePullToRefresh
            disabled={listStatus === 'loading'}
            onRefresh={() => loadInstances(monitorObject, 1, false, true)}
          >
            <div className={styles.refreshContent}>
              {listStatus === 'loading' || listStatus === 'idle' ? (
                <MobileSkeleton label={t('common.loading')} variant="list" rows={5} />
              ) : listStatus === 'error' ? (
                <MobileResult kind="error" title={t('monitor.instanceLoadFailed')} description={t('monitor.retryHint')} actionLabel={t('common.retry')} onAction={() => void loadInstances(monitorObject).catch(() => undefined)} />
              ) : visibleInstances.length === 0 ? (
                <MobileResult
                  kind="empty"
                  compact
                  title={keyword ? t('monitor.noSearchResults') : mode === 'loaded_issue' ? t('monitor.noLoadedIssues') : t('monitor.noInstances')}
                />
              ) : (
                <div className={styles.instanceTableScroll} data-instance-table-scroll>
                  <div className={styles.instanceTable}>
                    <div className={styles.instanceTableHead} style={{ gridTemplateColumns: tableGridColumns }}>
                      <span className={styles.colSticky}>{t('monitor.columnName')}</span>
                      <span className={styles.colRight}>{t('monitor.columnStatus')}</span>
                      <span className={styles.colRight}>{t('monitor.columnReported')}</span>
                      {summaryFields.map((field) => (
                        <span className={styles.colRight} key={field.key || field.name}>{field.name}</span>
                      ))}
                    </div>
                    {visibleInstances.map((instance) => {
                      const summary = instanceListSummaryEntries(monitorObject, instance);
                      const detailParams = new URLSearchParams({
                        objectId: String(monitorObject.id),
                        objectName: monitorObject.displayName,
                        objectIcon: monitorObject.icon || '',
                        instanceId: instance.id,
                        instanceName: instance.name,
                        idValues: JSON.stringify(instance.idValues),
                        interval: String(instance.interval || ''),
                        status: instance.status,
                        lastReportedAt: String(instance.lastReportedAt || ''),
                        facts: JSON.stringify(instanceSummaryEntries(monitorObject, instance, 4)),
                      });
                      return (
                        <Link
                          className={styles.instanceRow}
                          href={`/monitor/detail?${detailParams.toString()}`}
                          key={instance.id}
                          style={{ gridTemplateColumns: tableGridColumns }}
                        >
                          <span className={`${styles.instanceIdentity} ${styles.colSticky}`}>
                            <MonitorObjectIcon
                              className={styles.instanceIcon}
                              icon={monitorObject.icon}
                              size={24}
                            />
                            <span className={styles.instanceCopy}>
                              <span className={styles.instanceName}>{instance.name}</span>
                              <span className={styles.instanceIdLine}>{instance.idValues.join(' · ') || instance.id}</span>
                            </span>
                          </span>
                          <span className={styles.status} data-status={instance.status}>
                            {instance.status ? t(`monitor.status.${instance.status}`, instance.status) : '--'}
                          </span>
                          <span className={styles.colRight}>
                            {instance.lastReportedAt
                              ? formatAccountDateTime(
                                new Date(instance.lastReportedAt * 1000).toISOString(),
                                preferences,
                                { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' },
                              )
                              : '--'}
                          </span>
                          {summaryFields.map((field, index) => (
                            <span className={styles.colRight} key={field.key || field.name}>
                              {summary[index]?.value ?? '--'}
                            </span>
                          ))}
                        </Link>
                      );
                    })}
                  </div>
                  {mode === 'all'
                    && shouldShowListPagination(count, instances.length, MONITOR_PAGE_SIZE)
                    && (
                    <InfiniteScroll
                      hasMore={hasMore}
                      loadMore={() => loadInstances(monitorObject, page + 1, true).catch(() => undefined)}
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
        bodyStyle={{ height: '78vh', borderTopLeftRadius: 16, borderTopRightRadius: 16, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      >
        <div className={styles.picker}>
          <div className={styles.pickerHeader}>
            <strong className={styles.pickerTitle}>{t('monitor.selectObjectTitle')}</strong>
            <button type="button" className={styles.pickerClose} onClick={() => setPickerOpen(false)}>{t('common.done')}</button>
          </div>
          <div className={styles.pickerSearch}>
            <MobileSearchBar
              size="page"
              value={pickerKeyword}
              onChange={setPickerKeyword}
              placeholder={t('monitor.searchObjects')}
            />
          </div>
          <div className={styles.pickerBody}>
            {pickerGroups.length === 0 ? (
              <MobileResult kind="empty" title={t('monitor.noObjects')} compact />
            ) : pickerGroups.map((group) => (
              <div key={group.type.id}>
                <div className={styles.pickerGroup}>{group.type.displayName}</div>
                {group.objects.map((object) => {
                  const active = object.id === monitorObject?.id;
                  return (
                    <button
                      type="button"
                      key={object.id}
                      className={`${styles.pickerRow} ${active ? styles.pickerRowActive : ''}`}
                      onClick={() => applyObject(object)}
                    >
                      <span className={styles.pickerRowCopy}>
                        <span className={styles.pickerRowName}>{object.displayName}</span>
                        <span className={styles.pickerRowMeta}>{t('monitor.resultCount', undefined, { count: object.instanceCount })}</span>
                      </span>
                      <span className={styles.pickerRowAction}>{active ? t('monitor.currentObject') : t('monitor.selectObjectAction')}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </Popup>
    </div>
  );
}
