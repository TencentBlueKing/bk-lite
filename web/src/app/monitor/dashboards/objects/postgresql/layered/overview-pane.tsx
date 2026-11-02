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
import { formatCacheHitPercent } from './cache-hit';
import { PostgresHint } from './hint';
import {
  cacheHitReading,
  postgresLatest,
  postgresMerged,
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
  alertEvents: HostAlertRailEvent[];
  eventsLoading: boolean;
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
    body: '当前连到本库的后端会话数。'
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
    body: '共享缓冲命中占比。展示为百分数；目录公式已含 ×100，勿再 ×100。分母为 0 时显示 —，禁假 0%。'
  },
  {
    key: 'deadlock',
    label: '死锁速率',
    metric: 'postgresql_deadlocks_rate',
    unit: 'cps' as const,
    color: PG_PALETTE.rose,
    body: '每秒发生的死锁次数；持续抬升需排查冲突事务。'
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

const HEALTH_PENDING = [
  'postgresql_numbackends',
  'postgresql_xact_commit_rate',
  'postgresql_cache_hit_ratio',
  'postgresql_blks_hit_rate',
  'postgresql_blks_read_rate',
  'postgresql_deadlocks_rate'
];

export default function OverviewPane({
  metricMap,
  pendingMetricNames,
  booting,
  alertEvents,
  eventsLoading,
  onOpenFocus,
  onFocusAlert
}: OverviewPaneProps) {
  const hit = cacheHitReading(metricMap);
  const healthLoading = booting || HEALTH_PENDING.some((name) => pendingMetricNames.has(name));
  const cards = useMemo<KpiTileModel[]>(() => KPI_SPECS.map((item) => {
    const info = <PostgresHint kind={`pg-kpi-${item.key}`} title={item.label} body={item.body} />;
    if (item.key === 'cache') {
      const value = hit.percent == null ? EMPTY : formatCacheHitPercent(hit.percent);
      return {
        key: item.key,
        label: item.label,
        value,
        tone: hit.percent == null ? undefined : item.color,
        info
      };
    }
    const latest = postgresLatest(metricMap, item.metric);
    return {
      key: item.key,
      label: item.label,
      value: latest == null ? EMPTY : joinMetric(latest, item.unit),
      tone: latest == null ? undefined : item.color,
      info
    };
  }), [hit.percent, metricMap]);

  return (
    <div data-postgres-pane="overview" className="contents">
      <ProSection title="健康概览">
        <KpiTileRow
          items={healthLoading ? KPI_SPECS.map((item) => ({ key: item.key, label: item.label, value: '' })) : cards}
          loading={healthLoading}
          columns={4}
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
            const loading = pendingMetricNames.has(card.metric) && plotted.length === 0 && latest == null;
            const axis = describeFocusAxis('cps', seriesSampleValues(plotted));
            return (
              <ProFocusCard key={card.key}>
                <div className={proChromeClass.shortcutCopy} data-postgres-focus={card.key}>
                  <FocusShortcutTitle
                    label={card.label}
                    unit={axis.unitLabel}
                    hint={<PostgresHint kind={`pg-focus-${card.key}`} title={card.label} body={card.body} />}
                  />
                  {loading ? <ProDashLoading size="small" /> : (
                    <div className={proChromeClass.shortcutValue} style={latest == null ? undefined : { color: card.color }}>
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
