import type { ChartData, GapInterval } from '@/app/monitor/types';
import { attachGapIntervals } from '@/app/monitor/utils/gapIntervals';

export type AlertSnapshotPoint = [number, string];

export interface AlertSnapshotChartModel {
  values: AlertSnapshotPoint[];
  dataValues: AlertSnapshotPoint[];
  gapIntervals: GapInterval[];
  xAxisDomain: [number, number] | null;
  noDataTimes: number[];
}

interface AlertSnapshot {
  type?: string;
  event_time?: string;
  snapshot_time?: string;
  raw_data?: {
    values?: AlertSnapshotPoint[];
  } | Record<string, never>;
}

const hasRawData = (rawData: AlertSnapshot['raw_data']): boolean =>
  !!rawData && Object.keys(rawData).length > 0;

const toUnixSeconds = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1e12 ? Math.floor(value / 1000) : value;
  }
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.floor(parsed / 1000);
};

const readSnapshotPoints = (snapshot: AlertSnapshot): AlertSnapshotPoint[] => {
  if (!hasRawData(snapshot.raw_data)) {
    return [];
  }
  const points: AlertSnapshotPoint[] = [];
  (snapshot.raw_data?.values || []).forEach((point) => {
    if (!Array.isArray(point) || point.length < 2) return;
    const timestamp = Number(point[0]);
    if (!Number.isFinite(timestamp)) return;
    points.push([timestamp, String(point[1])]);
  });
  return points;
};

const buildNoDataGapIntervals = (
  noDataTimes: number[],
  valueTimes: number[]
): GapInterval[] => {
  const uniqueNoDataTimes = [...new Set(noDataTimes)]
    .filter((time) => Number.isFinite(time))
    .sort((left, right) => left - right);
  if (!uniqueNoDataTimes.length) {
    return [];
  }

  const uniqueValueTimes = [...new Set(valueTimes)]
    .filter((time) => Number.isFinite(time))
    .sort((left, right) => left - right);
  const clusters: number[][] = [[uniqueNoDataTimes[0]]];

  uniqueNoDataTimes.slice(1).forEach((time) => {
    const cluster = clusters[clusters.length - 1];
    const lastTime = cluster[cluster.length - 1];
    const hasValueBetween = uniqueValueTimes.some(
      (valueTime) => valueTime > lastTime && valueTime < time
    );
    if (hasValueBetween) {
      clusters.push([time]);
      return;
    }
    cluster.push(time);
  });

  return clusters.map((cluster) => {
    const firstNoData = cluster[0];
    const lastNoData = cluster[cluster.length - 1];
    const lastValueBefore = [...uniqueValueTimes]
      .reverse()
      .find((time) => time <= firstNoData);
    const firstValueAfter = uniqueValueTimes.find((time) => time > lastNoData);
    // 最后一个真实点之后已经没有新采样，空窗接到该点；不把最后一个 Y 值水平拖进空窗。
    const start = lastValueBefore ?? firstNoData;
    const end = uniqueValueTimes.includes(lastNoData)
      ? lastNoData
      : (firstValueAfter ?? lastNoData);
    return {
      start,
      end,
      duration: end - start,
      align: 'exact' as const
    };
  });
};

export const buildAlertSnapshotChartModel = (
  snapshots: AlertSnapshot[] = [],
  options?: { alertType?: string }
): AlertSnapshotChartModel => {
  const isNoDataAlert = options?.alertType === 'no_data';
  const preAlertPoints = new Map<number, string>();
  const otherPoints = new Map<number, string>();
  const noDataTimes: number[] = [];

  snapshots.forEach((snapshot) => {
    if (snapshot.type === 'no_data') {
      const snapshotTime = toUnixSeconds(
        snapshot.snapshot_time || snapshot.event_time
      );
      if (snapshotTime != null) {
        noDataTimes.push(snapshotTime);
      }
      return;
    }

    const target = snapshot.type === 'pre_alert' ? preAlertPoints : otherPoints;
    readSnapshotPoints(snapshot).forEach(([timestamp, value]) => {
      target.set(timestamp, value);
    });
  });

  const lastNoDataTime = noDataTimes.length ? Math.max(...noDataTimes) : null;
  const dataPoints = new Map<number, string>(preAlertPoints);
  otherPoints.forEach((value, timestamp) => {
    if (isNoDataAlert && lastNoDataTime != null && timestamp < lastNoDataTime) {
      return;
    }
    dataPoints.set(timestamp, value);
  });

  const uniqueNoDataTimes = [...new Set(noDataTimes)]
    .filter((time) => Number.isFinite(time))
    .sort((left, right) => left - right);
  const dataValues = [...dataPoints.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([timestamp, value]) => [timestamp, value] as AlertSnapshotPoint);
  const gapIntervals = isNoDataAlert
    ? buildNoDataGapIntervals(
        uniqueNoDataTimes,
        dataValues.map(([timestamp]) => timestamp)
      )
    : [];
  const domainTimes = isNoDataAlert
    ? [...dataPoints.keys(), ...uniqueNoDataTimes]
    : [...dataPoints.keys()];
  const xAxisDomain = domainTimes.length
    ? ([Math.min(...domainTimes), Math.max(...domainTimes)] as [number, number])
    : null;

  return {
    values: dataValues,
    dataValues,
    gapIntervals,
    xAxisDomain,
    noDataTimes: isNoDataAlert ? uniqueNoDataTimes : []
  };
};

export const buildAlertSnapshotChartValues = (
  snapshots: AlertSnapshot[] = []
): AlertSnapshotPoint[] => buildAlertSnapshotChartModel(snapshots).dataValues;

const hasPlotValueKey = (item: ChartData): boolean =>
  Object.keys(item).some((key) => /^value\d+$/.test(key));

const hasFinitePlotValue = (item: ChartData): boolean =>
  Object.keys(item).some(
    (key) =>
      /^value\d+$/.test(key) &&
      typeof item[key] === 'number' &&
      Number.isFinite(item[key] as number)
  );

const ensureAlertSnapshotPlotSeries = (data: ChartData[]): ChartData[] => {
  if (!data.length || data.some(hasPlotValueKey)) {
    return data;
  }
  // 纯无数据快照没有 Y 值。Recharts 的 ReferenceArea 需要同轴 Area 才能画出空窗。
  return data.map((item) => ({
    ...item,
    value1: null,
  }));
};

export const decorateAlertSnapshotChartData = (
  chartData: ChartData[],
  gapIntervals: GapInterval[],
  xAxisDomain: [number, number] | null,
  noDataTimes: number[] = []
): ChartData[] => {
  let data = chartData;
  const times = new Set(data.map((item) => item.time));
  const extras: ChartData[] = [];
  const uniqueNoDataTimes = [...new Set(noDataTimes)]
    .filter((time) => Number.isFinite(time))
    .sort((left, right) => left - right);
  const noDataTimeSet = new Set(uniqueNoDataTimes);

  if (xAxisDomain) {
    if (!times.has(xAxisDomain[0])) {
      extras.push({ time: xAxisDomain[0] });
      times.add(xAxisDomain[0]);
    }
    if (xAxisDomain[1] !== xAxisDomain[0] && !times.has(xAxisDomain[1])) {
      extras.push({ time: xAxisDomain[1] });
      times.add(xAxisDomain[1]);
    }
  }

  uniqueNoDataTimes.forEach((time) => {
    if (times.has(time)) {
      return;
    }
    extras.push({
      time,
      value1: null,
      noDataSnapshot: true,
    });
    times.add(time);
  });

  gapIntervals.forEach((gap) => {
    if (!(gap.end > gap.start)) {
      return;
    }
    const hasInteriorNoData = uniqueNoDataTimes.some(
      (time) => time > gap.start && time < gap.end
    );
    if (hasInteriorNoData) {
      return;
    }
    const hasLeftValue = data.some(
      (item) => item.time <= gap.start && hasFinitePlotValue(item)
    );
    const hasRightValue = data.some(
      (item) => item.time >= gap.end && hasFinitePlotValue(item)
    );
    if (!(hasLeftValue && hasRightValue)) {
      return;
    }
    const mid = (gap.start + gap.end) / 2;
    if (!times.has(mid)) {
      extras.push({ time: mid, value1: null });
      times.add(mid);
    }
  });

  if (extras.length) {
    data = [...data, ...extras].sort((left, right) => left.time - right.time);
  }

  data = data.map((item) => {
    if (!noDataTimeSet.has(item.time) || hasFinitePlotValue(item)) {
      return item;
    }
    return {
      ...item,
      value1: hasPlotValueKey(item) ? item.value1 ?? null : null,
      noDataSnapshot: true,
    };
  });

  if (!gapIntervals.length) {
    return ensureAlertSnapshotPlotSeries(data);
  }

  return ensureAlertSnapshotPlotSeries(attachGapIntervals(data, gapIntervals));
};

export interface AlertDetailMetricQuery {
  id: number;
  monitor_object_id?: string | number;
}

const isUsableObjectId = (value: unknown): value is string | number => {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value > 0;
  }
  if (typeof value !== 'string') {
    return false;
  }
  const trimmed = value.trim();
  return Boolean(trimmed) && trimmed !== 'all';
};

const resolveAlertDetailMetricId = (alert: Record<string, any>): number | undefined => {
  const queryCondition = alert.policy?.query_condition;
  if (queryCondition?.type !== 'metric' || queryCondition.metric_id == null) {
    return undefined;
  }
  const metricId = Number(queryCondition.metric_id);
  if (!Number.isFinite(metricId) || metricId <= 0) {
    return undefined;
  }
  return metricId;
};

/**
 * 告警详情只查这一条指标定义。对象 ID 必须来自告警策略，不得复用左侧树的「全部」。
 */
export const buildAlertDetailMetricQuery = (
  alert: Record<string, any>
): AlertDetailMetricQuery | null => {
  const metricId = resolveAlertDetailMetricId(alert);
  const objectId = alert.policy?.monitor_object;
  if (metricId == null || !isUsableObjectId(objectId)) {
    return null;
  }
  return { id: metricId, monitor_object_id: objectId };
};

export const resolveAlertDetailMetric = (
  alert: Record<string, any>,
  metricInfo: Record<string, any> = {}
): Record<string, any> => {
  const queryCondition = alert.policy?.query_condition;
  const displayUnit =
    alert.policy?.calculation_unit || alert.policy?.metric_unit || metricInfo.unit;

  if (queryCondition?.type === 'formula') {
    const resultName = queryCondition.result_name || metricInfo.display_name || metricInfo.name || '--';
    return {
      ...metricInfo,
      name: metricInfo.name || resultName,
      display_name: resultName,
      unit: displayUnit || ''
    };
  }

  return {
    ...metricInfo,
    unit: displayUnit || ''
  };
};

export const resolveAlertDetailChartUnit = (
  alert: Record<string, any>,
  responseUnit: string | null | undefined
): string =>
  responseUnit ||
  alert.policy?.threshold_unit ||
  alert.policy?.calculation_unit ||
  alert.policy?.metric_unit ||
  '';
