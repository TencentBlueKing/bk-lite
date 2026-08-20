'use client';

import { useEffect, useMemo, useState } from 'react';
import { CheckOutlined, FireOutlined } from '@ant-design/icons';
import {
  Button,
  Descriptions,
  Drawer,
  Popconfirm,
  Space,
  Tabs,
  Tag,
  Typography,
  theme,
} from 'antd';
import Link from 'next/link';
import dayjs from 'dayjs';
import CatalogState, { type CatalogStateKind } from '@/app/apm/components/catalog-state';
import {
  formatClockTime,
  formatDateTime,
  formatLatency,
  formatMonthDay,
  formatPercentage,
  formatRequestRate,
  type Translate,
} from '@/app/apm/components/metric-format';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { ALERT_LEVEL_COLORS, OBSERVABILITY_SERIES_COLORS } from '@/constants/observabilityChart';
import { useTranslation } from '@/utils/i18n';
import type {
  ApmAlert,
  ApmAlertEvent,
  ApmAlertMetricSnapshot,
  ApmEventSnapshot,
  ApmNotificationDelivery,
  ApmPolicyComparator,
  ApmPolicyMetric,
  ApmPolicySeverity,
} from '@/app/apm/types';
import styles from '@/app/apm/events/event-workspace.module.scss';

const ACTION_KEY = { triggered: 'apm.alerts.trigger', escalated: 'apm.alerts.escalated', recovered: 'apm.alerts.recover', closed: 'apm.alerts.manuallyClosed' } as const;
const STATUS_KEY = { active: 'apm.status.firing', recovered: 'apm.status.recovered', closed: 'apm.alerts.statusClosed' } as const;
const SEVERITY_KEY: Record<ApmPolicySeverity, string> = { critical: 'apm.severity.critical', error: 'apm.severity.error', warning: 'apm.severity.warning' };
const METRIC_KEY: Record<ApmPolicyMetric, string> = {
  error_rate: 'apm.common.errorRate',
  p95: 'apm.common.p95Latency',
  p99: 'apm.common.p99Latency',
  throughput: 'apm.common.throughput',
  no_traffic: 'apm.alerts.noTraffic',
};
const METRIC_UNIT_KEY: Record<ApmPolicyMetric, string | null> = {
  error_rate: 'apm.common.percentUnit',
  p95: 'apm.common.millisecondUnit',
  p99: 'apm.common.millisecondUnit',
  throughput: 'apm.common.requestsPerSecondUnit',
  no_traffic: null,
};
const COMPARATOR_SYMBOL: Record<ApmPolicyComparator, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
};

function formatMetricDisplayValue(
  metric: ApmPolicyMetric,
  value: string | number | null | undefined,
  unit?: string,
  noDataLabel = '—',
  t?: Translate,
): string {
  if (value == null || value === '') return noDataLabel;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (metric === 'error_rate') {
    const percent = unit === 'ratio' || Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
    return formatPercentage(percent, percent >= 10 ? 1 : 2);
  }
  if (metric === 'p95' || metric === 'p99') {
    return formatLatency(numeric, false, t);
  }
  if (metric === 'throughput') {
    return formatRequestRate(numeric, false, t);
  }
  return String(numeric);
}

function toChartMetricNumber(
  metric: ApmPolicyMetric,
  value: string | number | null | undefined,
  unit?: string,
): number | null {
  if (value == null || value === '') return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (metric === 'error_rate' && (unit === 'ratio' || Math.abs(numeric) <= 1)) {
    return Number((numeric * 100).toFixed(4));
  }
  return numeric;
}

function formatChartAxisValue(metric: ApmPolicyMetric, value: number, t: Translate): string {
  if (metric === 'error_rate') return formatPercentage(value, value >= 10 ? 1 : 2);
  if (metric === 'p95' || metric === 'p99') {
    return formatLatency(value, false, t);
  }
  if (metric === 'throughput') {
    return formatRequestRate(value, false, t);
  }
  return String(value);
}

function snapshotElapsedLabel(elapsedMinutes: number, triggerLabel: string, t: Translate): string {
  return elapsedMinutes === 0
    ? triggerLabel
    : t('apm.alerts.minutesAfterTrigger', '+{count} 分钟', { count: elapsedMinutes });
}

interface SnapshotChartRow {
  [key: string]: unknown;
  timestamp: string;
  elapsedMinutes: number;
  value: number | null;
  threshold: number | null;
  event: number | null;
}

function buildAlertSnapshotChartRows(
  alert: ApmAlert,
  snapshot: ApmAlertMetricSnapshot | null,
): SnapshotChartRow[] {
  const items = [...(snapshot?.snapshots ?? [])]
    .sort((left, right) => dayjs(left.snapshot_time).valueOf() - dayjs(right.snapshot_time).valueOf());
  if (!items.length) return [];
  const intervalMin = Math.max(1, snapshot?.evaluation_interval ?? 1);
  const origin = dayjs(alert.started_at);
  const lastTime = dayjs(items[items.length - 1].snapshot_time);
  const lastSlot = Math.max(1, Math.round(lastTime.diff(origin, 'minute') / intervalMin));
  const bySlot = new Map<number, (typeof items)[number]>();
  items.forEach((item) => {
    const slot = Math.max(0, Math.round(dayjs(item.snapshot_time).diff(origin, 'minute') / intervalMin));
    bySlot.set(slot, item);
  });
  let lastThreshold: number | null = null;
  return Array.from({ length: lastSlot + 1 }, (_, slot) => {
    const item = bySlot.get(slot);
    const value = item
      ? toChartMetricNumber(alert.metric_type, item.value, snapshot?.unit)
      : null;
    const threshold = item
      ? toChartMetricNumber(alert.metric_type, item.threshold?.value, snapshot?.unit)
      : lastThreshold;
    if (threshold != null) lastThreshold = threshold;
    return {
      timestamp: origin.add(slot * intervalMin, 'minute').toISOString(),
      elapsedMinutes: slot * intervalMin,
      value,
      threshold,
      event: item?.type === 'event' ? value : null,
    };
  });
}

function resolveThreshold(alert: ApmAlert, snapshot: ApmAlertMetricSnapshot | null, t: Translate): {
  comparator: string;
  display: string;
} {
  const item = [...(snapshot?.snapshots ?? [])].reverse().find((row) => row.threshold != null)
    ?? snapshot?.snapshots.find((row) => row.threshold != null);
  const comparator = item?.threshold?.comparator ?? 'gt';
  const raw = item?.threshold?.value ?? alert.current_value;
  return {
    comparator: COMPARATOR_SYMBOL[comparator] ?? String(comparator),
    display: formatMetricDisplayValue(alert.metric_type, raw, snapshot?.unit, '—', t),
  };
}

const STATE_TAG_CLASS: Record<ApmAlert['status'], string> = {
  active: styles.alertDetailStateTagActive,
  recovered: styles.alertDetailStateTagRecovered,
  closed: styles.alertDetailStateTagClosed,
};
const METRIC_TAG_CLASS: Record<ApmPolicyMetric, string> = {
  error_rate: styles.alertDetailMetricTagError,
  p95: styles.alertDetailMetricTagLatency,
  p99: styles.alertDetailMetricTagLatency,
  throughput: styles.alertDetailMetricTagThroughput,
  no_traffic: styles.alertDetailMetricTagIdle,
};

function AlertStateTag({ status }: { status: ApmAlert['status'] }) {
  const { t } = useTranslation();
  return (
    <span className={`${styles.alertDetailStateTag} ${STATE_TAG_CLASS[status]}`}>
      {t(STATUS_KEY[status])}
    </span>
  );
}

function AlertLevelTag({ severity }: { severity: ApmPolicySeverity }) {
  const { t } = useTranslation();
  return (
    <Tag className={styles.alertDetailLevelTag} color={ALERT_LEVEL_COLORS[severity]}>
      {t(SEVERITY_KEY[severity])}
    </Tag>
  );
}

function AlertMetricTag({ metric }: { metric: ApmPolicyMetric }) {
  const { t } = useTranslation();
  return (
    <span className={`${styles.alertDetailMetricTag} ${METRIC_TAG_CLASS[metric]}`}>
      {t(METRIC_KEY[metric])}
    </span>
  );
}

const DELIVERY_STATUS_KEY = { pending: 'apm.alerts.deliveryPending', delivered: 'apm.alerts.deliveryDelivered', failed: 'apm.alerts.deliveryFailed' } as const;

function readTraceContext(context: Record<string, unknown> | undefined, key: string) {
  const value = context?.[key];
  return typeof value === 'string' && value.trim() ? value : '';
}

function buildTraceSearchHref(context: Record<string, unknown> | undefined) {
  const serviceName = readTraceContext(context, 'service_name');
  const startedAt = readTraceContext(context, 'started_at');
  const endedAt = readTraceContext(context, 'ended_at');
  if (!serviceName || !startedAt || !endedAt) return null;
  const params = new URLSearchParams({
    service_name: serviceName,
    started_at: startedAt,
    ended_at: endedAt,
  });
  const namespace = readTraceContext(context, 'service_namespace');
  const environment = readTraceContext(context, 'environment');
  const endpoint = readTraceContext(context, 'endpoint');
  if (namespace) params.set('service_namespace', namespace);
  if (environment) params.set('environment', environment);
  if (endpoint) params.set('span_name', endpoint);
  return `/apm/explore/traces?${params.toString()}`;
}

type HeatLevel = 'none' | 'low' | 'mid' | 'high' | 'burst';
const HEAT_LEVELS: Array<{ level: HeatLevel; i18nKey: string }> = [
  { level: 'none', i18nKey: 'apm.alerts.heatNone' },
  { level: 'low', i18nKey: 'apm.alerts.heatLow' },
  { level: 'mid', i18nKey: 'apm.alerts.heatMid' },
  { level: 'high', i18nKey: 'apm.alerts.heatHigh' },
  { level: 'burst', i18nKey: 'apm.alerts.heatBurst' },
];

function resolveHeatLevel(count: number): HeatLevel {
  if (count === 0) return 'none';
  if (count <= 3) return 'low';
  if (count <= 7) return 'mid';
  if (count <= 15) return 'high';
  return 'burst';
}

function buildSevenDayHeatmap(timestamps: string[], endAt: string) {
  const end = dayjs(endAt).startOf('day');
  const days = Array.from({ length: 7 }, (_, index) => end.subtract(6 - index, 'day'));
  const matrix = days.map(() => Array.from({ length: 24 }, () => 0));
  timestamps.forEach((stamp) => {
    const point = dayjs(stamp);
    const dayIndex = days.findIndex((day) => point.isSame(day, 'day'));
    if (dayIndex >= 0) {
      matrix[dayIndex][point.hour()] += 1;
    }
  });
  return { days, matrix };
}

function EventDistributionHeatmap({
  timestamps,
  endAt,
  onCellClick,
}: {
  timestamps: string[];
  endAt: string;
  onCellClick: (start: string, end: string) => void;
}) {
  const { t } = useTranslation();
  const { days, matrix } = useMemo(
    () => buildSevenDayHeatmap(timestamps, endAt),
    [endAt, timestamps],
  );
  const today = dayjs(endAt).startOf('day');
  const heatColors: Record<HeatLevel, string> = {
    none: 'var(--color-fill-2)',
    low: 'color-mix(in srgb, var(--color-primary) 18%, var(--color-bg))',
    mid: 'color-mix(in srgb, var(--color-primary) 40%, var(--color-bg))',
    high: 'var(--color-primary)',
    burst: 'var(--color-fail)',
  };

  return (
    <div>
      <div className={styles.alertDetailEventCardHead}>
        <Typography.Text className={styles.alertDetailEventCardTitle}>
          {t('apm.alerts.heatmapTitle', '事件分布 · 近 7 天 × 24h')}
        </Typography.Text>
        <div className={styles.alertDetailHeatLegend} aria-label={t('apm.alerts.heatmapLegend', '事件密度图例')}>
          <Typography.Text type="secondary" className={styles.alertDetailChartHint}>{t('apm.alerts.density', '密度：')}</Typography.Text>
          {HEAT_LEVELS.map((item) => (
            <span key={item.level} className={styles.alertDetailHeatLegendItem}>
              <span
                className={styles.alertDetailHeatSwatch}
                style={{ background: heatColors[item.level] }}
              />
              <Typography.Text type="secondary" className={styles.alertDetailHeatLegendLabel}>
                {t(item.i18nKey)}
              </Typography.Text>
            </span>
          ))}
        </div>
      </div>
      <div className={styles.alertDetailHeatScroll}>
        <div className={styles.alertDetailHeatGrid} role="img" aria-label={t('apm.alerts.heatmapAria', '事件分布，近 7 天按小时聚合')}>
          <div className={styles.alertDetailHeatHours}>
            <span />
            {Array.from({ length: 24 }, (_, hour) => (
              <span key={hour} className={hour % 3 === 0 ? styles.alertDetailHeatHourActive : undefined}>
                {hour}
              </span>
            ))}
          </div>
          {days.map((day, dayIndex) => {
            const isToday = day.isSame(today, 'day');
            return (
              <div key={day.valueOf()} className={styles.alertDetailHeatRow}>
                <span className={isToday ? styles.alertDetailHeatDayToday : styles.alertDetailHeatDay}>
                  {`${formatMonthDay(day.toDate())}${isToday ? ` (${t('apm.alerts.today', '今')})` : ''}`}
                </span>
                {matrix[dayIndex].map((count, hour) => {
                  const level = resolveHeatLevel(count);
                  const start = day.hour(hour).minute(0).second(0);
                  return (
                    <button
                      key={`${dayIndex}-${hour}`}
                      type="button"
                      title={t('apm.alerts.heatmapCell', '{time} · {count} 条', { time: formatDateTime(start.toISOString(), false), count })}
                      className={`${styles.alertDetailHeatCell} ${level === 'burst' ? styles.alertDetailHeatPeak : ''}`}
                      style={{ background: heatColors[level] }}
                      onClick={() => onCellClick(start.toISOString(), start.add(1, 'hour').toISOString())}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
      <div className={styles.alertDetailHeatFoot}>
        <FireOutlined className={styles.alertDetailHeatFootIcon} />
        {t('apm.alerts.heatmapBurstHint', '红框为爆发时段(≥16 条)')}
      </div>
    </div>
  );
}

interface AlertDetailDrawerProps {
  open: boolean;
  alert: ApmAlert | null;
  metricSnapshot: ApmAlertMetricSnapshot | null;
  metricSnapshotLoading: boolean;
  metricSnapshotError: CatalogStateKind | null;
  selectedEvent: ApmAlertEvent | null;
  eventEvidence: ApmEventSnapshot | null;
  eventEvidenceLoading: boolean;
  deliveries: ApmNotificationDelivery[];
  retryingDeliveryId: string | null;
  onClose: () => void;
  onCloseAlert: (alert: ApmAlert) => void;
  onRetrySnapshot: (alert: ApmAlert) => void;
  onSelectEvent: (alert: ApmAlert, event: ApmAlertEvent) => void;
  onRetryDelivery: (deliveryId: string) => void;
}

export default function AlertDetailDrawer({
  open,
  alert,
  metricSnapshot,
  metricSnapshotLoading,
  metricSnapshotError,
  selectedEvent,
  eventEvidence,
  deliveries,
  retryingDeliveryId,
  onClose,
  onCloseAlert,
  onRetrySnapshot,
  onSelectEvent,
  onRetryDelivery,
}: AlertDetailDrawerProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [tab, setTab] = useState<'alert' | 'event'>('alert');
  const [hourFilter, setHourFilter] = useState<{ start: string; end: string } | null>(null);

  useEffect(() => {
    setTab('alert');
    setHourFilter(null);
  }, [alert?.id]);

  const notifiers = useMemo(() => {
    const names = deliveries.flatMap((item) => item.recipients).filter(Boolean);
    return Array.from(new Set(names));
  }, [deliveries]);
  const notificationStatus = (alert?.notification_status || 'none') as NonNullable<ApmAlert['notification_status']>;
  const threshold = alert ? resolveThreshold(alert, metricSnapshot, t) : null;
  const serviceLabel = alert ? `${alert.service_namespace}/${alert.service_name}` : '';
  const lifecycleEvents = useMemo(
    () => [...(alert?.events ?? [])].sort(
      (left, right) => dayjs(right.occurred_at).valueOf() - dayjs(left.occurred_at).valueOf(),
    ),
    [alert?.events],
  );
  const metricSnapshotRows = useMemo(
    () => (alert ? buildAlertSnapshotChartRows(alert, metricSnapshot) : []),
    [alert, metricSnapshot],
  );
  const eventStreamRows = useMemo(() => {
    if (!alert) return [];
    const windowStart = dayjs(alert.started_at).valueOf();
    const windowEnd = dayjs(alert.ended_at || alert.last_event_at || alert.started_at).valueOf();
    const unit = metricSnapshot?.unit;
    const rows = (metricSnapshot?.snapshots ?? []).map((item, index) => {
      const occurred = dayjs(item.snapshot_time).valueOf();
      return {
        id: `${item.snapshot_time}-${item.type}-${item.event_id ?? index}`,
        occurredAt: item.snapshot_time,
        content: alert.endpoint || t('apm.alerts.allEndpoints', '全部端点'),
        value: formatMetricDisplayValue(alert.metric_type, item.value, unit, t('apm.common.noData', '无数据'), t),
        inAlertWindow: occurred >= windowStart && occurred <= windowEnd,
        danger: item.type === 'event' || item.type === 'no_data',
        eventId: item.event_id,
      };
    });
    lifecycleEvents.forEach((item) => {
      if (item.action !== 'closed') return;
      if (rows.some((row) => row.eventId === item.event_id)) return;
      rows.push({
        id: item.id,
        occurredAt: item.occurred_at,
        content: t(ACTION_KEY[item.action]),
        value: formatMetricDisplayValue(alert.metric_type, item.value, unit, t('apm.common.noData', '无数据'), t),
        inAlertWindow: true,
        danger: false,
        eventId: item.event_id,
      });
    });
    return rows.sort((left, right) => dayjs(right.occurredAt).valueOf() - dayjs(left.occurredAt).valueOf());
  }, [alert, lifecycleEvents, metricSnapshot, t]);
  const visibleStreamRows = useMemo(() => {
    if (!hourFilter) return eventStreamRows;
    const start = new Date(hourFilter.start).getTime();
    const end = new Date(hourFilter.end).getTime();
    return eventStreamRows.filter((row) => {
      const occurred = new Date(row.occurredAt).getTime();
      return occurred >= start && occurred < end;
    });
  }, [eventStreamRows, hourFilter]);
  const heatTimestamps = useMemo(
    () => eventStreamRows.map((item) => item.occurredAt),
    [eventStreamRows],
  );
  const heatEndAt = eventStreamRows[0]?.occurredAt || alert?.last_event_at || alert?.started_at || '';
  const traceSearchHref = eventEvidence && eventEvidence.payload_status !== 'expired'
    ? buildTraceSearchHref(eventEvidence.trace_context)
    : null;
  const alertWindowLabel = alert
    ? `${formatClockTime(alert.started_at)} ~ ${formatClockTime(alert.ended_at || alert.last_event_at || alert.started_at)}`
    : '';

  const handleHeatMapClick = (start: string, end: string) => {
    if (!alert) return;
    setHourFilter({ start, end });
    const startMs = new Date(start).getTime();
    const endMs = new Date(end).getTime();
    const target = lifecycleEvents.find((item) => {
      const occurred = new Date(item.occurred_at).getTime();
      return occurred >= startMs && occurred < endMs;
    });
    if (target) onSelectEvent(alert, target);
  };

  const handleStreamRowClick = (eventId: string | null) => {
    if (!alert || !eventId) return;
    const target = lifecycleEvents.find((item) => item.event_id === eventId);
    if (target) onSelectEvent(alert, target);
  };

  return (
    <Drawer
      width={880}
      open={open}
      onClose={onClose}
      className={styles.alertDetailDrawer}
      classNames={{ body: styles.alertDetailDrawerBody, footer: styles.alertDetailDrawerFooter }}
      title={alert ? (
        <div className={styles.alertDetailTitle}>
          <AlertStateTag status={alert.status} />
          <AlertLevelTag severity={alert.severity} />
          <AlertMetricTag metric={alert.metric_type} />
          <span className={styles.alertDetailTitleText}>{alert.title}</span>
        </div>
      ) : null}
      footer={(
        <Button onClick={onClose}>{t('common.cancel', '取消')}</Button>
      )}
    >
      {alert ? (
        <>
          <div className={styles.alertDetailMeta}>
            <span>
              {t('apm.alerts.ownerService', '所属服务')}{' '}
              {alert.service_id ? (
                <Link className={styles.alertDetailMetaLink} href={`/apm/services/${alert.service_id}`}>
                  {serviceLabel}
                </Link>
              ) : (
                <Typography.Text className={styles.alertDetailMetaText}>{serviceLabel}</Typography.Text>
              )}
            </span>
            {alert.endpoint ? (
              <span>
                {t('apm.alerts.ownerEndpoint', '所属端点')}{' '}
                <Typography.Text className={styles.alertDetailMetaText}>{alert.endpoint}</Typography.Text>
              </span>
            ) : null}
            {alert.version ? (
              <span>
                {t('apm.alerts.ownerVersion', '所属版本')} <Typography.Text className={styles.alertDetailMetaText}>{alert.version}</Typography.Text>
              </span>
            ) : null}
            {alert.environment ? (
              <span>
                {t('apm.common.environment', '环境')} <Typography.Text className={styles.alertDetailMetaText}>{alert.environment}</Typography.Text>
              </span>
            ) : null}
            <span>
              {t('apm.alerts.relatedPolicy', '关联规则')}{' '}
              <Link className={styles.alertDetailRule} href={`/apm/events/policies/${alert.policy_id}`}>
                {alert.policy_name}
              </Link>
            </span>
            <span>
              {t('apm.alerts.triggeredAt', '触发时间')}{' '}
              <Typography.Text className={styles.alertDetailMetaText}>
                {formatDateTime(alert.started_at)}
              </Typography.Text>
            </span>
          </div>

          <Tabs
            className={styles.alertDetailTabs}
            activeKey={tab}
            onChange={(key) => setTab(key as 'alert' | 'event')}
            items={[
              { key: 'alert', label: t('apm.alerts.alertTab', '告警') },
              { key: 'event', label: t('apm.alerts.eventTab', '事件') },
            ]}
          />

          <div className={styles.alertDetailBody}>
            {tab === 'alert' ? (
              <div>
                <Descriptions
                  className={styles.alertDetailInfo}
                  title={t('apm.alerts.info', '告警信息')}
                  column={2}
                  bordered
                  size="small"
                >
                  <Descriptions.Item label={t('apm.common.time', '时间')}>
                    {formatDateTime(alert.last_event_at || alert.started_at)}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.level', '级别')}>
                    <div
                      className={styles.alertDetailLevel}
                      style={{ borderLeftColor: ALERT_LEVEL_COLORS[alert.severity], color: ALERT_LEVEL_COLORS[alert.severity] }}
                    >
                      {t(SEVERITY_KEY[alert.severity])}
                    </div>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.firstAlertAt', '首次告警时间')}>
                    {formatDateTime(alert.started_at)}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.ownerVersion', '所属版本')}>
                    {alert.version || '--'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.object', '所属对象')}>
                    <Space size={4} direction="vertical" className={styles.alertDetailObject}>
                      {alert.service_id ? (
                        <Link className={styles.alertDetailMetaLink} href={`/apm/services/${alert.service_id}`}>
                          {alert.service_name}
                        </Link>
                      ) : (
                        <span>{alert.service_name}</span>
                      )}
                      {alert.endpoint ? (
                        <Typography.Text type="secondary" className={styles.alertDetailObjectScope}>
                          {alert.endpoint}
                        </Typography.Text>
                      ) : null}
                    </Space>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.relatedPolicy', '关联规则')}>
                    <span className={styles.alertDetailRule}>
                      <Link href={`/apm/events/policies/${alert.policy_id}`}>
                        {alert.policy_name}
                      </Link>
                    </span>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.metric', '度量')}>
                    <Space size={4} align="center">
                      <AlertMetricTag metric={alert.metric_type} />
                      <Typography.Text type="secondary" className={styles.alertDetailObjectScope}>
                        {t(alert.endpoint ? 'apm.alerts.groupByEndpoint' : alert.version ? 'apm.alerts.groupByVersion' : 'apm.alerts.groupAggregate')}
                      </Typography.Text>
                    </Space>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.policies.threshold', '阈值')}>
                    <span className={styles.alertDetailTabular}>
                      {threshold ? `${threshold.comparator} ${threshold.display}` : '--'}
                    </span>
                  </Descriptions.Item>
                  {alert.status !== 'active' ? (
                    <Descriptions.Item label={t('apm.alerts.endTime', '告警结束时间')}>
                      {alert.ended_at ? formatDateTime(alert.ended_at) : '--'}
                    </Descriptions.Item>
                  ) : null}
                  <Descriptions.Item label={t('apm.alerts.notification', '通知')}>
                    {notificationStatus === 'none' ? (
                      <Typography.Text type="secondary">{t('apm.alerts.notificationNone', '未通知')}</Typography.Text>
                    ) : (
                      <Tag
                        className={styles.alertDetailNotifyTag}
                        color={notificationStatus === 'delivered' ? 'success' : notificationStatus === 'failed' ? 'error' : 'warning'}
                        icon={notificationStatus === 'delivered' ? <CheckOutlined /> : undefined}
                      >
                        {t(`apm.alerts.notification${notificationStatus[0].toUpperCase()}${notificationStatus.slice(1)}`)}
                      </Tag>
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.operator', '操作人')}>
                    {alert.operator || '--'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('apm.alerts.notifiedPeople', '通知人')} span={alert.status === 'active' ? 2 : 1}>
                    {notifiers.length ? notifiers.join(', ') : '--'}
                  </Descriptions.Item>
                </Descriptions>

                <div className={styles.alertDetailCloseRow}>
                  <Popconfirm
                    title={t('apm.alerts.manualCloseConfirm', '人工关闭会追加 closed 事件和不可变快照，确认继续？')}
                    disabled={alert.status !== 'active'}
                    onConfirm={() => onCloseAlert(alert)}
                  >
                    <Button type="primary" danger disabled={alert.status !== 'active'}>
                      {t('apm.alerts.closeAlert', '关闭告警')}
                    </Button>
                  </Popconfirm>
                </div>

                <div className={styles.alertDetailChartCard}>
                  <Typography.Title level={5} className={styles.alertDetailChartTitle}>
                    {t('apm.alerts.metricSnapshot', '告警指标快照')}
                    <Typography.Text type="secondary" className={styles.alertDetailChartHint}>
                      {t('apm.alerts.eachPolicyScan', '每点一次策略扫描')}
                      {metricSnapshot ? ` · ${t('apm.alerts.scanInterval', '检测频率 {minutes}m', { minutes: metricSnapshot.evaluation_interval })}` : ''}
                      {METRIC_UNIT_KEY[alert.metric_type]
                        ? ` · ${t(METRIC_KEY[alert.metric_type])}(${t(METRIC_UNIT_KEY[alert.metric_type])})`
                        : ` · ${t(METRIC_KEY[alert.metric_type])}`}
                    </Typography.Text>
                  </Typography.Title>
                  {metricSnapshotLoading ? (
                    <CatalogState kind="loading" />
                  ) : metricSnapshotError ? (
                    <CatalogState kind={metricSnapshotError} onRetry={() => onRetrySnapshot(alert)} />
                  ) : metricSnapshotRows.length ? (
                    <div
                      className={styles.alertDetailChart}
                      role="img"
                      aria-label={t('apm.alerts.metricSnapshotAria', '告警指标快照，按策略扫描绘制评估值与当时阈值')}
                    >
                      <TimeSeriesComposedChart
                        data={metricSnapshotRows}
                        xDataKey="timestamp"
                        getXLabel={(item) => snapshotElapsedLabel(item.elapsedMinutes, t('apm.alerts.trigger', '触发'), t)}
                        xAxisBoundaryGap={false}
                        yAxes={[{ formatter: (value) => formatChartAxisValue(alert.metric_type, value, t) }]}
                        series={[
                          {
                            name: t('apm.alerts.evaluationValue', '评估值'),
                            type: 'line',
                            dataKey: 'value',
                            color: OBSERVABILITY_SERIES_COLORS[0],
                            showArea: true,
                            areaOpacity: 0.24,
                            smooth: false,
                            showSymbol: true,
                            lineWidth: 1.5,
                          },
                          {
                            name: t('apm.alerts.thresholdAtTime', '当时阈值'),
                            type: 'line',
                            dataKey: 'threshold',
                            color: ALERT_LEVEL_COLORS[alert.severity],
                            lineType: 'dashed',
                            lineWidth: 1.5,
                          },
                          {
                            name: t('apm.alerts.lifecycleEvent', '生命周期事件'),
                            type: 'line',
                            dataKey: 'event',
                            color: token.colorWarning,
                            showSymbol: true,
                            lineWidth: 0,
                          },
                        ]}
                      />
                    </div>
                  ) : (
                    <CatalogState kind="empty" description={t('apm.alerts.noMetricSnapshot', '暂无告警指标快照')} />
                  )}
                </div>
              </div>
            ) : (
              <div>
                <div className={styles.alertDetailEventCard}>
                  <EventDistributionHeatmap
                    timestamps={heatTimestamps}
                    endAt={heatEndAt}
                    onCellClick={handleHeatMapClick}
                  />
                </div>

                <div className={styles.alertDetailEventCard}>
                  <div className={styles.alertDetailEventCardHead}>
                    <Typography.Text className={styles.alertDetailEventCardTitle}>
                      {t('apm.alerts.eventStreamTitle', '事件流(按时间倒序 · 共 {count} 条)', { count: eventStreamRows.length })}
                    </Typography.Text>
                    <Typography.Text type="secondary" className={styles.alertDetailChartHint}>
                      {alert.service_name}
                      {alert.endpoint ? ` · ${alert.endpoint}` : ''}
                      {traceSearchHref ? (
                        <>
                          {' · '}
                          <Link className={styles.alertDetailRule} href={traceSearchHref}>
                            {t('apm.alerts.viewTraceAtTime', '查看当时调用链')}
                          </Link>
                        </>
                      ) : null}
                    </Typography.Text>
                  </div>
                  {metricSnapshotLoading ? (
                    <CatalogState kind="loading" />
                  ) : visibleStreamRows.length ? (
                    <div className={styles.alertDetailEventList} role="list" aria-label={t('apm.alerts.eventStreamAria', '事件流时间线')}>
                      {visibleStreamRows.map((item) => {
                        const selected = Boolean(item.eventId && item.eventId === selectedEvent?.event_id);
                        return (
                          <button
                            key={item.id}
                            type="button"
                            role="listitem"
                            className={`${styles.alertDetailEventRow} ${selected ? styles.alertDetailEventRowSelected : ''} ${item.inAlertWindow ? styles.alertDetailEventRowActive : ''}`}
                            aria-label={`${item.content} ${formatClockTime(item.occurredAt)}`}
                            onClick={() => handleStreamRowClick(item.eventId)}
                          >
                            <span className={styles.alertDetailEventTime}>
                              {formatClockTime(item.occurredAt)}
                            </span>
                            <span className={styles.alertDetailEventContent}>{item.content}</span>
                            <span
                              className={`${styles.alertDetailEventValue} ${item.danger ? styles.alertDetailEventValueDanger : item.inAlertWindow ? styles.alertDetailEventValueWarn : ''}`}
                            >
                              {item.value}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <CatalogState kind="empty" description={t(hourFilter ? 'apm.alerts.noEventsInPeriod' : 'apm.alerts.noEvents', hourFilter ? '该时段暂无事件' : '暂无事件')} />
                  )}
                  {eventStreamRows.length ? (
                    <Typography.Text type="secondary" className={`${styles.alertDetailChartHint} mt-2 block`}>
                      {t('apm.alerts.alertWindowHint', '红底高亮 = 告警触发时段({window})', { window: alertWindowLabel })}
                    </Typography.Text>
                  ) : null}
                </div>

                {deliveries.length ? (
                  <div className={styles.alertDetailEventCard}>
                    <div className={styles.alertDetailEventCardHead}>
                      <Typography.Text className={styles.alertDetailEventCardTitle}>{t('apm.alerts.delivery', '通知投递')}</Typography.Text>
                    </div>
                    <div className="flex flex-col border border-[var(--color-border-1)] rounded-md" role="list" aria-label={t('apm.alerts.deliveryRecords', '通知投递记录')}>
                      {deliveries.map((delivery) => (
                        <div
                          key={delivery.id}
                          className="flex items-center gap-3 px-3 py-2 border-b border-[var(--color-border-1)] last:border-b-0"
                          role="listitem"
                        >
                          <span className="min-w-0 flex-1 truncate">{delivery.channel_name || t('apm.alerts.unnamedChannel', '未命名渠道')}</span>
                          <Tag color={delivery.status === 'delivered' ? 'success' : delivery.status === 'failed' ? 'error' : 'warning'}>
                            {t(DELIVERY_STATUS_KEY[delivery.status])}
                          </Tag>
                          {delivery.status === 'failed' ? (
                            <Button
                              type="link"
                              size="small"
                              loading={retryingDeliveryId === delivery.id}
                              onClick={() => onRetryDelivery(delivery.id)}
                            >
                              {t('apm.alerts.retryDelivery', '重投')}
                            </Button>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </>
      ) : null}
    </Drawer>
  );
}
