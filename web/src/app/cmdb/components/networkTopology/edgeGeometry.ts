export interface EdgeGeometryPoint { x: number; y: number }

/** 折点与相邻点过近时视为冗余 */
export const MANUAL_EDGE_VERTEX_MIN_SEGMENT = 4;
/** 折点到源→目标直线的最大距离；全部不超过则视为已拉直并清除 */
export const MANUAL_EDGE_VERTEX_COLLINEAR_TOLERANCE = 8;

const normalizeVertices = (
  vertices?: EdgeGeometryPoint[] | null,
): EdgeGeometryPoint[] =>
  (vertices || [])
    .filter(
      (point) =>
        point && Number.isFinite(point.x) && Number.isFinite(point.y),
    )
    .map((point) => ({ x: point.x, y: point.y }));

const pointDistance = (a: EdgeGeometryPoint, b: EdgeGeometryPoint) => {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.hypot(dx, dy);
};

/** 点到线段的最短距离（含端点投影夹紧） */
const distanceToSegment = (
  point: EdgeGeometryPoint,
  start: EdgeGeometryPoint,
  end: EdgeGeometryPoint,
) => {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq < 1e-8) {
    return pointDistance(point, start);
  }
  const t = Math.max(
    0,
    Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSq),
  );
  return pointDistance(point, {
    x: start.x + t * dx,
    y: start.y + t * dy,
  });
};

const collapseNearbyVertices = (
  vertices: EdgeGeometryPoint[],
  minSegment: number,
): EdgeGeometryPoint[] => {
  if (vertices.length === 0) return [];
  const collapsed: EdgeGeometryPoint[] = [vertices[0]];
  for (let index = 1; index < vertices.length; index += 1) {
    const point = vertices[index];
    const prev = collapsed[collapsed.length - 1];
    if (pointDistance(prev, point) >= minSegment) {
      collapsed.push(point);
    }
  }
  return collapsed;
};

/**
 * 松手写回前归一化手工折点：
 * - 压缩过近冗余点
 * - 若全部折点近似落在源→目标直线上，返回空数组（视为撤销折点）
 */
export const normalizeManualEdgeVertices = (
  source: EdgeGeometryPoint,
  target: EdgeGeometryPoint,
  vertices?: EdgeGeometryPoint[] | null,
  options?: {
    minSegment?: number;
    collinearTolerance?: number;
  },
): EdgeGeometryPoint[] => {
  const minSegment = options?.minSegment ?? MANUAL_EDGE_VERTEX_MIN_SEGMENT;
  const collinearTolerance =
    options?.collinearTolerance ?? MANUAL_EDGE_VERTEX_COLLINEAR_TOLERANCE;
  const cleaned = collapseNearbyVertices(
    normalizeVertices(vertices),
    minSegment,
  );
  if (cleaned.length === 0) return [];

  const allCollinear = cleaned.every(
    (point) => distanceToSegment(point, source, target) <= collinearTolerance,
  );
  if (allCollinear) return [];
  return cleaned;
};
