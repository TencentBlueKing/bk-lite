'use client';

import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { MongoHint } from './hint';
import {
  formatEventCount,
  formatMongoReading,
  mongoCountMerged,
  mongoLatest,
  mongoMerged,
  type MongoMetricMap
} from './series';

export interface MongoSeriesSpec {
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
}

export function MongoTrend({
  anchor,
  title,
  body,
  series,
  metricMap,
  pending,
  points,
  pendingNames,
  percent = false,
  counts = false,
  emptyText = '本窗口暂无数据'
}: {
  anchor: string;
  title: string;
  body: string;
  series: readonly MongoSeriesSpec[];
  metricMap: MongoMetricMap;
  pending: ReadonlySet<string>;
  /** 配对出来的百分比折线。不传就按序列名合并。 */
  points?: ChartData[];
  /** 派生折线的等待依据。不传就用序列名。 */
  pendingNames?: readonly string[];
  percent?: boolean;
  counts?: boolean;
  emptyText?: string;
}) {
  const multi = series.length > 1;
  const mixedUnits = new Set(series.map((item) => item.unit)).size > 1;
  const data = points
    ?? (counts
      ? mongoCountMerged(metricMap, series.map((item) => ({ name: item.name, label: item.label })))
      : mongoMerged(metricMap, series.map((item) => ({ name: item.name, label: item.label }))));
  const waitFor = pendingNames ?? series.map((item) => item.name);
  const awaiting = waitFor.some((name) => pending.has(name)) && data.length === 0;
  const unit = series[0]?.unit || 'none';
  const readingOf = (item: MongoSeriesSpec) => {
    if (!multi) return undefined;
    const latest = mongoLatest(metricMap, item.name);
    if (counts) return latest == null ? '—' : formatEventCount(latest);
    return formatMongoReading(latest, item.unit);
  };
  return (
    <div id={`mongo-${anchor}`} className="min-w-0" data-mongodb-chart={anchor}>
      <ThinTimeSeries
        title={title}
        hintNode={<MongoHint kind={`mongo-chart-${anchor}`} title={title} body={body} />}
        unit={unit}
        valueBounds={percent ? { min: 0, max: 100 } : undefined}
        pinAxisZero={counts || (!percent && (unit === 'cps' || unit === 'byteps' || unit === 'counts'))}
        independentAxes={mixedUnits}
        keepLegend={multi}
        loading={awaiting}
        emptyText={emptyText}
        data={data}
        legends={series.map((item) => ({
          label: item.label,
          color: item.color,
          unit: mixedUnits ? item.unit : undefined,
          reading: readingOf(item)
        }))}
      />
    </div>
  );
}
