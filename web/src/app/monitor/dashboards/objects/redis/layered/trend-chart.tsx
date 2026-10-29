'use client';

import React, { useMemo } from 'react';
import type { MetricUnit } from '../../../shared/types';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { redisCategoryText, type RedisCategoryCopyKey } from './redis-copy';
import { redisChartPoints, redisInstantOps, redisLatest, redisProductText, type RedisMetricMap } from './series';

export interface RedisTrendSeries {
  name: string;
  labelKey: RedisCategoryCopyKey;
  color: string;
  /** 上限一类参考线。缺省实线。 */
  dashed?: boolean;
}

export interface RedisTrendSpec {
  titleKey: RedisCategoryCopyKey;
  hintKey?: RedisCategoryCopyKey;
  /** 没有采点时的空态。缺省用通用「窗口内暂无采样」。 */
  emptyKey?: RedisCategoryCopyKey;
  unit: MetricUnit;
  series: readonly RedisTrendSeries[];
  /** 覆盖副标题，例如未配置内存上限。 */
  subtitle?: string;
}

export default function RedisTrendChart({
  spec,
  metricMap,
  pending,
  hint
}: {
  spec: RedisTrendSpec;
  metricMap: RedisMetricMap;
  pending: ReadonlySet<string>;
  /** 覆盖 spec.hintKey。空字符串不显示问号。 */
  hint?: string;
}) {
  const { t } = useDashboardText();
  const text = (key: RedisCategoryCopyKey) => redisCategoryText(t, key);
  const proTime = useProTimeWindow();
  const window = proTime?.window ?? null;
  const keepInstant = spec.series.some((item) => item.name === redisInstantOps);
  const plotted = useMemo(
    () => redisChartPoints(
      metricMap,
      spec.series.map((item) => ({
        name: item.name,
        label: redisCategoryText(t, item.labelKey)
      })),
      window,
      keepInstant
    ),
    [keepInstant, metricMap, spec, t, window]
  );
  const awaiting = spec.series.some((item) => pending.has(item.name));
  const unitLabel = spec.unit === 'cps'
    ? text('rateUnit')
    : spec.unit === 'counts'
      ? text('countUnit')
      : undefined;
  const liveCount = spec.series.filter((item) => redisLatest(metricMap, item.name) != null).length;
  const multi = liveCount > 1;
  const readingOf = (name: string) => (
    redisProductText(metricMap, name, spec.unit, unitLabel) ?? text('legendQuiet')
  );

  return (
    <ThinTimeSeries
      title={text(spec.titleKey)}
      hint={hint ?? (spec.hintKey ? text(spec.hintKey) : undefined)}
      subtitle={spec.subtitle}
      unit={spec.unit}
      loading={awaiting && plotted.length === 0}
      emptyText={text(spec.emptyKey ?? 'sampleEmpty')}
      hideFlatAxisLabels={spec.series.length <= 1}
      keepLegend={multi}
      data={plotted}
      legends={spec.series.map((item) => ({
        label: text(item.labelKey),
        color: item.color,
        dashed: item.dashed,
        reading: multi ? readingOf(item.name) : undefined
      }))}
    />
  );
}
