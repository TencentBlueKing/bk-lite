'use client';

import React, { useMemo } from 'react';
import type { MetricUnit } from '../../../shared/types';
import { formatMetricValue } from '../../../shared/utils/format';
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
import { PG_PALETTE } from '../config';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { formatCacheHitPercent } from './cache-hit';
import { postgresKpiJump } from './ia';
import { PostgresHint } from './hint';
import {
  cacheHitReading,
  formatEventCount,
  postgresLatest,
  postgresMerged,
  postgresWindowCount,
  type PostgresMetricMap
} from './series';

const EMPTY = '—';

const joinMetric = (value: number, unit: MetricUnit) => {
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

interface OverviewPaneProps {
  metricMap: PostgresMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  booting: boolean;
  alertCount: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
  onOpenAlerts: () => void;
  onOpenFocus: (anchor: string) => void;
  onFocusAlert: (alertId: string) => void;
}

const KPI_SPECS = [
  {
    key: 'connections',
    label: '连接',
    metric: 'postgresql_numbackends',
    unit: 'counts' as const,
    color: PG_PALETTE.blue,
    body: '当前连接到本库的会话数。'
  },
  {
    key: 'commit',
    label: '提交速率',
    metric: 'postgresql_xact_commit_rate',
    unit: 'cps' as const,
    color: PG_PALETTE.emerald,
    body: '每秒成功提交的事务数，反映写入/事务繁忙程度。'
  },
  {
    key: 'cache',
    label: '缓存命中率',
    metric: 'postgresql_cache_hit_ratio',
    unit: 'percent' as const,
    color: PG_PALETTE.emerald,
    body: '共享缓冲区命中占总读取的比例。偏低说明热点数据未驻留内存、读盘偏多。\n命中 ÷（命中 + 未命中）× 100%\n分母为 0 时显示 —，不用 0% 顶替。'
  },
  {
    key: 'deadlock',
    label: '死锁次数',
    metric: 'postgresql_deadlocks_count',
    unit: 'counts' as const,
    color: PG_PALETTE.rose,
    body: '当前时间范围内发生的死锁次数。\n偶发需要关注冲突事务；持续出现时应排查锁顺序与长事务。\n暂无数据时显示 —。'
  }
] as const;

const FOCUS_SPECS = [
  {
    key: 'blks-read',
    label: '磁盘块读取速率',
    metric: 'postgresql_blks_read_rate',
    color: PG_PALETTE.orange,
    anchor: 'cache-disk',
    cta: '查看缓存与磁盘',
    body: '每秒从磁盘读入的块次数。升高通常伴随缓存未命中增多；与概览「缓存命中率」互补，不是同一指标。'
  },
  {
    key: 'temp-files',
    label: '临时文件创建速率',
    metric: 'postgresql_temp_files_rate',
    color: PG_PALETTE.amber,
    anchor: 'anomaly',
    cta: '查看异常与临时',
    body: '查询溢出 work_mem 写临时文件的速率。'
  },
  {
    key: 'rollback',
    label: '事务回滚速率',
    metric: 'postgresql_xact_rollback_rate',
    color: PG_PALETTE.rose,
    anchor: 'transactions',
    cta: '查看事务与数据操作',
    body: '每秒回滚事务数。持续升高需查失败或冲突；异于概览「提交速率」。'
  },
  {
    key: 'checkpoint-req',
    label: '请求检查点速率',
    metric: 'postgresql_checkpoints_req_rate',
    color: PG_PALETTE.orange,
    anchor: 'checkpoint',
    cta: '查看检查点与缓冲区',
    body: '因 WAL 或缓冲压力请求触发的检查点速率；偏高暗示检查点配置或写压。'
  }
] as const;

/** 死锁次数：0 用中性色，大于 0 才用告警色。 */
export const postgresDeadlockTone = (latest: number | null, alertColor: string) => (
  latest != null && latest > 0 ? alertColor : undefined
);

const ALERT_KPI_KEY = 'alerts';
const ALERT_KPI_LABEL = '告警数量';

/** 活跃告警数。0 仍显示 0；未知或失败用 --，不拿空串把卡藏掉。 */
export const postgresAlertKpiValue = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return '--';
  return String(Math.max(0, Math.round(count)));
};

/** 0 成功色，大于 0 失败色。还没有数时不涂色。 */
export const postgresAlertKpiTone = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return undefined;
  return count > 0 ? 'var(--color-fail)' : 'var(--color-success)';
};

/** 窗口全是 0（或没有非 0 采样）时弱化焦点大数，折线仍保留。 */
export const postgresFocusQuiet = (latest: number | null, samples: readonly number[]) => (
  latest === 0 && samples.every((value) => value === 0)
);

const HEALTH_PENDING = [
  'postgresql_numbackends',
  'postgresql_xact_commit_rate',
  'postgresql_cache_hit_ratio',
  'postgresql_blks_hit_rate',
  'postgresql_blks_read_rate',
  'postgresql_deadlocks_count'
];

export default function OverviewPane({
  metricMap,
  pendingMetricNames,
  booting,
  alertCount,
  alertsOpen,
  alertEvents,
  eventsLoading,
  onOpenAlerts,
  onOpenFocus,
  onFocusAlert
}: OverviewPaneProps) {
  const { dt } = useDashboardText();
  const hit = cacheHitReading(metricMap);
  const healthLoading = booting || HEALTH_PENDING.some((name) => pendingMetricNames.has(name));
  const cards = useMemo<KpiTileModel[]>(() => {
    const metricCards: KpiTileModel[] = KPI_SPECS.map((item) => {
      const label = item.key === 'deadlock' ? dt(item.label) : item.label;
      const body = item.key === 'deadlock' ? dt(item.body) : item.body;
      const info = <PostgresHint kind={`pg-kpi-${item.key}`} title={label} body={body} />;
      const jump = postgresKpiJump(item.key);
      const activate = jump
        ? { onActivate: () => onOpenFocus(jump.anchor), activatesDialog: false as const }
        : {};
      if (item.key === 'cache') {
        const value = hit.percent == null ? EMPTY : formatCacheHitPercent(hit.percent);
        return {
          key: item.key,
          label,
          value,
          tone: hit.percent == null ? undefined : item.color,
          info,
          ...activate
        };
      }
      const latest = item.key === 'deadlock'
        ? postgresWindowCount(metricMap, item.metric)
        : postgresLatest(metricMap, item.metric);
      const shown = item.key === 'deadlock' && latest != null ? Math.round(latest) : latest;
      const tone = item.key === 'deadlock'
        ? postgresDeadlockTone(shown, item.color)
        : (latest == null ? undefined : item.color);
      return {
        key: item.key,
        label,
        value: latest == null ? EMPTY : (
          item.key === 'deadlock' ? formatEventCount(latest) : joinMetric(latest, item.unit)
        ),
        tone,
        info,
        ...activate
      };
    });
    metricCards.push({
      key: ALERT_KPI_KEY,
      label: ALERT_KPI_LABEL,
      value: postgresAlertKpiValue(alertCount),
      tone: postgresAlertKpiTone(alertCount),
      onActivate: onOpenAlerts,
      expanded: alertsOpen
    });
    return metricCards;
  }, [alertCount, alertsOpen, dt, hit.percent, metricMap, onOpenAlerts, onOpenFocus]);

  const loadingTiles: KpiTileModel[] = [
    ...KPI_SPECS.map((item) => ({
      key: item.key,
      label: item.key === 'deadlock' ? dt(item.label) : item.label,
      value: ''
    })),
    { key: ALERT_KPI_KEY, label: ALERT_KPI_LABEL, value: '' }
  ];

  return (
    <div data-postgres-pane="overview" className="contents">
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
        <div className={proChromeClass.shortcutGrid} data-postgres-focus="grid">
          {FOCUS_SPECS.map((card) => {
            const plotted = postgresMerged(metricMap, [{ name: card.metric, label: card.label }]);
            const latest = postgresLatest(metricMap, card.metric);
            const samples = seriesSampleValues(plotted);
            const quiet = postgresFocusQuiet(latest, samples);
            const loading = pendingMetricNames.has(card.metric) && plotted.length === 0 && latest == null;
            const axis = describeFocusAxis('cps', samples);
            return (
              <ProFocusCard key={card.key}>
                <div className={proChromeClass.shortcutCopy} data-postgres-focus={card.key} data-postgres-focus-weight={quiet ? 'quiet' : 'normal'}>
                  <FocusShortcutTitle
                    label={card.label}
                    unit={axis.unitLabel}
                    hint={<PostgresHint kind={`pg-focus-${card.key}`} title={card.label} body={card.body} />}
                  />
                  {loading ? <ProDashLoading size="small" /> : (
                    <div
                      className={proChromeClass.shortcutValue}
                      style={latest == null ? undefined : {
                        color: card.color,
                        ...(quiet ? { fontSize: 15, fontWeight: 500 } : {})
                      }}
                    >
                      {latest == null ? EMPTY : formatFocusHeadline(axis, latest)}
                    </div>
                  )}
                  <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpenFocus(card.anchor)}>
                    {card.cta}
                  </button>
                </div>
                {plotted.length > 0 ? (
                  <ThinTimeSeries
                    bare
                    numericAxis
                    className={proChromeClass.focusChart}
                    title=""
                    unit="cps"
                    data={plotted}
                    legends={[{ label: card.label, color: card.color }]}
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
