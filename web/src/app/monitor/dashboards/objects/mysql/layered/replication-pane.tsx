'use client';

import React, { useMemo } from 'react';
import { GrayTabEmptyState, KpiTileRow, ThinTimeSeries, type KpiTileModel } from '../../host/layered/pro-chrome';
import { HOST_SERIES_COLOR, HOST_THRESHOLD_COLOR } from '../../host/config';
import { readMysqlRoleBlock, type MysqlRoleTone } from './ia';
import type { MetricSeries } from '../types';

const TONE_COLOR: Record<MysqlRoleTone, string | undefined> = {
  ok: HOST_THRESHOLD_COLOR.ok,
  warn: HOST_THRESHOLD_COLOR.warn,
  muted: undefined
};

const LOADING_KPIS: KpiTileModel[] = [
  { key: 'delay', label: '复制延迟', value: '' },
  { key: 'io', label: 'IO 线程', value: '' },
  { key: 'sql', label: 'SQL 线程', value: '' }
];

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

  if (loading) {
    return (
      <>
        <KpiTileRow loading items={LOADING_KPIS} />
        <ThinTimeSeries
          title="复制延迟"
          loading
          unit="s"
          data={[]}
          legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
        />
      </>
    );
  }

  if (!block || block.fields.length === 0) {
    return <GrayTabEmptyState title="暂无复制数据" />;
  }

  const items: KpiTileModel[] = block.fields.map((field) => ({
    key: field.label,
    label: field.label,
    value: field.value,
    tone: TONE_COLOR[field.tone]
  }));

  return (
    <>
      <KpiTileRow items={items} />
      {block.kind === 'replica' ? (
        <ThinTimeSeries
          title="复制延迟"
          unit="s"
          data={block.delay || []}
          emptyText="暂无复制数据"
          legends={[{ label: '延迟', color: HOST_SERIES_COLOR.memUsed }]}
        />
      ) : null}
    </>
  );
}
