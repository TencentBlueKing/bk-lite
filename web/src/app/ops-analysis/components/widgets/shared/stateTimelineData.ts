/** State timeline 纯数据工具（无 React/antd 依赖，便于单测）。 */

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

/** 把原始数据解析为 {t,v} 点序列：支持 [[t,v]] 与 [{name,value}] 两种形态。 */
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
    .filter((p): p is StatePoint => p !== null);
};

/** 连续相同状态合并为分段。 */
export const buildSegments = (points: StatePoint[]): StateSegment[] => {
  const segs: StateSegment[] = [];
  for (const p of points) {
    const last = segs[segs.length - 1];
    if (last && last.v === p.v) {
      last.count += 1;
      last.endT = p.t;
    } else {
      segs.push({ v: p.v, count: 1, startT: p.t, endT: p.t });
    }
  }
  return segs;
};
