import { layoutNetworkTopology } from '@/app/cmdb/components/networkTopology';
import type {
  NetworkTopologyLayoutMode,
  NetworkTopologyLayoutResult,
  NetworkTopologyLink,
  NetworkTopologyNode,
} from '@/app/cmdb/components/networkTopology';

const COMPONENT_GAP = 160;
const ISLAND_GAP_X = 180;
const ISLAND_GAP_Y = 140;
const NODE_WIDTH = 160;
const NODE_HEIGHT = 110;
const ISLAND_COLUMNS = 4;

const normalizeId = (value: unknown) => String(value ?? '');

export const splitClosedSetComponents = (
  nodeIds: string[],
  links: Array<{ source?: string; target?: string }>,
): { components: string[][]; isolated: string[] } => {
  const ids = nodeIds.map(normalizeId);
  const idSet = new Set(ids);
  const parent = new Map(ids.map((id) => [id, id]));
  const find = (id: string): string => {
    const current = parent.get(id) || id;
    if (current === id) return id;
    const root = find(current);
    parent.set(id, root);
    return root;
  };
  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  };

  const degree = new Map(ids.map((id) => [id, 0]));
  links.forEach((link) => {
    const source = normalizeId(link.source);
    const target = normalizeId(link.target);
    if (!idSet.has(source) || !idSet.has(target) || source === target) return;
    union(source, target);
    degree.set(source, (degree.get(source) || 0) + 1);
    degree.set(target, (degree.get(target) || 0) + 1);
  });

  const isolated = ids.filter((id) => (degree.get(id) || 0) === 0);
  const isolatedSet = new Set(isolated);
  const grouped = new Map<string, string[]>();
  ids.forEach((id) => {
    if (isolatedSet.has(id)) return;
    const root = find(id);
    grouped.set(root, [...(grouped.get(root) || []), id]);
  });

  return {
    components: Array.from(grouped.values()),
    isolated,
  };
};

const pickComponentRoot = (
  nodeIds: string[],
  links: NetworkTopologyLink[],
): string => {
  const degree = new Map(nodeIds.map((id) => [id, 0]));
  const idSet = new Set(nodeIds);
  links.forEach((link) => {
    const source = normalizeId(link.source);
    const target = normalizeId(link.target);
    if (!idSet.has(source) || !idSet.has(target)) return;
    degree.set(source, (degree.get(source) || 0) + 1);
    degree.set(target, (degree.get(target) || 0) + 1);
  });
  return [...degree.entries()].sort((left, right) => {
    if (right[1] !== left[1]) return right[1] - left[1];
    return left[0].localeCompare(right[0]);
  })[0]?.[0] || nodeIds[0];
};

const boundingBox = (nodes: Array<{ x: number; y: number }>) => {
  if (!nodes.length) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  nodes.forEach((node) => {
    minX = Math.min(minX, node.x);
    minY = Math.min(minY, node.y);
    maxX = Math.max(maxX, node.x + NODE_WIDTH);
    maxY = Math.max(maxY, node.y + NODE_HEIGHT);
  });
  return { minX, minY, maxX, maxY };
};

const translateNodes = (
  nodes: NetworkTopologyLayoutResult['nodes'],
  dx: number,
  dy: number,
) =>
  nodes.map((node) => ({
    ...node,
    x: node.x + dx,
    y: node.y + dy,
  }));

export const packClosedSetLayout = ({
  nodes,
  links,
  mode,
}: {
  nodes: NetworkTopologyNode[];
  links: NetworkTopologyLink[];
  mode: NetworkTopologyLayoutMode;
}): NetworkTopologyLayoutResult => {
  const { components, isolated } = splitClosedSetComponents(
    nodes.map((node) => node.id),
    links,
  );
  const nodeById = new Map(nodes.map((node) => [normalizeId(node.id), node]));
  const positioned: NetworkTopologyLayoutResult['nodes'] = [];
  let cursorX = 0;
  let union = { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  let hasContent = false;

  components.forEach((componentIds) => {
    const subsetNodes = componentIds
      .map((id) => nodeById.get(id))
      .filter((node): node is NetworkTopologyNode => Boolean(node));
    const idSet = new Set(componentIds);
    const subsetLinks = links.filter(
      (link) => idSet.has(normalizeId(link.source)) && idSet.has(normalizeId(link.target)),
    );
    const laid = layoutNetworkTopology({
      nodes: subsetNodes,
      links: subsetLinks,
      centerId: pickComponentRoot(componentIds, subsetLinks),
      mode,
      fitToViewport: false,
    });
    const box = boundingBox(laid.nodes);
    const moved = translateNodes(laid.nodes, cursorX - box.minX, -box.minY);
    positioned.push(...moved);
    const movedBox = boundingBox(moved);
    if (!hasContent) {
      union = movedBox;
      hasContent = true;
    } else {
      union = {
        minX: Math.min(union.minX, movedBox.minX),
        minY: Math.min(union.minY, movedBox.minY),
        maxX: Math.max(union.maxX, movedBox.maxX),
        maxY: Math.max(union.maxY, movedBox.maxY),
      };
    }
    cursorX = movedBox.maxX + COMPONENT_GAP;
  });

  const islandOriginX = hasContent ? union.maxX + COMPONENT_GAP : 0;
  const islandOriginY = hasContent ? union.maxY - NODE_HEIGHT : 0;
  isolated.forEach((id, index) => {
    const node = nodeById.get(id);
    if (!node) return;
    const column = index % ISLAND_COLUMNS;
    const row = Math.floor(index / ISLAND_COLUMNS);
    positioned.push({
      ...node,
      x: islandOriginX + column * ISLAND_GAP_X,
      y: islandOriginY + row * ISLAND_GAP_Y,
    });
  });

  const allLinks = layoutNetworkTopology({
    nodes,
    links,
    mode,
    fitToViewport: false,
  }).links;

  return {
    nodes: positioned,
    links: allLinks,
  };
};
