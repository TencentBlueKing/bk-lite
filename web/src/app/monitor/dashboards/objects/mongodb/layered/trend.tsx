'use client';

import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import { clipChartDataToWindow } from '../../../shared/utils/pro-chart-window';
import { ThinTimeSeries } from '../../host/layered/pro-chrome';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { MongoHint } from './hint';
import {
  activeQueueChartState,
  formatEventCount,
  formatMongoReading,
  mongoCountMerged,
  mongoLatest,
  mongoMerged,
  mongoPoints,
  type MongoMetricMap
} from './series';

export interface MongoSeriesSpec {
  name: string;
  label: string;
  color: string;
  unit: MetricUnit;
}

const EMPTY_POINTS: ChartData[] = [];

export function MongoTrend({
  anchor,
  title,
  body,
  series,
  metricMap,
  pending,
  points,
  pendingNames,
  hintTitle,
  percent = false,
  counts = false,
  emptyText = '本窗口暂无数据',
  idleText,
  bare = false,
  stretch = false,
  areaOpacity,
  keepSeriesColor = false,
  showHint = true,
  mutedTitle = false,
  resolveValueBounds
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
  /** 说明标题。不传就用卡片标题。 */
  hintTitle?: string;
  percent?: boolean;
  counts?: boolean;
  emptyText?: string;
  /**
   * 每条序列在当前窗口都有点、且值全是 0 时，不画线，改显示这句。
   * 缺数仍走 emptyText。只给活跃与排队，其它趋势不传。
   */
  idleText?: string;
  /** 嵌进已有卡壳，不再套一层 panel。 */
  bare?: boolean;
  /** 卡边拉满所在栅格行，和旁边的卡齐高。 */
  stretch?: boolean;
  /**
   * 用窗口内采样决定百分比轴。传入后不再锁死 0–100。
   * 采样已忽略 null，并已裁到当前图表窗口。
   */
  resolveValueBounds?: (samples: readonly number[]) => { min: number; max: number } | null;
  /** 折线下浅面积。只给指定卡，不改其它趋势。 */
  areaOpacity?: number;
  /** 贴轴时保持序列色。 */
  keepSeriesColor?: boolean;
  /** 标题旁的问号。 */
  showHint?: boolean;
  /** 标题降成弱标签。 */
  mutedTitle?: boolean;
}) {
  const multi = series.length > 1;
  const mixedUnits = new Set(series.map((item) => item.unit)).size > 1;
  const data = points
    ?? (counts
      ? mongoCountMerged(metricMap, series.map((item) => ({ name: item.name, label: item.label })))
      : mongoMerged(metricMap, series.map((item) => ({ name: item.name, label: item.label }))));
  const waitFor = pendingNames ?? series.map((item) => item.name);
  const awaiting = waitFor.some((name) => pending.has(name)) && data.length === 0;
  const proTime = useProTimeWindow();
  const queueState = idleText
    ? activeQueueChartState(
      series.map((item) => clipChartDataToWindow(
        mongoPoints(metricMap, item.name),
        proTime?.window ?? null
      ).flatMap((point) => (
        typeof point.value1 === 'number' && Number.isFinite(point.value1) ? [point.value1] : []
      ))),
      series.map((item) => pending.has(item.name))
    )
    : null;
  const hidePlot = queueState === 'idle' || queueState === 'empty' || queueState === 'loading';
  const shownData = hidePlot ? EMPTY_POINTS : data;
  const shownLoading = queueState === 'loading' || (queueState == null && awaiting);
  const shownEmpty = queueState === 'idle' ? idleText : emptyText;
  const unit = series[0]?.unit || 'none';
  const readingOf = (item: MongoSeriesSpec) => {
    if (!multi) return undefined;
    if (queueState === 'idle') return formatMongoReading(0, item.unit);
    const latest = mongoLatest(metricMap, item.name);
    if (counts) return latest == null ? '—' : formatEventCount(latest);
    return formatMongoReading(latest, item.unit);
  };
  return (
    <div
      id={`mongo-${anchor}`}
      className={stretch ? 'h-full min-w-0' : 'min-w-0'}
      data-mongodb-chart={anchor}
      data-mongodb-axes={mixedUnits ? 'dual' : 'shared'}
      data-mongodb-activity={queueState || undefined}
    >
      <ThinTimeSeries
        title={title}
        hintNode={showHint && title ? <MongoHint kind={`mongo-chart-${anchor}`} title={hintTitle || title} body={body} /> : undefined}
        unit={unit}
        bare={bare}
        className={stretch ? 'h-full' : undefined}
        mutedTitle={mutedTitle}
        valueBounds={resolveValueBounds ? undefined : (percent ? { min: 0, max: 100 } : undefined)}
        resolveValueBounds={resolveValueBounds}
        areaOpacity={areaOpacity}
        keepSeriesColor={keepSeriesColor}
        pinAxisZero={counts || (!percent && (unit === 'cps' || unit === 'byteps' || unit === 'counts'))}
        independentAxes={mixedUnits}
        keepLegend={multi}
        loading={shownLoading}
        emptyText={shownEmpty}
        data={shownData}
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
