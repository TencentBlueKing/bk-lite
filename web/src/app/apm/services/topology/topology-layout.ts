import { DagreLayout } from '@antv/layout';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';

export interface PositionedApmTopologyNode extends ApmTopologyNode {
  x: number;
  y: number;
}

interface EdgeEndpoint {
  x: number;
  y: number;
  radius: number;
}

export interface TopologyEdgeGeometry {
  path: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  controlX: number;
  controlY: number;
  labelX: number;
  labelY: number;
}

const CANVAS_BOUNDS = {
  minX: 150,
  maxX: 900,
  minY: 100,
  maxY: 390,
} as const;

const normalizeAxis = (
  value: number,
  sourceMin: number,
  sourceMax: number,
  targetMin: number,
  targetMax: number,
) => {
  if (sourceMin === sourceMax) return (targetMin + targetMax) / 2;
  return targetMin + ((value - sourceMin) / (sourceMax - sourceMin)) * (targetMax - targetMin);
};

const roundCoordinate = (value: number) => Math.round(value * 100) / 100;

export const layoutLayeredTopology = async (
  nodes: ApmTopologyNode[],
  edges: ApmTopologyEdge[],
): Promise<PositionedApmTopologyNode[]> => {
  if (nodes.length === 0) return [];

  const layout = new DagreLayout({
    rankdir: 'LR',
    nodesep: 90,
    edgesep: 32,
    ranksep: 150,
    nodeSize: [76, 76],
    edgeLabelSize: [84, 20],
    edgeLabelOffset: 12,
  });

  await layout.execute({
    nodes: nodes.map((item) => ({ id: item.id })),
    edges: edges.map((item, index) => ({
      id: `apm-topology-edge-${index}`,
      source: item.source,
      target: item.target,
    })),
  });

  const rawPositions = new Map<string, { x: number; y: number }>();
  layout.forEachNode((item) => {
    rawPositions.set(String(item.id), { x: item.x, y: item.y });
  });

  const rawValues = nodes.map((item) => rawPositions.get(item.id) ?? { x: 0, y: 0 });
  const xValues = rawValues.map((item) => item.x);
  const yValues = rawValues.map((item) => item.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);

  return nodes.map((item) => {
    const raw = rawPositions.get(item.id) ?? { x: 0, y: 0 };
    return {
      ...item,
      x: roundCoordinate(normalizeAxis(raw.x, minX, maxX, CANVAS_BOUNDS.minX, CANVAS_BOUNDS.maxX)),
      y: roundCoordinate(normalizeAxis(raw.y, minY, maxY, CANVAS_BOUNDS.minY, CANVAS_BOUNDS.maxY)),
    };
  });
};

const unitVector = (fromX: number, fromY: number, toX: number, toY: number) => {
  const dx = toX - fromX;
  const dy = toY - fromY;
  const length = Math.hypot(dx, dy) || 1;
  return { x: dx / length, y: dy / length };
};

export const buildTopologyEdgeGeometry = (
  source: EdgeEndpoint,
  target: EdgeEndpoint,
  reciprocal: boolean,
): TopologyEdgeGeometry => {
  const direct = unitVector(source.x, source.y, target.x, target.y);
  const midpointX = (source.x + target.x) / 2;
  const midpointY = (source.y + target.y) / 2;
  const curveOffset = reciprocal ? 28 : 0;
  const controlX = midpointX - direct.y * curveOffset;
  const controlY = midpointY + direct.x * curveOffset;
  const sourceDirection = unitVector(source.x, source.y, controlX, controlY);
  const targetDirection = unitVector(target.x, target.y, controlX, controlY);
  const startX = source.x + sourceDirection.x * (source.radius + 4);
  const startY = source.y + sourceDirection.y * (source.radius + 4);
  const endX = target.x + targetDirection.x * (target.radius + 9);
  const endY = target.y + targetDirection.y * (target.radius + 9);
  const labelX = (startX + 2 * controlX + endX) / 4;
  const labelY = (startY + 2 * controlY + endY) / 4;

  return {
    path: `M ${roundCoordinate(startX)} ${roundCoordinate(startY)} Q ${roundCoordinate(controlX)} ${roundCoordinate(controlY)} ${roundCoordinate(endX)} ${roundCoordinate(endY)}`,
    startX,
    startY,
    endX,
    endY,
    controlX,
    controlY,
    labelX,
    labelY,
  };
};

export const hasReciprocalTopologyEdge = (
  edge: ApmTopologyEdge,
  edgePairs: ReadonlySet<string>,
) => edgePairs.has(`${edge.target}\u0000${edge.source}`);
