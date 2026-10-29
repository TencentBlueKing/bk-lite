'use client';

import React, { useMemo } from 'react';
import type { MetricUnit } from '../../../shared/types';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisMerged, type RedisMetricMap } from './series';

export interface RedisTrendSeries {
  name: string;
  labelKey: RedisCategoryCopyKey;
  color: string;
}

export interface RedisTrendSpec {
  titleKey: RedisCategoryCopyKey;
  hintKey?: RedisCategoryCopyKey;
  unit: MetricUnit;
  series: readonly RedisTrendSeries[];
  /** 覆盖副标题，例如未配置内存上限。 */
  subtitle?: string;
}

export default function RedisTrendChart({
  spec,
  metricMap,
  pending
}: {
  spec: RedisTrendSpec;
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
}) {
  const { t } = useDashboardText();
  const text = (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
  const proTime = useProTimeWindow();
  const window = proTime?.window ?? null;
  const plotted = useMemo(
    () => clipChartDataToWindow(
      redisMerged(metricMap, spec.series.map((item) => ({
        name: item.name,
        label: redisCategoryText(t, item.labelKey)
      }))),
      window
    ),
    [metricMap, spec, t, window]
  );
  const awaiting = spec.series.some((item) => pending.has(item.name));

  return (
    <ThinTimeSeries
      title={text(spec.titleKey)}
      hint={spec.hintKey ? text(spec.hintKey) : undefined}
      subtitle={spec.subtitle}
      unit={spec.unit}
      loading={awaiting && plotted.length === 0}
      emptyText={text('chartQuiet')}
      data={plotted}
      legends={spec.series.map((item) => ({
        label: text(item.labelKey),
        color: item.color
      }))}
    />
  );
}
