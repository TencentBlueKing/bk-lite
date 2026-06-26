import type {
  NetworkTopologyLayoutMode,
  NetworkTopologyLayoutResult,
  NetworkTopologyLink,
  NetworkTopologyNode,
  NetworkTopologyPositionedNode,
} from './types';
import {
  NETWORK_TOPOLOGY_VIEWBOX,
  NETWORK_TOPOLOGY_VISUAL,
} from './visual';

interface LayoutInput {
  nodes: NetworkTopologyNode[];
  links: NetworkTopologyLink[];
  centerId?: string;
  mode: NetworkTopologyLayoutMode;
  fitToViewport?: boolean;
  viewport?: {
    width: number;
    height: number;
  };
}

interface RawPosition {
  x: number;
  y: number;
}

const normalizeId = (value: unknown) => String(value ?? '');
const MAX_LAYOUT_EXPAND_SCALE = 1.65;

const buildHopMap = (
  nodes: NetworkTopologyNode[],
  links: NetworkTopologyLink[],
  centerId?: string,
) => {
  const hopMap = new Map<string, number>();
  nodes.forEach((node) => {
    if (node.hop !== undefined) {
      hopMap.set(normalizeId(node.id), Number(node.hop));
    }
  });

  if (!centerId || hopMap.has(centerId)) {
    return hopMap;
  }

  const adjacency = new Map<string, Set<string>>();
  links.forEach((link) => {
    if (!adjacency.has(link.source)) adjacency.set(link.source, new Set());
    if (!adjacency.has(link.target)) adjacency.set(link.target, new Set());
    adjacency.get(link.source)!.add(link.target);
    adjacency.get(link.target)!.add(link.source);
  });

  const queue = [centerId];
  hopMap.set(centerId, 0);
  while (queue.length) {
    const current = queue.shift()!;
    const nextHop = (hopMap.get(current) || 0) + 1;
    (adjacency.get(current) || new Set()).forEach((next) => {
      if (hopMap.has(next)) return;
      hopMap.set(next, nextHop);
      queue.push(next);
    });
  }

  return hopMap;
};

const computeRawPositions = ({
  nodes,
  links,
  centerId,
  mode,
}: LayoutInput): Map<string, RawPosition> => {
  const positions = new Map<string, RawPosition>();
  const ids = nodes.map((node) => normalizeId(node.id));
  const center = centerId || ids[0];

  if (mode === 'circular') {
    const others = ids.filter((id) => id !== center);
    const radius = Math.max(380, others.length * 82);
    if (center) positions.set(center, { x: 0, y: 0 });
    others.forEach((id, index) => {
      const angle =
        (index / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(id, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
    return positions;
  }

  if (mode === 'force') {
    ids.forEach((id, index) => {
      const hop = Number(nodes.find((node) => normalizeId(node.id) === id)?.hop || 0);
      const radius = 170 + hop * 320;
      const angle = index * 2.399963;
      positions.set(id, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius * 0.72,
      });
    });
    if (center && positions.has(center)) {
      const centerPosition = positions.get(center)!;
      positions.forEach((position) => {
        position.x -= centerPosition.x;
        position.y -= centerPosition.y;
      });
    }
    return positions;
  }

  const hopMap = buildHopMap(nodes, links, center);
  const byHop = new Map<number, string[]>();
  ids.forEach((id) => {
    const hop = hopMap.get(id) ?? Number.MAX_SAFE_INTEGER;
    const safeHop = hop === Number.MAX_SAFE_INTEGER ? 99 : hop;
    if (!byHop.has(safeHop)) byHop.set(safeHop, []);
    byHop.get(safeHop)!.push(id);
  });

  byHop.forEach((hopNodes, hop) => {
    hopNodes.forEach((id, index) => {
      positions.set(id, {
        x: hop * NETWORK_TOPOLOGY_VISUAL.layout.columnGap,
        y:
          (index - (hopNodes.length - 1) / 2) *
          NETWORK_TOPOLOGY_VISUAL.layout.rowGap,
      });
    });
  });

  return positions;
};

const fitPositions = (
  nodes: NetworkTopologyNode[],
  rawPositions: Map<string, RawPosition>,
  viewport = NETWORK_TOPOLOGY_VIEWBOX,
): NetworkTopologyPositionedNode[] => {
  if (!nodes.length) return [];

  const visual = NETWORK_TOPOLOGY_VISUAL;
  const halfWidth = visual.node.width / 2;
  const halfHeight = visual.node.height / 2;
  const points = nodes.map((node) => rawPositions.get(normalizeId(node.id)) || { x: 0, y: 0 });
  const minX = Math.min(...points.map((point) => point.x - halfWidth));
  const maxX = Math.max(...points.map((point) => point.x + halfWidth));
  const minY = Math.min(...points.map((point) => point.y - halfHeight));
  const maxY = Math.max(...points.map((point) => point.y + halfHeight));
  const rawWidth = Math.max(1, maxX - minX);
  const rawHeight = Math.max(1, maxY - minY);
  const targetWidth = viewport.width - visual.layout.paddingX * 2;
  const targetHeight = viewport.height - visual.layout.paddingY * 2;
  const scale = Math.min(
    MAX_LAYOUT_EXPAND_SCALE,
    targetWidth / rawWidth,
    targetHeight / rawHeight,
  );
  const fittedWidth = rawWidth * scale;
  const fittedHeight = rawHeight * scale;
  const originX = (viewport.width - fittedWidth) / 2 - minX * scale;
  const originY = (viewport.height - fittedHeight) / 2 - minY * scale;

  return nodes.map((node) => {
    const point = rawPositions.get(normalizeId(node.id)) || { x: 0, y: 0 };
    return {
      ...node,
      x: originX + point.x * scale,
      y: originY + point.y * scale,
    };
  });
};

const withCurveOffsets = (links: NetworkTopologyLink[]) => {
  const pairCount = new Map<string, number>();
  const pairIndex = new Map<string, number>();
  links.forEach((link) => {
    const key = [link.source, link.target].sort().join('__');
    pairCount.set(key, (pairCount.get(key) || 0) + 1);
  });

  return links.map((link) => {
    const key = [link.source, link.target].sort().join('__');
    const total = pairCount.get(key) || 1;
    const index = pairIndex.get(key) || 0;
    pairIndex.set(key, index + 1);
    return {
      ...link,
      curveOffset: (index - (total - 1) / 2) * 48,
    };
  });
};

export const layoutNetworkTopology = (
  input: LayoutInput,
): NetworkTopologyLayoutResult => {
  const rawPositions = computeRawPositions(input);
  return {
    nodes: input.fitToViewport === false
      ? input.nodes.map((node) => ({
        ...node,
        ...(rawPositions.get(normalizeId(node.id)) || { x: 0, y: 0 }),
      }))
      : fitPositions(input.nodes, rawPositions, input.viewport),
    links: withCurveOffsets(input.links),
  };
};

export const applyNodePositionOverrides = (
  layout: NetworkTopologyLayoutResult,
  overrides: Map<string, RawPosition>,
): NetworkTopologyLayoutResult => ({
  nodes: layout.nodes.map((node) => {
    const override = overrides.get(node.id);
    return override ? { ...node, ...override } : node;
  }),
  links: layout.links,
});
