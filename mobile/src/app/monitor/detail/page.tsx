'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Popup } from 'antd-mobile';
import { DownOutline } from 'antd-mobile-icons';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MetricCard from '@/features/monitor/metric-card';
import MetricChartSheet from '@/features/monitor/metric-chart-sheet';
import { getMonitorInstance, listEffectivePlugins, listMetricDefinition } from '@/features/monitor/adapter';
import { recordRecentView } from '@/features/monitor/recent-views-storage';
import { monitorRequestErrorKind, resolveMonitorReportingStatus, type MetricGroup, type MonitorMetric, type MonitorPlugin } from '@/features/monitor/model';
import MonitorObjectIcon from '@/features/monitor/object-icon-image';
import { useAuth } from '@/context/auth';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/monitor/monitor.module.css';

const RANGES = [15, 60, 360, 1440, 10080] as const;

type RangeMinutes = (typeof RANGES)[number];

function initialExpandedGroupIds(groups: MetricGroup[], metricItems: MonitorMetric[]) {
  const ids = groups
    .filter((group) => metricItems.some((metric) => metric.groupId === group.id))
    .map((group) => group.id);
  if (metricItems.some((metric) => !groups.some((group) => group.id === metric.groupId))) {
    ids.push(0);
  }
  if (ids.length <= 3) return new Set(ids);
  return new Set(ids.slice(0, 1));
}

function DetailMetricsSkeleton({ label }: { label: string }) {
  return (
    <div className={styles.detailMetricsLoading} role="status" aria-busy="true" aria-label={label}>
      <span className={styles.detailMetricsLoadingLabel}>{label}</span>
      <div className={styles.toolCard} aria-hidden="true">
        <div className={styles.detailRangeSkeleton}>
          {Array.from({ length: 5 }, (_, index) => (
            <span className={styles.detailSkeletonBlock} key={index} />
          ))}
        </div>
      </div>
      <div className={styles.metricStack} aria-hidden="true">
        <section className={styles.groupCard}>
          <div className={`${styles.detailSkeletonBlock} ${styles.detailGroupHeadSkeleton}`} />
          <div className={styles.metricGrid}>
            {Array.from({ length: 4 }, (_, index) => (
              <div className={`${styles.detailSkeletonBlock} ${styles.detailMetricCardSkeleton}`} key={index} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function MonitorDetailContent() {
  const { t } = useTranslation();
  const { userInfo, currentTeamId } = useAuth();
  const params = useSearchParams();
  const objectId = Number(params.get('objectId'));
  const objectName = params.get('objectName') || '--';
  const objectIcon = params.get('objectIcon') || '';
  const instanceId = params.get('instanceId') || '';
  const routeInstanceName = params.get('instanceName') || instanceId;
  const routeStatus = params.get('status') || '';
  const routeLastReportedAt = Number(params.get('lastReportedAt')) || null;
  const routeInterval = Number(params.get('interval')) || null;
  const idValues = useMemo(() => {
    try {
      const parsed: unknown = JSON.parse(params.get('idValues') || '[]');
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }, [params]);
  const [instanceName, setInstanceName] = useState(routeInstanceName);
  const [instanceStatus, setInstanceStatus] = useState(routeStatus);
  const [lastReportedAt, setLastReportedAt] = useState<number | null>(routeLastReportedAt);
  const [interval, setIntervalSeconds] = useState<number | null>(routeInterval);
  const [plugins, setPlugins] = useState<MonitorPlugin[]>([]);
  const [pluginId, setPluginId] = useState<number | null>(null);
  const [groups, setGroups] = useState<MetricGroup[]>([]);
  const [metrics, setMetrics] = useState<MonitorMetric[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'unavailable'>('loading');
  const [instanceResolved, setInstanceResolved] = useState(false);
  const [range, setRange] = useState<RangeMinutes>(15);
  const [reloadToken, setReloadToken] = useState(0);
  const [pluginPickerOpen, setPluginPickerOpen] = useState(false);
  const [metricSheetIndex, setMetricSheetIndex] = useState<number | null>(null);
  const recordedRef = useRef(false);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };
  const selectedPlugin = useMemo(
    () => plugins.find((plugin) => plugin.id === pluginId) || null,
    [pluginId, plugins],
  );
  const showPluginPicker = plugins.length >= 2 && Boolean(selectedPlugin);

  useEffect(() => {
    setInstanceName(routeInstanceName);
    setInstanceStatus(routeStatus);
    setLastReportedAt(routeLastReportedAt);
    setIntervalSeconds(routeInterval);
  }, [routeInstanceName, routeInterval, routeLastReportedAt, routeStatus]);

  useEffect(() => {
    if (!objectId || !instanceId) {
      setStatus('error');
      return;
    }
    const controller = new AbortController();
    setStatus('loading');
    setInstanceResolved(false);
    setPluginId(null);
    setPlugins([]);
    setGroups([]);
    setMetrics([]);
    setExpandedGroups(new Set());

    Promise.all([
      getMonitorInstance(
        objectId,
        instanceId,
        {},
        controller.signal,
      ),
      listEffectivePlugins(objectId, instanceId, controller.signal),
    ])
      .then(([instance, items]) => {
        if (controller.signal.aborted) return;
        // Server 没有单实例读取接口：列表命中或能解析出有效插件都能证明实例存在。
        if (!instance && items.length === 0) {
          setStatus('unavailable');
          return;
        }
        if (instance) {
          setInstanceName(instance.name || routeInstanceName);
          setInstanceStatus(instance.status || '');
          setLastReportedAt(instance.lastReportedAt);
          setIntervalSeconds(instance.interval);
        }
        setInstanceResolved(true);
        setPlugins(items);
        setPluginId(items[0]?.id || null);
        if (!items.length) setStatus('ready');
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setStatus(monitorRequestErrorKind(error) === 'error' ? 'error' : 'unavailable');
      });
    return () => controller.abort();
  }, [idValues, instanceId, objectId, reloadToken, routeInstanceName]);

  useEffect(() => {
    if (!pluginId) return;
    const controller = new AbortController();
    setStatus('loading');
    listMetricDefinition(objectId, pluginId, controller.signal)
      .then((result) => {
        setGroups(result.groups);
        setMetrics(result.metrics);
        setExpandedGroups(initialExpandedGroupIds(result.groups, result.metrics));
        setStatus('ready');
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setStatus(monitorRequestErrorKind(error) === 'error' ? 'error' : 'unavailable');
      });
    return () => controller.abort();
  }, [objectId, pluginId]);

  useEffect(() => {
    setMetricSheetIndex(null);
  }, [pluginId, range]);

  useEffect(() => {
    recordedRef.current = false;
  }, [instanceId, objectId]);

  // Reuse Auth userInfo already on this page — wait until id is known; do not fetch again or fall back to 0.
  useEffect(() => {
    if (!objectId || !instanceId || status !== 'ready' || !instanceResolved || !userInfo?.id || recordedRef.current) return;
    recordedRef.current = true;
    recordRecentView(userInfo.id, currentTeamId || 'none', objectId, instanceId);
  }, [currentTeamId, instanceId, instanceResolved, objectId, status, userInfo?.id]);

  const grouped = groups
    .map((group) => ({ group, metrics: metrics.filter((metric) => metric.groupId === group.id) }))
    .filter((item) => item.metrics.length);
  const orphanMetrics = metrics.filter((metric) => !groups.some((group) => group.id === metric.groupId));
  if (orphanMetrics.length) {
    grouped.push({
      group: { id: 0, name: 'other', displayName: t('monitor.otherMetrics'), order: Number.MAX_SAFE_INTEGER },
      metrics: orphanMetrics,
    });
  }
  const sheetMetrics = grouped.flatMap((item) => item.metrics);

  const returnTab = params.get('returnTab') || '';
  const backParams = new URLSearchParams({ objectId: String(objectId), objectName });
  const backHref = returnTab === 'recent'
    ? '/monitor'
    : objectId ? `/monitor?${backParams.toString()}` : '/monitor';
  const reportedLabel = lastReportedAt
    ? formatAccountDateTime(new Date(lastReportedAt * 1000).toISOString(), preferences)
    : '--';
  const reportingStatus = resolveMonitorReportingStatus(instanceStatus);
  const reportingStatusLabel = reportingStatus
    ? t(`monitor.reportingStatus.${reportingStatus}`)
    : '--';
  const displayId = idValues.length
    ? idValues.join(' · ')
    : instanceId.replace(/^\(\s*'?|"?/, '').replace(/'?\s*,?\s*\)$/, '').replace(/^'|'$/g, '') || instanceId;

  const toggleGroup = (groupId: number) => {
    setExpandedGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  return (
    <main className={styles.page}>
      <MobilePageHeader title={t('monitor.detailTitle')} backHref={backHref} />
      <div className={`${styles.scroll} ${styles.detailScroll}`}>
        {status !== 'unavailable' ? <section className={styles.heroCard}>
          <div className={styles.heroHead}>
            <MonitorObjectIcon className={styles.heroIcon} icon={objectIcon} size={36} />
            <div className={styles.heroCopy}>
              <h1 className={styles.heroTitle}>{instanceName}</h1>
              <div className={styles.heroIdentity}>
                <span className={styles.heroObjectText}>{objectName}</span>
                {reportingStatus ? (
                  <span className={styles.statusTag} data-status={reportingStatus}>
                    {reportingStatusLabel}
                  </span>
                ) : (
                  <span className={styles.heroObjectText}>--</span>
                )}
              </div>
            </div>
          </div>
          <div className={styles.heroFacts} aria-label={t('monitor.detailTitle')}>
            <div className={styles.heroFactItem}>
              <span className={styles.heroFactLabel}>{t('monitor.fields.reportedAt')}</span>
              <span className={styles.heroFactValue}>{reportedLabel}</span>
            </div>
            <div className={styles.heroFactItem}>
              <span className={styles.heroFactLabel}>{t('monitor.fields.interval')}</span>
              <span className={styles.heroFactValue}>
                {interval ? t('monitor.fields.intervalSeconds', undefined, { count: interval }) : '--'}
              </span>
            </div>
            <div className={styles.heroFactItem}>
              <span className={styles.heroFactLabel}>{t('monitor.instanceId')}</span>
              <span className={styles.heroFactValueMono} title={displayId}>{displayId}</span>
            </div>
          </div>
        </section> : null}

        <div className={styles.detailBody}>
          {status === 'loading' ? (
            <DetailMetricsSkeleton label={t('common.loading')} />
          ) : status !== 'ready' ? (
            <MobileResult
              kind={status === 'error' ? 'error' : 'permission'}
              title={status === 'unavailable' ? t('monitor.detailUnavailable') : t('monitor.detailLoadFailed')}
              description={status === 'error' ? t('monitor.retryHint') : ''}
              actionLabel={status === 'error' ? t('common.retry') : undefined}
              onAction={status === 'error' ? () => setReloadToken((value) => value + 1) : undefined}
              action={status !== 'error' ? <Link className={styles.retry} href="/monitor">{t('monitor.backToMonitor')}</Link> : undefined}
            />
          ) : plugins.length === 0 || metrics.length === 0 ? (
            <MobileResult kind="empty" title={t('monitor.noMetricsConfigured')} description={t('monitor.noMetricsConfiguredHint')} />
          ) : (
            <>
              <div className={styles.toolCard}>
                <div className={styles.rangeSeg} role="group" aria-label={t('monitor.timeRange')}>
                  {RANGES.map((minutes) => (
                    <button
                      type="button"
                      className={`${styles.rangeSegBtn} ${minutes === range ? styles.rangeSegBtnActive : ''}`}
                      aria-pressed={minutes === range}
                      onClick={() => setRange(minutes)}
                      key={minutes}
                    >
                      {t(`monitor.ranges.${minutes}`, `${minutes}m`)}
                    </button>
                  ))}
                </div>
                {showPluginPicker && selectedPlugin ? (
                  <button
                    type="button"
                    className={styles.pluginSwitch}
                    aria-expanded={pluginPickerOpen}
                    aria-haspopup="dialog"
                    aria-label={t('monitor.selectPluginTitle')}
                    onClick={() => setPluginPickerOpen(true)}
                  >
                    <span className={styles.pluginDot} data-status={selectedPlugin.status || undefined} aria-hidden="true" />
                    <span className={styles.pluginSwitchName}>{selectedPlugin.displayName}</span>
                    {selectedPlugin.status ? (
                      <span className={styles.pluginSwitchStatus}>
                        {t(`monitor.pluginStatus.${selectedPlugin.status}`, selectedPlugin.status)}
                      </span>
                    ) : null}
                    <DownOutline className={styles.pluginSwitchChevron} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
              <div className={styles.metricStack}>
                {grouped.map(({ group, metrics: items }) => {
                  const open = expandedGroups.has(group.id);
                  return (
                    <section className={styles.groupCard} key={group.id}>
                      <button
                        type="button"
                        className={styles.groupToggle}
                        aria-expanded={open}
                        onClick={() => toggleGroup(group.id)}
                      >
                        <span className={styles.groupToggleTitle}>{group.displayName}</span>
                        <span className={styles.groupCount}>
                          {t('monitor.groupCount', undefined, { count: items.length })}
                        </span>
                        <span className={styles.groupChevron} aria-hidden="true">{open ? '▾' : '▸'}</span>
                      </button>
                      {open ? (
                        <div className={styles.metricGrid}>
                          {items.map((metric) => {
                            const sheetIndex = sheetMetrics.findIndex((item) => item.id === metric.id);
                            return (
                              <MetricCard
                                key={`${metric.id}-${pluginId}-${range}`}
                                metric={metric}
                                monitorObjectId={objectId}
                                instanceId={instanceId}
                                rangeMinutes={range}
                                interval={interval}
                                onOpen={sheetIndex >= 0 ? () => setMetricSheetIndex(sheetIndex) : undefined}
                              />
                            );
                          })}
                        </div>
                      ) : null}
                    </section>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>

      <Popup
        visible={pluginPickerOpen}
        onMaskClick={() => setPluginPickerOpen(false)}
        bodyStyle={{
          height: '56vh',
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div className={styles.picker}>
          <div className={styles.pickerHeader}>
            <strong className={styles.pickerTitle}>{t('monitor.selectPluginTitle')}</strong>
            <button
              type="button"
              className={styles.pickerClose}
              onClick={() => setPluginPickerOpen(false)}
            >
              {t('common.cancel')}
            </button>
          </div>
          <div className={styles.pickerBody}>
            {plugins.map((plugin) => {
              const active = plugin.id === pluginId;
              return (
                <button
                  type="button"
                  key={plugin.id}
                  className={`${styles.pickerRow} ${active ? styles.pickerRowActive : ''}`}
                  onClick={() => {
                    setPluginId(plugin.id);
                    setPluginPickerOpen(false);
                  }}
                >
                  <span className={styles.pluginDot} data-status={plugin.status || undefined} aria-hidden="true" />
                  <span className={styles.pickerRowCopy}>
                    <span className={styles.pickerRowName}>{plugin.displayName}</span>
                    {plugin.status ? (
                      <span className={styles.pickerRowMeta}>
                        {t(`monitor.pluginStatus.${plugin.status}`, plugin.status)}
                      </span>
                    ) : null}
                  </span>
                  <span className={styles.pickerRowAction}>
                    {active ? t('monitor.currentPlugin') : t('monitor.selectPluginAction')}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </Popup>

      <MetricChartSheet
        open={metricSheetIndex != null}
        metrics={sheetMetrics}
        activeIndex={metricSheetIndex ?? 0}
        monitorObjectId={objectId}
        instanceId={instanceId}
        rangeMinutes={range}
        interval={interval}
        onClose={() => setMetricSheetIndex(null)}
        onActiveIndexChange={setMetricSheetIndex}
      />
    </main>
  );
}

export default function MonitorDetailPage() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<MobileSkeleton label={t('common.loading')} variant="detail" rows={4} />}>
      <MonitorDetailContent />
    </Suspense>
  );
}
