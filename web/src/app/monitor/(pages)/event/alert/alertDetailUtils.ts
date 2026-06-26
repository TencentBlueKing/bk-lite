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
