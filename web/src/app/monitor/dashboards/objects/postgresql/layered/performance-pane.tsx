'use client';

import React from 'react';
import type { MetricUnit } from '../../../shared/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { ProSection, ThinTimeSeries } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { PG_PALETTE } from '../config';
import { PostgresHint } from './hint';
import {
  cacheHitChartPoints,
  formatEventCount,
  postgresCountMerged,
  postgresLatest,
  postgresMerged,
  type PostgresMetricMap
} from './series';

interface SeriesSpec {
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
}

interface ChartSpec {
  key: string;
  title: string;
  body: string;
  series: readonly SeriesSpec[];
  /** 命中率图走成对分母，轴固定 0–100，不再乘 100。 */
  cacheHit?: boolean;
  /** 次数桶。纵轴从 0 起，全 0 仍画平线。 */
  countBuckets?: boolean;
  emptyText?: string;
}

interface ZoneSpec {
  id: string;
  title: string;
  grid: 'chartGrid3' | 'chartGrid2';
  charts: readonly ChartSpec[];
}

const CACHE_TXN_ZONES: readonly ZoneSpec[] = [
  {
    id: 'cache-disk',
    title: '缓存与磁盘',
    grid: 'chartGrid3',
    charts: [
      {
        key: 'cache-hit',
        title: '缓存命中率',
        cacheHit: true,
        body: '共享缓冲区命中占总读取的比例。偏低说明热点数据未驻留内存、读盘偏多。\n命中 ÷（命中 + 未命中）× 100%\n分母为 0 时显示 —，不用 0% 顶替。',
        series: [{
          name: 'postgresql_cache_hit_ratio',
          label: '缓存命中率',
          color: PG_PALETTE.emerald,
          unit: 'percent'
        }]
      },
      {
        key: 'hit-read',
        title: '缓存命中与磁盘读',
        body: '同一时段内，对照缓存命中块速率与磁盘块读取速率。',
        series: [
          { name: 'postgresql_blks_hit_rate', label: '命中块速率', color: PG_PALETTE.emerald, unit: 'cps' },
          { name: 'postgresql_blks_read_rate', label: '磁盘块读取速率', color: PG_PALETTE.orange, unit: 'cps' }
        ]
      },
      {
        key: 'blk-write',
        title: '块写入耗时',
        body: '块写入耗时的变化，用来观察写入是否变慢。',
        series: [{
          name: 'postgresql_blk_write_time',
          label: '块写入耗时',
          color: PG_PALETTE.indigo,
          unit: 'msps'
        }]
      }
    ]
  },
  {
    id: 'transactions',
    title: '事务与数据操作',
    grid: 'chartGrid3',
    charts: [
      {
        key: 'xact',
        title: '事务提交与回滚',
        body: '每秒提交与回滚事务数对照；回滚抬升需查失败或冲突。',
        series: [
          { name: 'postgresql_xact_commit_rate', label: '提交', color: PG_PALETTE.emerald, unit: 'cps' },
          { name: 'postgresql_xact_rollback_rate', label: '回滚', color: PG_PALETTE.rose, unit: 'cps' }
        ]
      },
      {
        key: 'rows-write',
        title: '行插入 / 更新 / 删除',
        body: '每秒插入、更新、删除的行数构成。',
        series: [
          { name: 'postgresql_tup_inserted_rate', label: '插入', color: PG_PALETTE.blue, unit: 'cps' },
          { name: 'postgresql_tup_updated_rate', label: '更新', color: PG_PALETTE.orange, unit: 'cps' },
          { name: 'postgresql_tup_deleted_rate', label: '删除', color: PG_PALETTE.rose, unit: 'cps' }
        ]
      },
      {
        key: 'rows-read',
        title: '查询返回与提取行',
        body: '查询返回行速率与提取行速率对照。',
        series: [
          { name: 'postgresql_tup_returned_rate', label: '返回行', color: PG_PALETTE.blue, unit: 'cps' },
          { name: 'postgresql_tup_fetched_rate', label: '提取行', color: PG_PALETTE.cyan, unit: 'cps' }
        ]
      }
    ]
  }
];

const CHECKPOINT_ANOMALY_ZONES: readonly ZoneSpec[] = [
  {
    id: 'checkpoint',
    title: '检查点与缓冲区',
    grid: 'chartGrid3',
    charts: [
      {
        key: 'checkpoints',
        title: '检查点',
        body: '定时检查点与请求检查点速率。请求偏高通常意味着 WAL 或缓冲压力。',
        series: [
          { name: 'postgresql_checkpoints_timed_rate', label: '定时检查点', color: PG_PALETTE.blue, unit: 'cps' },
          { name: 'postgresql_checkpoints_req_rate', label: '请求检查点', color: PG_PALETTE.orange, unit: 'cps' }
        ]
      },
      {
        key: 'buffer-source',
        title: '缓冲区写入来源',
        body: '检查点写入、后端直写、清理写满触发三类压力对照。',
        series: [
          { name: 'postgresql_buffers_checkpoint_rate', label: '检查点写入', color: PG_PALETTE.blue, unit: 'cps' },
          { name: 'postgresql_buffers_backend_rate', label: '后端直写', color: PG_PALETTE.orange, unit: 'cps' },
          { name: 'postgresql_maxwritten_clean_rate', label: '清理写满', color: PG_PALETTE.indigo, unit: 'cps' }
        ]
      },
      {
        key: 'buffer-alloc',
        title: '缓冲区分配',
        body: '新分配缓冲区的速率。持续升高说明缓冲分配在加快。',
        series: [{
          name: 'postgresql_buffers_alloc_rate',
          label: '缓冲区分配',
          color: PG_PALETTE.cyan,
          unit: 'cps'
        }]
      }
    ]
  },
  {
    id: 'anomaly',
    title: '异常与临时',
    grid: 'chartGrid2',
    charts: [
      {
        key: 'deadlock',
        title: '死锁与冲突',
        body: '各时间点上的死锁次数与并发冲突次数。\n用于观察冲突是否在窗口内反复出现。',
        countBuckets: true,
        emptyText: '本窗口暂无死锁或冲突数据。',
        series: [
          { name: 'postgresql_deadlocks_count', label: '死锁', color: PG_PALETTE.rose, unit: 'counts' },
          { name: 'postgresql_conflicts_count', label: '冲突', color: PG_PALETTE.amber, unit: 'counts' }
        ]
      },
      {
        key: 'temp',
        title: '临时文件与写入吞吐',
        body: '临时文件创建速率与临时写入字节吞吐对照。',
        series: [
          { name: 'postgresql_temp_files_rate', label: '临时文件', color: PG_PALETTE.amber, unit: 'cps' },
          { name: 'postgresql_temp_bytes_rate', label: '临时写入', color: PG_PALETTE.indigo, unit: 'byteps' }
        ]
      }
    ]
  }
];

const readingOf = (metricMap: PostgresMetricMap, name: string, unit: MetricUnit) => {
  const latest = postgresLatest(metricMap, name);
  if (latest == null) return '—';
  if (unit === 'counts') return formatEventCount(Math.max(0, latest));
  const formatted = formatMetricValue(latest, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

function PerformanceChart({
  spec,
  metricMap,
  pending
}: {
  spec: ChartSpec;
  metricMap: PostgresMetricMap;
  pending: ReadonlySet<string>;
}) {
  const { dt } = useDashboardText();
  const copy = (text: string) => (spec.countBuckets ? dt(text) : text);
  const multi = spec.series.length > 1;
  const mixedUnits = new Set(spec.series.map((item) => item.unit)).size > 1;
  const data = spec.cacheHit
    ? cacheHitChartPoints(metricMap)
    : spec.countBuckets
      ? postgresCountMerged(metricMap, spec.series.map((item) => ({ name: item.name, label: item.label })))
      : postgresMerged(metricMap, spec.series.map((item) => ({ name: item.name, label: item.label })));
  const awaiting = spec.series.some((item) => pending.has(item.name)) && data.length === 0;
  const unit = spec.series[0]?.unit || 'none';
  return (
    <div id={`pg-perf-${spec.key}`} className="min-w-0" data-postgres-chart={spec.key}>
      <ThinTimeSeries
        title={copy(spec.title)}
        hintNode={<PostgresHint kind={`pg-chart-${spec.key}`} title={copy(spec.title)} body={copy(spec.body)} />}
        unit={unit}
        valueBounds={spec.cacheHit ? { min: 0, max: 100 } : undefined}
        pinAxisZero={spec.countBuckets}
        independentAxes={mixedUnits}
        keepLegend={multi}
        loading={awaiting}
        emptyText={spec.emptyText ? copy(spec.emptyText) : '本窗口暂无数据'}
        data={data}
        legends={spec.series.map((item) => ({
          label: copy(item.label),
          color: item.color,
          unit: mixedUnits ? item.unit : undefined,
          reading: multi ? readingOf(metricMap, item.name, item.unit) : undefined
        }))}
      />
    </div>
  );
}

function TrendSections({
  pane,
  zones,
  metricMap,
  pendingMetricNames
}: {
  pane: 'cache-txn' | 'checkpoint-anomaly';
  zones: readonly ZoneSpec[];
  metricMap: PostgresMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <div data-postgres-pane={pane} className="contents">
      {zones.map((zone) => (
        <ProSection key={zone.id} id={`pg-zone-${zone.id}`} title={zone.title}>
          <div className={host[zone.grid]} data-postgres-zone={zone.id}>
            {zone.charts.map((chart) => (
              <PerformanceChart
                key={chart.key}
                spec={chart}
                metricMap={metricMap}
                pending={pendingMetricNames}
              />
            ))}
          </div>
        </ProSection>
      ))}
    </div>
  );
}

export function CacheTxnPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: PostgresMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <TrendSections
      pane="cache-txn"
      zones={CACHE_TXN_ZONES}
      metricMap={metricMap}
      pendingMetricNames={pendingMetricNames}
    />
  );
}

export function CheckpointAnomalyPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: PostgresMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <TrendSections
      pane="checkpoint-anomaly"
      zones={CHECKPOINT_ANOMALY_ZONES}
      metricMap={metricMap}
      pendingMetricNames={pendingMetricNames}
    />
  );
}
