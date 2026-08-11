'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InfiniteScroll, Popup } from 'antd-mobile';
import { CheckOutline, FilterOutline } from 'antd-mobile-icons';
import MobileSearchBar from '@/components/mobile-search-bar';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import { useAuth } from '@/context/auth';
import { listDisplayFieldMetrics, listMonitorInstances, listMonitorObjects } from '@/features/monitor/adapter';
import {
  MONITOR_PAGE_SIZE,
  buildDisplayMetricUnitIndex,
  displayFieldMetricNames,
  groupMonitorObjects,
  instanceListSummaryEntries,
  normalizeReportingStatusFilters,
  orderedMonitorObjects,
  resolveMonitorReportingStatus,
  type MonitorInstance,
  type MonitorObject,
  type MonitorReportingStatusFilter,
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

const REPORTING_STATUS_OPTIONS: MonitorReportingStatusFilter[] = ['normal', 'unavailable'];

interface MonitorInstancesViewState {
  monitorObject: MonitorObject | null;
  objects: MonitorObject[];
  keyword: string;
  statusFilters: MonitorReportingStatusFilter[];
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
  const [input, setInput] = useState(initialSnapshot.current?.data.keyword || '');
  const [keyword, setKeyword] = useState(initialSnapshot.current?.data.keyword || '');
  const [statusFilters, setStatusFilters] = useState<MonitorReportingStatusFilter[]>(
    normalizeReportingStatusFilters(initialSnapshot.current?.data.statusFilters),
  );
  const [statusDraft, setStatusDraft] = useState<MonitorReportingStatusFilter[]>([]);
  const [statusFilterOpen, setStatusFilterOpen] = useState(false);
  const [instances, setInstances] = useState<MonitorInstance[]>(initialSnapshot.current?.data.instances || []);
  const [count, setCount] = useState(initialSnapshot.current?.data.count || 0);
  const [page, setPage] = useState(initialSnapshot.current?.data.page || 0);
  const [listStatus, setListStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>(initialSnapshot.current ? 'ready' : 'idle');
  const [metricUnits, setMetricUnits] = useState<Map<string, string>>(new Map());
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerKeyword, setPickerKeyword] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const snapshotRefreshPending = useRef(Boolean(initialSnapshot.current));
  const statusFilterKey = statusFilters.join(',');
  const lastRequestedKey = useRef<string | null>(
    initialSnapshot.current?.data.monitorObject
      ? `${initialSnapshot.current.data.monitorObject.id}:${initialSnapshot.current.data.keyword}:${normalizeReportingStatusFilters(initialSnapshot.current.data.statusFilters).join(',')}`
      : null,
  );
  const objectRequestId = useRef(0);
  const listRequestId = useRef(0);
  const metricUnitRequestId = useRef(0);
  const objectController = useRef<AbortController | null>(null);
  const listController = useRef<AbortController | null>(null);
  const metricUnitController = useRef<AbortController | null>(null);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };

  const orderedObjects = useMemo(() => orderedMonitorObjects(objects), [objects]);
  const objectGroups = useMemo(() => groupMonitorObjects(objects), [objects]);
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
    setInput('');
    setKeyword('');
    setStatusFilters([]);
    setStatusFilterOpen(false);
    lastRequestedKey.current = null;
    setInstances([]);
    setCount(0);
    setPage(0);
    setListStatus('idle');
    setPickerOpen(false);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    if (replaceUrl) syncUrl(next);
  }, [monitorObject?.id, syncUrl]);

  const loadObjects = useCallback(async (preserveContent = false) => {
    const currentId = ++objectRequestId.current;
    objectController.current?.abort();
    const controller = new AbortController();
    objectController.current = controller;
    if (!preserveContent) setObjectStatus('loading');
    try {
      const nextObjects = await listMonitorObjects(controller.signal);
      if (currentId !== objectRequestId.current) return;
      setObjects(nextObjects);
      const ordered = orderedMonitorObjects(nextObjects);
      const cachedObjectId = initialSnapshot.current?.data.monitorObject?.id;
      const preferred = (objectId && ordered.find((item) => item.id === objectId))
        || (cachedObjectId && ordered.find((item) => item.id === cachedObjectId))
        || ordered[0]
        || null;
      setMonitorObject(preferred);
      setObjectStatus(preferred ? 'ready' : 'missing');
      if (preferred && preferred.id !== objectId) syncUrl(preferred);
    } catch (error) {
      if (controller.signal.aborted || currentId !== objectRequestId.current) return;
      if (!preserveContent) setObjectStatus('error');
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
      const result = await listMonitorInstances(object.id, targetPage, keyword.trim(), {
        status: statusFilters,
        signal: controller.signal,
      });
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
  }, [keyword, statusFilters]);

  useEffect(() => {
    const preserveContent = Boolean(initialSnapshot.current);
    if (preserveContent) lastRequestedKey.current = null;
    void loadObjects(preserveContent).catch(() => undefined);
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
    setInput('');
    setKeyword('');
    setStatusFilters([]);
    setStatusFilterOpen(false);
    lastRequestedKey.current = null;
    setInstances([]);
    setCount(0);
    setPage(0);
    setListStatus('idle');
    if (nextObject.id !== objectId) syncUrl(nextObject);
  }, [monitorObject?.id, objectId, objects, syncUrl]);

  useEffect(() => {
    if (!monitorObject) {
      setMetricUnits(new Map());
      return;
    }
    const currentId = ++metricUnitRequestId.current;
    metricUnitController.current?.abort();
    const controller = new AbortController();
    metricUnitController.current = controller;
    const names = displayFieldMetricNames(monitorObject);
    if (!names.length) {
      setMetricUnits(new Map());
      return;
    }
    void listDisplayFieldMetrics(monitorObject.id, names, controller.signal)
      .then((metrics) => {
        if (currentId !== metricUnitRequestId.current || controller.signal.aborted) return;
        setMetricUnits(buildDisplayMetricUnitIndex(metrics));
      })
      .catch(() => {
        if (currentId !== metricUnitRequestId.current || controller.signal.aborted) return;
        setMetricUnits(new Map());
      });
  }, [monitorObject]);

  useEffect(() => {
    if (!monitorObject) return;
    const requestKey = `${monitorObject.id}:${keyword}:${statusFilterKey}`;
    if (lastRequestedKey.current === requestKey) return;
    lastRequestedKey.current = requestKey;
    const preserveContent = snapshotRefreshPending.current;
    snapshotRefreshPending.current = false;
    void loadInstances(monitorObject, 1, false, preserveContent).catch(() => undefined);
  }, [keyword, loadInstances, monitorObject, statusFilterKey]);

  const submitSearch = (value: string) => {
    const next = value.trim();
    setInput(value);
    setKeyword(next);
  };

  const clearSearch = () => {
    setInput('');
    setKeyword('');
  };

  const openStatusFilter = () => {
    setStatusDraft(statusFilters);
    setStatusFilterOpen(true);
  };

  const toggleStatusDraft = (status: MonitorReportingStatusFilter) => {
    setStatusDraft((current) => (
      current.includes(status)
        ? current.filter((item) => item !== status)
        : [...current, status]
    ));
  };

  const applyStatusFilter = () => {
    setStatusFilters(normalizeReportingStatusFilters(statusDraft));
    setStatusFilterOpen(false);
  };

  const resetStatusFilter = () => {
    setStatusDraft([]);
  };

  useEffect(() => () => {
    objectRequestId.current += 1;
    listRequestId.current += 1;
    metricUnitRequestId.current += 1;
    objectController.current?.abort();
    listController.current?.abort();
    metricUnitController.current?.abort();
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
      statusFilters,
      instances,
      count,
      page,
    }, scrollTop);
  }, [cacheScope, count, instances, keyword, listStatus, monitorObject, objectStatus, objects, page, statusFilters]);

  useEffect(() => {
    saveSnapshot();
  }, [saveSnapshot]);

  useEffect(() => {
    restoreMobileViewScroll(scrollRef.current, initialSnapshot.current?.scrollTop);
  }, []);

  const hasMore = listStatus === 'ready' && instances.length < count;
  const summaryFields = monitorObject?.displayFields || [];
  // 移动端先给出状态判断，再给时间证据：名称 → 上报状态 → 上报时间 → 全部 display_fields。
  // 名称列必须封顶，不能用 1fr——行宽 min-width:100% 时 1fr 会吃掉剩余空间，看起来怎么改都一样大。
  const tableGridColumns = [
    '164px',
    '88px',
    '96px',
    ...summaryFields.map(() => 'minmax(68px, 84px)'),
  ].join(' ');
  const hasStatusFilter = statusFilters.length > 0;
  const emptyTitle = keyword || hasStatusFilter
    ? t('monitor.noSearchResults')
    : t('monitor.noInstances');

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
              value={input}
              onChange={setInput}
              onSearch={submitSearch}
              onClear={clearSearch}
              placeholder={t('monitor.searchInstances')}
              aria-label={t('monitor.searchInstances')}
            />
          </div>
        </div>
      )}
      <div
        className={styles.scroll}
        ref={scrollRef}
        onScroll={(event) => saveSnapshot(event.currentTarget.scrollTop)}
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
              ) : (
                <div className={styles.instanceTableScroll} data-instance-table-scroll>
                  <div className={styles.instanceTable}>
                    <div className={styles.instanceTableHead} style={{ gridTemplateColumns: tableGridColumns }}>
                      <span className={styles.colSticky}>{t('monitor.columnName')}</span>
                      <button
                        type="button"
                        className={`${styles.columnFilter} ${hasStatusFilter ? styles.columnFilterActive : ''}`}
                        aria-label={t('monitor.filterReportingStatus')}
                        aria-expanded={statusFilterOpen}
                        onClick={openStatusFilter}
                      >
                        <span className={styles.columnFilterLabel}>{t('monitor.columnReportingStatus')}</span>
                        <FilterOutline className={styles.columnFilterIcon} aria-hidden />
                      </button>
                      <span className={styles.colRight}>{t('monitor.columnReportTime')}</span>
                      {summaryFields.map((field) => (
                        <span className={styles.colRight} key={field.key || field.name}>{field.name}</span>
                      ))}
                    </div>
                    {instances.length === 0 ? (
                      <div className={styles.instanceTableEmpty} role="status">
                        <MobileResult kind="empty" compact title={emptyTitle} />
                      </div>
                    ) : (
                      instances.map((instance) => {
                      const summary = instanceListSummaryEntries(monitorObject, instance, undefined, metricUnits);
                      const reportingStatus = resolveMonitorReportingStatus(instance.status);
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
                      });
                      return (
                        <Link
                          className={styles.instanceRow}
                          href={`/monitor/detail?${detailParams.toString()}`}
                          key={instance.id}
                          style={{ gridTemplateColumns: tableGridColumns }}
                        >
                          <span
                            className={`${styles.instanceIdentity} ${styles.colSticky}`}
                          >
                            <MonitorObjectIcon
                              className={styles.instanceIcon}
                              icon={monitorObject.icon}
                              size={26}
                            />
                            <span className={styles.instanceCopy}>
                              <span className={styles.instanceName}>
                                {instance.name}
                              </span>
                            </span>
                          </span>
                          <span className={styles.statusCell}>
                            {reportingStatus ? (
                              <span
                                className={styles.statusTag}
                                data-status={reportingStatus}
                              >
                                {t(
                                  `monitor.reportingStatus.${reportingStatus}`,
                                )}
                              </span>
                            ) : (
                              <span className={styles.colRight}>--</span>
                            )}
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
                            <span
                              className={styles.colRight}
                              key={field.key || field.name}
                            >
                              {summary[index]?.value ?? '--'}
                            </span>
                          ))}
                        </Link>
                      );
                    })
                    )}
                  </div>
                  {shouldShowListPagination(count, instances.length, MONITOR_PAGE_SIZE)
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
        visible={statusFilterOpen}
        onMaskClick={() => setStatusFilterOpen(false)}
        bodyStyle={{
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          overflow: 'hidden',
        }}
      >
        <div className={styles.statusFilterSheet}>
          <div className={styles.pickerHeader}>
            <strong className={styles.pickerTitle}>{t('monitor.filterReportingStatus')}</strong>
            <button
              type="button"
              className={styles.pickerClose}
              onClick={() => setStatusFilterOpen(false)}
            >
              {t('common.cancel')}
            </button>
          </div>
          <div className={styles.statusFilterOptions} role="group" aria-label={t('monitor.filterReportingStatus')}>
            {REPORTING_STATUS_OPTIONS.map((status) => {
              const checked = statusDraft.includes(status);
              return (
                <button
                  type="button"
                  key={status}
                  className={`${styles.statusFilterOption} ${checked ? styles.statusFilterOptionActive : ''}`}
                  aria-pressed={checked}
                  onClick={() => toggleStatusDraft(status)}
                >
                  <span>{t(`monitor.reportingStatus.${status}`)}</span>
                  {checked ? <CheckOutline className={styles.statusFilterCheck} aria-hidden /> : null}
                </button>
              );
            })}
          </div>
          <div className={styles.statusFilterActions}>
            <button type="button" className={styles.statusFilterReset} onClick={resetStatusFilter}>
              {t('monitor.resetFilter')}
            </button>
            <button type="button" className={styles.statusFilterConfirm} onClick={applyStatusFilter}>
              {t('common.confirm')}
            </button>
          </div>
        </div>
      </Popup>

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
                        <span className={styles.pickerRowName}>
                          {t('monitor.objectCountLabel', undefined, {
                            name: object.displayName,
                            count: object.instanceCount,
                          })}
                        </span>
                      </span>
                      {active ? (
                        <span className={styles.pickerRowAction}>{t('monitor.currentObject')}</span>
                      ) : null}
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
