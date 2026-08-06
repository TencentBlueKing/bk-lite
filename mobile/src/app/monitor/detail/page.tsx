'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Popup } from 'antd-mobile';
import { DownOutline } from 'antd-mobile-icons';
import MobilePageHeader from '@/components/mobile-page-header';
import { MobileResult, MobileSkeleton } from '@/components/mobile-feedback';
import MetricCard from '@/features/monitor/metric-card';
import { getMonitorInstance, listEffectivePlugins, listMetricDefinition } from '@/features/monitor/adapter';
import { monitorRequestErrorKind, type MetricGroup, type MonitorMetric, type MonitorPlugin } from '@/features/monitor/model';
import MonitorObjectIcon from '@/features/monitor/object-icon-image';
import { useAuth } from '@/context/auth';
import { formatAccountDateTime } from '@/platform/preferences/dateTime';
import { useTranslation } from '@/utils/i18n';
import styles from '@/features/monitor/monitor.module.css';

const RANGES = [15, 60, 360, 1440, 10080];

type DetailTab = 'metrics' | 'about';

function parseFacts(raw: string | null): Array<{ label: string; value: string }> {
  try {
    const parsed: unknown = JSON.parse(raw || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => {
        const row = typeof item === 'object' && item !== null ? item as Record<string, unknown> : {};
        return { label: String(row.label || ''), value: String(row.value ?? '') };
      })
      .filter((item) => item.label && item.value);
  } catch {
    return [];
  }
}

function MonitorDetailContent() {
  const { t } = useTranslation();
  const { userInfo } = useAuth();
  const params = useSearchParams();
  const objectId = Number(params.get('objectId'));
  const objectName = params.get('objectName') || '--';
  const objectIcon = params.get('objectIcon') || '';
  const instanceId = params.get('instanceId') || '';
  const routeInstanceName = params.get('instanceName') || instanceId;
  const routeStatus = params.get('status') || '';
  const routeLastReportedAt = Number(params.get('lastReportedAt')) || null;
  const routeInterval = Number(params.get('interval')) || null;
  const routeFacts = useMemo(() => parseFacts(params.get('facts')), [params]);
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
  const [facts, setFacts] = useState(routeFacts);
  const [activeTab, setActiveTab] = useState<DetailTab>('metrics');
  const [plugins, setPlugins] = useState<MonitorPlugin[]>([]);
  const [pluginId, setPluginId] = useState<number | null>(null);
  const [groups, setGroups] = useState<MetricGroup[]>([]);
  const [metrics, setMetrics] = useState<MonitorMetric[]>([]);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'forbidden' | 'missing'>('loading');
  const [range, setRange] = useState(15);
  const [reloadToken, setReloadToken] = useState(0);
  const [pluginPickerOpen, setPluginPickerOpen] = useState(false);
  const preferences = { locale: userInfo?.locale || 'en', timezone: userInfo?.timezone || 'Asia/Shanghai' };
  const selectedPlugin = useMemo(
    () => plugins.find((plugin) => plugin.id === pluginId) || null,
    [pluginId, plugins],
  );
  const canSwitchPlugin = plugins.length > 1;

  useEffect(() => {
    setInstanceName(routeInstanceName);
    setInstanceStatus(routeStatus);
    setLastReportedAt(routeLastReportedAt);
    setIntervalSeconds(routeInterval);
    setFacts(routeFacts);
  }, [routeFacts, routeInstanceName, routeInterval, routeLastReportedAt, routeStatus]);

  useEffect(() => {
    if (!objectId || !instanceId) {
      setStatus('error');
      return;
    }
    const controller = new AbortController();
    setStatus('loading');
    setPluginId(null);
    setPlugins([]);
    setGroups([]);
    setMetrics([]);
    setExpandedGroups(new Set());

    const refreshHeader = getMonitorInstance(
      objectId,
      instanceId,
      { name: routeInstanceName, idValues },
      controller.signal,
    ).then((instance) => {
      if (!instance || controller.signal.aborted) return;
      setInstanceName(instance.name || routeInstanceName);
      setInstanceStatus(instance.status || '');
      setLastReportedAt(instance.lastReportedAt);
      setIntervalSeconds(instance.interval);
    }).catch(() => undefined);

    listEffectivePlugins(objectId, instanceId, controller.signal)
      .then(async (items) => {
        await refreshHeader;
        if (controller.signal.aborted) return;
        setPlugins(items);
        setPluginId(items[0]?.id || null);
        if (!items.length) setStatus('ready');
      })
      .catch((error) => {
        if (!controller.signal.aborted) setStatus(monitorRequestErrorKind(error));
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
        const firstGroup = result.groups.find((group) => result.metrics.some((metric) => metric.groupId === group.id));
        setExpandedGroups(new Set(firstGroup ? [firstGroup.id] : result.groups[0] ? [result.groups[0].id] : [0]));
        setStatus('ready');
      })
      .catch((error) => {
        if (!controller.signal.aborted) setStatus(monitorRequestErrorKind(error));
      });
    return () => controller.abort();
  }, [objectId, pluginId]);

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

  const backParams = new URLSearchParams({ objectId: String(objectId), objectName });
  const backHref = objectId ? `/monitor?${backParams.toString()}` : '/monitor';
  const reportedLabel = lastReportedAt
    ? formatAccountDateTime(new Date(lastReportedAt * 1000).toISOString(), preferences)
    : t('monitor.noReportTime');
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
      <div className={styles.scroll}>
        <section className={styles.hero}>
          <div className={styles.heroHead}>
            <MonitorObjectIcon className={styles.heroIcon} icon={objectIcon} size={28} />
            <div className={styles.heroCopy}>
              <h1 className={styles.heroTitle}>{instanceName}</h1>
              <div className={styles.heroMeta}>
                <span className={styles.heroObject}>{objectName}</span>
                <span className={styles.heroMetaSep} aria-hidden>·</span>
                <span className={styles.heroStatus} data-status={instanceStatus || undefined}>
                  {instanceStatus ? t(`monitor.status.${instanceStatus}`, instanceStatus) : '--'}
                </span>
                <span className={styles.heroMetaSep} aria-hidden>·</span>
                <span className={styles.heroMetaText}>{displayId}</span>
              </div>
              <div className={styles.heroMeta}>
                <span className={styles.heroMetaText}>{reportedLabel}</span>
                {interval ? (
                  <>
                    <span className={styles.heroMetaSep} aria-hidden>·</span>
                    <span className={styles.heroMetaText}>
                      {t('monitor.fields.interval')} {t('monitor.fields.intervalSeconds', undefined, { count: interval })}
                    </span>
                  </>
                ) : null}
              </div>
              {facts.length > 0 && (
                <div className={styles.heroFactsGrid}>
                  {facts.slice(0, 4).map((fact) => (
                    <span key={`${fact.label}-${fact.value}`}>{fact.label} · {fact.value}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        <div className={styles.detailTabs} role="tablist" aria-label={t('monitor.detailTitle')}>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'metrics'}
            className={`${styles.detailTab} ${activeTab === 'metrics' ? styles.detailTabActive : ''}`}
            onClick={() => setActiveTab('metrics')}
          >
            {t('monitor.detailTabs.metrics')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'about'}
            className={`${styles.detailTab} ${activeTab === 'about' ? styles.detailTabActive : ''}`}
            onClick={() => setActiveTab('about')}
          >
            {t('monitor.detailTabs.about')}
          </button>
        </div>

        {activeTab === 'about' ? (
          <section className={styles.aboutList}>
            {[
              [t('monitor.fields.object'), objectName],
              [t('monitor.fields.instance'), instanceName],
              [t('monitor.fields.status'), instanceStatus ? t(`monitor.status.${instanceStatus}`, instanceStatus) : '--'],
              [t('monitor.fields.reportedAt'), reportedLabel],
              [t('monitor.fields.interval'), interval ? t('monitor.fields.intervalSeconds', undefined, { count: interval }) : '--'],
              ...facts.map((fact) => [fact.label, fact.value] as const),
              [t('monitor.instanceId'), displayId],
            ].map(([label, value]) => (
              <div className={styles.aboutRow} key={`${label}-${value}`}>
                <span className={styles.aboutLabel}>{label}</span>
                <span className={styles.aboutValue}>{value}</span>
              </div>
            ))}
          </section>
        ) : (
          <>
            {plugins.length > 0 && selectedPlugin && (
              <div className={`${styles.controls} ${styles.controlsInline}`}>
                <span className={styles.controlLabel}>{t('monitor.dataSource')}</span>
                {canSwitchPlugin ? (
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
                ) : (
                  <div className={styles.pluginSwitch} data-static="true">
                    <span className={styles.pluginDot} data-status={selectedPlugin.status || undefined} aria-hidden="true" />
                    <span className={styles.pluginSwitchName}>{selectedPlugin.displayName}</span>
                    {selectedPlugin.status ? (
                      <span className={styles.pluginSwitchStatus}>
                        {t(`monitor.pluginStatus.${selectedPlugin.status}`, selectedPlugin.status)}
                      </span>
                    ) : null}
                  </div>
                )}
              </div>
            )}

            {status === 'loading' ? (
              <MobileSkeleton label={t('common.loading')} variant="metrics" rows={3} />
            ) : status !== 'ready' ? (
              <MobileResult
                kind={status === 'error' ? 'error' : 'permission'}
                title={status === 'forbidden' ? t('monitor.detailForbidden') : status === 'missing' ? t('monitor.detailMissing') : t('monitor.detailLoadFailed')}
                description={status === 'error' ? t('monitor.retryHint') : ''}
                actionLabel={status === 'error' ? t('common.retry') : undefined}
                onAction={status === 'error' ? () => setReloadToken((value) => value + 1) : undefined}
                action={status !== 'error' ? <Link className={styles.retry} href="/monitor">{t('monitor.backToMonitor')}</Link> : undefined}
              />
            ) : plugins.length === 0 || metrics.length === 0 ? (
              <MobileResult kind="empty" title={t('monitor.noMetricsConfigured')} description={t('monitor.noMetricsConfiguredHint')} />
            ) : (
              <div className={styles.metricPanel}>
                <div className={styles.metricToolbar} role="group" aria-label={t('monitor.timeRange')}>
                  <span className={styles.metricToolbarLabel}>{t('monitor.timeRange')}</span>
                  <div className={styles.pills}>
                    {RANGES.map((minutes) => (
                      <button
                        type="button"
                        className={`${styles.pill} ${minutes === range ? styles.pillActive : ''}`}
                        aria-pressed={minutes === range}
                        onClick={() => setRange(minutes)}
                        key={minutes}
                      >
                        {t(`monitor.ranges.${minutes}`, `${minutes}m`)}
                      </button>
                    ))}
                  </div>
                </div>
                {grouped.map(({ group, metrics: items }) => {
                  const open = expandedGroups.has(group.id);
                  return (
                    <section className={styles.metricGroup} key={group.id}>
                      <button
                        type="button"
                        className={styles.groupToggle}
                        aria-expanded={open}
                        onClick={() => toggleGroup(group.id)}
                      >
                        <span className={styles.groupToggleTitle}>
                          {group.displayName}
                          {' '}
                          {open ? '▾' : '▸'}
                        </span>
                        <span className={styles.groupToggleMeta}>
                          {open
                            ? t('monitor.collapseGroup')
                            : `${t('monitor.groupCount', undefined, { count: items.length })} · ${t('monitor.expandGroup')}`}
                        </span>
                      </button>
                      {open && (
                        <div className={styles.metricGrid}>
                          {items.map((metric) => (
                            <MetricCard key={`${metric.id}-${pluginId}-${range}`} metric={metric} idValues={idValues} rangeMinutes={range} interval={interval} />
                          ))}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </>
        )}
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
