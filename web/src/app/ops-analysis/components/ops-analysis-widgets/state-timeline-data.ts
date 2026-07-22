export interface StatePoint {
  t: string;
  v: string | number;
}

export interface StateSegment {
  v: string | number;
  count: number;
  startT: string;
  endT: string;
}

export const parsePoints = (rawData: unknown): StatePoint[] => {
  if (!Array.isArray(rawData)) return [];
  return rawData
    .map((item: any) => {
      if (Array.isArray(item) && item.length >= 2) {
        return { t: String(item[0]), v: item[1] };
      }
      if (item && typeof item === 'object' && 'value' in item) {
        return { t: String(item.name ?? item.time ?? ''), v: item.value };
      }
      return null;
    })
    .filter((point): point is StatePoint => point !== null);
};

export const buildSegments = (points: StatePoint[]): StateSegment[] => {
  const segments: StateSegment[] = [];
  for (const point of points) {
    const lastSegment = segments[segments.length - 1];
    if (lastSegment && lastSegment.v === point.v) {
      lastSegment.count += 1;
      lastSegment.endT = point.t;
    } else {
      segments.push({ v: point.v, count: 1, startT: point.t, endT: point.t });
    }
  }
  return segments;
};
