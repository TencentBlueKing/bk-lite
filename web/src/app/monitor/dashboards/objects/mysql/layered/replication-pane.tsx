'use client';

import React, { useMemo } from 'react';
import type { ChartData } from '@/app/monitor/types';
import { GrayTabEmptyState, ProSectionTitle, ThinTimeSeries } from '../../host/layered/pro-chrome';
import { KpiStrip, type KpiCardModel } from '../../host/layered/signal-bar';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import {
  formatMysqlReplicationLag,
  readMysqlRoleBlock,
  type MysqlRoleField,
  type MysqlRoleTone
} from './ia';
import type { MetricSeries } from '../types';
import pro from './pro.module.scss';

const TONE_COLOR: Record<MysqlRoleTone, string | undefined> = {
  ok: HOST_THRESHOLD_COLOR.ok,
  warn: HOST_THRESHOLD_COLOR.warn,
  muted: undefined
};

const REPLICA_LABELS = ['复制延迟', 'IO 线程', 'SQL 线程'] as const;
const THREAD_LABELS = new Set<string>(['IO 线程', 'SQL 线程']);

const toneColor = (field: MysqlRoleField) => {
  if (field.value === '--') return undefined;
  if (THREAD_LABELS.has(field.label) && field.tone === 'warn') return HOST_THRESHOLD_COLOR.crit;
  return TONE_COLOR[field.tone];
};

const displayValue = (field: MysqlRoleField) => {
  if (field.value === '--' || !THREAD_LABELS.has(field.label)) return field.value;
  return `● ${field.value}`;
};

const lagChange = (points: ChartData[] | undefined) => {
  if (!points || points.length < 2) return undefined;
  const previous = points[points.length - 2]?.value1;
  const latest = points[points.length - 1]?.value1;
  if (typeof previous !== 'number' || typeof latest !== 'number') return undefined;
  const delta = latest - previous;
  if (Math.abs(delta) < 0.05) return '较上一点持平';
  const text = formatMysqlReplicationLag(Math.abs(delta));
  return `较上一点 ${delta > 0 ? '+' : '−'}${text}`;
};

const replicaFields = (fields: MysqlRoleField[]) => REPLICA_LABELS.map((label) => (
  fields.find((field) => field.label === label) || { label, value: '--', tone: 'muted' as const }
));

function FillState({ title }: { title: string }) {
  return (
    <div
      className="[&>section>div]:flex [&>section>div]:min-h-[280px] [&>section>div]:items-center [&>section>div]:justify-center"
      data-replication-state={title === '加载中' ? 'loading' : 'empty'}
    >
      <GrayTabEmptyState title={title} />
    </div>
  );
}

export default function ReplicationPane({
  metricMap,
  loading
}: {
  metricMap: Record<string, MetricSeries | undefined>;
  loading: boolean;
}) {
  const block = useMemo(
    () => (loading ? null : readMysqlRoleBlock(metricMap)),
    [loading, metricMap]
  );

  if (loading) return <FillState title="加载中" />;
  if (!block || block.fields.length === 0) return <FillState title="暂无复制数据" />;

  const fields = block.kind === 'replica' ? replicaFields(block.fields) : block.fields;
  const change = lagChange(block.delay);
  const items: KpiCardModel[] = fields.map((field) => ({
    key: field.label,
    label: field.label,
    value: displayValue(field),
    tone: toneColor(field),
    subtitle: field.label === '复制延迟' ? change : undefined
  }));
  const showTrend = block.kind === 'replica' || Boolean(block.delay?.length);

  return (
    <div data-replication-state="ready">
      <ProSectionTitle>状态</ProSectionTitle>
      <div className="mt-3 [&>div]:!grid-cols-3">
        <KpiStrip items={items} />
      </div>
      {showTrend ? (
        <>
          <div className="mt-3">
            <ProSectionTitle>趋势</ProSectionTitle>
          </div>
          <div className={`mt-3 ${pro.perfGrid}`}>
            <div className={pro.perfWide}>
              <ThinTimeSeries
                title="复制延迟"
                unit="s"
                data={block.delay || []}
                emptyText="暂无数据"
                legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
              />
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
