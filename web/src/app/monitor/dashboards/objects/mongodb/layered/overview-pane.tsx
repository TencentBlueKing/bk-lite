'use client';

import React, { useMemo } from 'react';
import {
  EVENT_RAIL_HINT_LINES,
  KpiTileRow,
  ProDashLoading,
  ProFocusCard,
  ProInfoHint,
  ProSection,
  ThinTimeSeries,
  proChromeClass,
  type KpiTileModel
} from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, formatFocusHeadline, seriesSampleValues } from '../../host/layered/focus-axis';
import { mongoFocusJump, mongoKpiJump, type MongoTab } from './ia';
import { MONGODB_PALETTE } from './metrics';
import { MongoHint } from './hint';
import {
  formatMongoPercent,
  formatMongoReading,
  mongoLatest,
  mongoMerged,
  mongoRatioPercent,
  mongoRatioPoints,
  type MongoMetricMap
} from './series';

const EMPTY = '—';

interface OverviewPaneProps {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  booting: boolean;
  alertCount: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onOpenAlerts: () => void;
  onOpenTarget: (tab: MongoTab, anchor: string) => void;
  onFocusAlert: (alertId: string) => void;
}

const KPI_SPECS = [
  {
    key: 'connections',
    label: '当前连接数',
    metric: 'mongodb_connections_current',
    unit: 'counts' as const,
    color: MONGODB_PALETTE.blue,
    body: '此刻连到本实例的客户端连接数。'
  },
  {
    key: 'queries',
    label: '查询吞吐',
    metric: 'mongodb_queries_rate',
    unit: 'cps' as const,
    color: MONGODB_PALETTE.cyan,
    body: '每秒完成的查询操作数，反映读侧繁忙程度。'
  },
  {
    key: 'latency',
    label: '命令延迟',
    metric: 'mongodb_latency_commands_avg',
    unit: 'ms' as const,
    color: MONGODB_PALETTE.violet,
    body: '命令从发起到完成的平均耗时。升高通常意味着负载或资源压力加大。'
  },
  {
    key: 'cache',
    label: '缓存使用率',
    metric: 'mongodb_wtcache_usage_ratio',
    unit: 'percent' as const,
    color: MONGODB_PALETTE.blue,
    body: 'WiredTiger 缓存已用容量占总上限的比例。接近上限时工作集更易挤出内存。\n已用 ÷ 上限 × 100%\n分母为 0 时显示 —，不用 0% 顶替。'
  }
] as const;

const FOCUS_SPECS = [
  {
    key: 'queued-writes',
    label: '排队写操作',
    unit: 'counts' as const,
    unitLabel: '个',
    color: MONGODB_PALETTE.orange,
    cta: '查看活跃与排队',
    body: '等待执行的写操作数量。持续抬升说明写路径开始堆积。'
  },
  {
    key: 'docs-scanned',
    label: '文档扫描频率',
    unit: 'cps' as const,
    unitLabel: '次/秒',
    color: MONGODB_PALETTE.cyan,
    cta: '',
    body: '每秒扫描的文档数。偏高常见于缺索引或查询条件过宽。'
  },
  {
    key: 'page-faults',
    label: '缺页频率',
    unit: 'cps' as const,
    unitLabel: '次/秒',
    color: MONGODB_PALETTE.red,
    cta: '',
    body: '每秒缺页次数。升高通常意味着工作集未能很好落在内存中。'
  },
  {
    key: 'dirty',
    label: '脏数据占比',
    unit: 'percent' as const,
    unitLabel: '%',
    color: MONGODB_PALETTE.orange,
    cta: '查看脏数据趋势',
    body: 'WiredTiger 缓存中尚未落盘的脏数据所占比例。\n脏数据 ÷ 当前缓存 × 100%\n分母为 0 时显示 —，不用 0% 顶替。'
  }
] as const;

const ALERT_KPI_KEY = 'alerts';
const ALERT_KPI_LABEL = '告警数量';

/** 活跃告警数。0 仍显示 0；还没取到数时用 --。 */
export const mongoAlertKpiValue = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return '--';
  return String(Math.max(0, Math.round(count)));
};

export const mongoAlertKpiTone = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return undefined;
  return count > 0 ? 'var(--color-fail)' : 'var(--color-success)';
};

const HEALTH_PENDING = [
  'mongodb_connections_current',
  'mongodb_queries_rate',
  'mongodb_latency_commands_avg',
  'mongodb_wtcache_current_bytes',
  'mongodb_wtcache_max_bytes_configured'
];

const focusQuiet = (latest: number | null, samples: readonly number[]) => (
  latest === 0 && samples.every((value) => value === 0)
);

export default function OverviewPane({
  metricMap,
  pendingMetricNames,
  booting,
  alertCount,
  alertsOpen,
  alertEvents,
  eventsLoading,
  onOpenAlerts,
  onOpenTarget,
  onFocusAlert
}: OverviewPaneProps) {
  const cachePercent = mongoRatioPercent(
    metricMap,
    'mongodb_wtcache_current_bytes',
    'mongodb_wtcache_max_bytes_configured'
  );
  const dirtyPercent = mongoRatioPercent(
    metricMap,
    'mongodb_wtcache_tracked_dirty_bytes',
    'mongodb_wtcache_current_bytes'
  );
  const healthLoading = booting || HEALTH_PENDING.some((name) => pendingMetricNames.has(name));
  const cards = useMemo<KpiTileModel[]>(() => {
    const metricCards: KpiTileModel[] = KPI_SPECS.map((item) => {
      const info = <MongoHint kind={`mongo-kpi-${item.key}`} title={item.label} body={item.body} />;
      const jump = mongoKpiJump(item.key);
      const activate = jump
        ? { onActivate: () => onOpenTarget(jump.tab, jump.anchor), activatesDialog: false as const }
        : {};
      if (item.key === 'cache') {
        return {
          key: item.key,
          label: item.label,
          value: formatMongoPercent(cachePercent),
          tone: cachePercent == null ? undefined : item.color,
          info,
          ...activate
        };
      }
      const latest = mongoLatest(metricMap, item.metric);
      return {
        key: item.key,
        label: item.label,
        value: formatMongoReading(latest, item.unit),
        tone: latest == null ? undefined : item.color,
        info,
        ...activate
      };
    });
    metricCards.push({
      key: ALERT_KPI_KEY,
      label: ALERT_KPI_LABEL,
      value: mongoAlertKpiValue(alertCount),
      tone: mongoAlertKpiTone(alertCount),
      onActivate: onOpenAlerts,
      expanded: alertsOpen
    });
    return metricCards;
  }, [alertCount, alertsOpen, cachePercent, metricMap, onOpenAlerts, onOpenTarget]);

  const loadingTiles: KpiTileModel[] = [
    ...KPI_SPECS.map((item) => ({ key: item.key, label: item.label, value: '' })),
    { key: ALERT_KPI_KEY, label: ALERT_KPI_LABEL, value: '' }
  ];

  return (
    <div data-mongodb-pane="overview" className="contents">
      <ProSection title="健康概览">
        <KpiTileRow
          items={healthLoading ? loadingTiles : cards}
          loading={healthLoading}
          columns={5}
        />
      </ProSection>
      <ProSection
        title="事件"
        hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}
      >
        <EventsRail events={alertEvents} loading={eventsLoading} onFocusAlert={onFocusAlert} />
      </ProSection>
      <ProSection title="重点关注">
        <div className={proChromeClass.shortcutGrid} data-mongodb-focus="grid">
          {FOCUS_SPECS.map((card) => {
            const percent = card.key === 'dirty';
            const plotted = percent
              ? mongoRatioPoints(
                metricMap,
                'mongodb_wtcache_tracked_dirty_bytes',
                'mongodb_wtcache_current_bytes'
              )
              : card.key === 'queued-writes'
                ? mongoMerged(metricMap, [
                  { name: 'mongodb_queued_writes', label: '排队写' },
                  { name: 'mongodb_active_writes', label: '活跃写' }
                ])
                : mongoMerged(metricMap, [{
                  name: card.key === 'docs-scanned'
                    ? 'mongodb_total_docs_scanned_rate'
                    : 'mongodb_page_faults_rate',
                  label: card.label
                }]);
            const latest = percent
              ? dirtyPercent
              : card.key === 'queued-writes'
                ? mongoLatest(metricMap, 'mongodb_queued_writes')
                : card.key === 'docs-scanned'
                  ? mongoLatest(metricMap, 'mongodb_total_docs_scanned_rate')
                  : mongoLatest(metricMap, 'mongodb_page_faults_rate');
            const samples = seriesSampleValues(plotted);
            const quiet = focusQuiet(latest, samples);
            const pendingNames = percent
              ? ['mongodb_wtcache_tracked_dirty_bytes', 'mongodb_wtcache_current_bytes']
              : card.key === 'queued-writes'
                ? ['mongodb_queued_writes', 'mongodb_active_writes']
                : [card.key === 'docs-scanned' ? 'mongodb_total_docs_scanned_rate' : 'mongodb_page_faults_rate'];
            const loading = pendingNames.some((name) => pendingMetricNames.has(name))
              && plotted.length === 0
              && latest == null;
            const axis = describeFocusAxis(card.unit, samples);
            const jump = mongoFocusJump(card.key);
            const headline = latest == null ? EMPTY : formatFocusHeadline(axis, latest);
            return (
              <ProFocusCard key={card.key}>
                <div
                  className={proChromeClass.shortcutCopy}
                  data-mongodb-focus={card.key}
                  data-mongodb-focus-weight={quiet ? 'quiet' : 'normal'}
                >
                  <FocusShortcutTitle
                    label={card.label}
                    unit={card.unitLabel}
                    hint={<MongoHint kind={`mongo-focus-${card.key}`} title={card.label} body={card.body} />}
                  />
                  {loading ? <ProDashLoading size="small" /> : (
                    <div
                      className={proChromeClass.shortcutValue}
                      style={latest == null ? undefined : {
                        color: percent ? 'var(--color-text-1)' : card.color,
                        ...(quiet ? { fontSize: 15, fontWeight: 500 } : {})
                      }}
                    >
                      {headline}
                    </div>
                  )}
                  {jump && card.cta ? (
                    <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpenTarget(jump.tab, jump.anchor)}>
                      {card.cta}
                    </button>
                  ) : null}
                </div>
                {plotted.length > 0 ? (
                  <ThinTimeSeries
                    bare
                    numericAxis={card.unit !== 'counts'}
                    pinAxisZero
                    valueBounds={percent ? { min: 0, max: 100 } : undefined}
                    className={proChromeClass.focusChart}
                    title=""
                    unit={card.unit}
                    data={plotted}
                    legends={card.key === 'queued-writes'
                      ? [
                        { label: '排队写', color: MONGODB_PALETTE.orange },
                        { label: '活跃写', color: MONGODB_PALETTE.green }
                      ]
                      : [{ label: card.label, color: card.color }]}
                  />
                ) : (
                  <div className={proChromeClass.focusChart} />
                )}
              </ProFocusCard>
            );
          })}
        </div>
      </ProSection>
    </div>
  );
}
