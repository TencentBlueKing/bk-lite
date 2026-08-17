export type AlertSnapshotPoint = [number, string];

interface AlertSnapshot {
  event_time?: string;
  raw_data?: {
    values?: AlertSnapshotPoint[];
  } | Record<string, never>;
}

const hasRawData = (rawData: AlertSnapshot['raw_data']): boolean =>
  !!rawData && Object.keys(rawData).length > 0;

export const buildAlertSnapshotChartValues = (
  snapshots: AlertSnapshot[] = []
): AlertSnapshotPoint[] => {
  const pointMap = new Map<number, AlertSnapshotPoint>();

  snapshots.forEach((snapshot) => {
    if (!hasRawData(snapshot.raw_data)) {
      return;
    }

    const values = snapshot.raw_data?.values || [];
    values.forEach((point) => {
      if (!Array.isArray(point) || point.length < 2) return;
      const timestamp = Number(point[0]);
      if (!Number.isFinite(timestamp)) return;
      pointMap.set(timestamp, [timestamp, String(point[1])]);
    });
  });

  return Array.from(pointMap.values()).sort((prev, next) => prev[0] - next[0]);
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
