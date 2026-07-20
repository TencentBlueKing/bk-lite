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
