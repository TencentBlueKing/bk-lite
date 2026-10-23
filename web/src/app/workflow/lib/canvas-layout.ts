import { DagreLayout } from '@antv/layout';

export interface LayoutNode {
  id: string;
  position: { x: number; y: number };
}

export interface LayoutEdge {
  source: string;
  target: string;
}

const GRID_SIZE = 16;
const NODE_SIZE = 96;
const NODE_X_SPACING = GRID_SIZE * 8;
const NODE_Y_SPACING = GRID_SIZE * 6;
const SUBGRAPH_SPACING = GRID_SIZE * 8;

const snapToGrid = (value: number) => Math.round(value / GRID_SIZE) * GRID_SIZE;

function positionComparator(positionById: Map<string, LayoutNode['position']>) {
  return (left: string, right: string) => {
    const leftPosition = positionById.get(left) || { x: 0, y: 0 };
    const rightPosition = positionById.get(right) || { x: 0, y: 0 };
    return leftPosition.y - rightPosition.y || leftPosition.x - rightPosition.x || left.localeCompare(right);
  };
}

function connectedComponents(nodeIds: string[], edges: LayoutEdge[]) {
  const adjacency = new Map(nodeIds.map((id) => [id, new Set<string>()]));
  edges.forEach(({ source, target }) => {
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  });

  const visited = new Set<string>();
  return nodeIds.flatMap((start) => {
    if (visited.has(start)) return [];
    const component: string[] = [];
    const queue = [start];
    visited.add(start);
    while (queue.length) {
      const id = queue.shift()!;
      component.push(id);
      adjacency.get(id)?.forEach((next) => {
        if (!visited.has(next)) {
          visited.add(next);
          queue.push(next);
        }
      });
    }
    return [component];
  });
}

async function layoutComponent(nodeIds: string[], edges: LayoutEdge[]) {
  const componentIds = new Set(nodeIds);
  const layout = new DagreLayout({
    rankdir: 'LR',
    nodesep: NODE_Y_SPACING,
    edgesep: NODE_Y_SPACING,
    ranksep: NODE_X_SPACING,
    nodeSize: [NODE_SIZE, NODE_SIZE],
  });
  try {
    await layout.execute({
      nodes: nodeIds.map((id) => ({ id })),
      edges: edges
        .filter(({ source, target }) => componentIds.has(source) && componentIds.has(target))
        .map(({ source, target }, index) => ({ id: `${source}-${target}-${index}`, source, target })),
    });

    const positions = new Map<string, LayoutNode['position']>();
    layout.forEachNode((node) => positions.set(String(node.id), {
      x: node.x - NODE_SIZE / 2,
      y: node.y - NODE_SIZE / 2,
    }));
    return positions;
  } finally {
    layout.destroy();
  }
}

export async function layoutWorkflowCanvas<T extends LayoutNode>(nodes: T[], edges: LayoutEdge[]): Promise<T[]> {
  if (!nodes.length) return [];

  const nodeIds = new Set(nodes.map(({ id }) => id));
  const validEdges = edges.filter(({ source, target }) => nodeIds.has(source) && nodeIds.has(target));
  const positionById = new Map(nodes.map(({ id, position }) => [id, position]));
  const comparePosition = positionComparator(positionById);
  const targets = new Set(validEdges.map(({ target }) => target));
  const orderedIds = nodes.map(({ id }) => id).sort((left, right) => {
    const rootOrder = Number(targets.has(left)) - Number(targets.has(right));
    return rootOrder || comparePosition(left, right);
  });
  const components = connectedComponents(orderedIds, validEdges);
  const anchorX = snapToGrid(Math.min(...nodes.map(({ position }) => position.x)));
  const anchorY = snapToGrid(Math.min(...nodes.map(({ position }) => position.y)));
  const nextPositionById = new Map<string, LayoutNode['position']>();
  let componentOffsetY = 0;

  for (const component of components) {
    const componentIdSet = new Set(component);
    const componentIds = [...component].sort(comparePosition);
    const componentEdges = validEdges
      .filter(({ source, target }) => componentIdSet.has(source) && componentIdSet.has(target))
      .sort((left, right) => comparePosition(left.target, right.target) || comparePosition(left.source, right.source));
    const rawPositions = await layoutComponent(componentIds, componentEdges);
    const values = [...rawPositions.values()];
    const minX = Math.min(...values.map(({ x }) => x));
    const minY = Math.min(...values.map(({ y }) => y));
    const maxY = Math.max(...values.map(({ y }) => y + NODE_SIZE));

    componentIds.forEach((id) => {
      const position = rawPositions.get(id)!;
      nextPositionById.set(id, {
        x: anchorX + snapToGrid(position.x - minX),
        y: anchorY + componentOffsetY + snapToGrid(position.y - minY),
      });
    });
    componentOffsetY += snapToGrid(maxY - minY) + SUBGRAPH_SPACING;
  }

  return nodes.map((node) => ({ ...node, position: nextPositionById.get(node.id) || node.position }));
}
