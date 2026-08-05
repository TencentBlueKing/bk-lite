/** 同一设备对多链路的平行微偏移（直线近似）。 */

export const PARALLEL_EDGE_OFFSET_STEP = 16;
export const STATUS_TOPOLOGY_PARALLEL_CONNECTOR = 'status-topology-parallel';

export type Point = { x: number; y: number };

export const getDevicePairKey = (source: string, target: string) =>
  [String(source), String(target)].sort().join('__');

/**
 * 按设备对分配垂直于连线的偏移量，对称分布：…,-16,0,16,…
 */
export const assignParallelOffsets = <T extends { source: string; target: string }>(
  links: T[],
  step = PARALLEL_EDGE_OFFSET_STEP,
): Array<T & { parallelOffset: number }> => {
  const pairCount = new Map<string, number>();
  const pairIndex = new Map<string, number>();
  links.forEach((link) => {
    const key = getDevicePairKey(link.source, link.target);
    pairCount.set(key, (pairCount.get(key) || 0) + 1);
  });

  return links.map((link) => {
    const key = getDevicePairKey(link.source, link.target);
    const total = pairCount.get(key) || 1;
    const index = pairIndex.get(key) || 0;
    pairIndex.set(key, index + 1);
    return {
      ...link,
      parallelOffset: total <= 1 ? 0 : (index - (total - 1) / 2) * step,
    };
  });
};

/**
 * 生成近似平行于源→目标的折线控制点（两端仍回到锚点）。
 * 供自定义 connector 在拖动时按当前端点实时重算，避免绝对 vertices 卡住。
 */
export const buildParallelEdgePoints = (
  source: Point,
  target: Point,
  offset: number,
): Point[] => {
  if (!offset) return [source, target];
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * offset;
  const ny = (dx / len) * offset;
  const t0 = 0.2;
  const t1 = 0.8;
  return [
    source,
    { x: source.x + dx * t0 + nx, y: source.y + dy * t0 + ny },
    { x: source.x + dx * t1 + nx, y: source.y + dy * t1 + ny },
    target,
  ];
};

/** @deprecated 使用 buildParallelEdgePoints；保留给单测兼容 */
export const buildParallelEdgeVertices = (
  source: Point,
  target: Point,
  offset: number,
): Point[] | undefined => {
  if (!offset) return undefined;
  return buildParallelEdgePoints(source, target, offset).slice(1, 3);
};

export const buildParallelConnectorPath = (
  source: Point,
  target: Point,
  offset: number,
): string => {
  const points = buildParallelEdgePoints(source, target, offset);
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ');
};
