import type {
  NetworkStatusTopologyLink,
  NetworkStatusTopologyNode,
} from '@/app/ops-analysis/types/sceneWidget';

export interface FaultPathInput {
  nodes: NetworkStatusTopologyNode[];
  links: NetworkStatusTopologyLink[];
  centerId: string;
  selectedNodeId: string;
}

export interface FaultPathResult {
  nodeIds: string[];
  linkIds: string[];
}

export interface GraphNodeViewModel extends NetworkStatusTopologyNode {
  x: number;
  y: number;
}

export interface GraphLinkViewModel extends NetworkStatusTopologyLink {
  active?: boolean;
}

const ACTIVE_ALERT_STATUS = 'pending,processing,unassigned';

const normalizeId = (value: unknown) => String(value ?? '');

export const getLinkId = (link: NetworkStatusTopologyLink) =>
  normalizeId(link.id || link.relationship_id || `${getLinkEndpoints(link).source}-${getLinkEndpoints(link).target}`);

export const getLinkEndpoints = (link: NetworkStatusTopologyLink) => ({
  source: normalizeId(link.source || link.source_device),
  target: normalizeId(link.target || link.target_device),
});

export const getLinkPortLabel = (link: NetworkStatusTopologyLink) => {
  const sourcePort = link.source_port || link.source_inst_name;
  const targetPort = link.target_port || link.target_inst_name;
  return [sourcePort, targetPort].filter(Boolean).join(' / ');
};

export const buildAlertListUrl = ({
  resourceType,
  resourceId,
}: {
  resourceType: string;
  resourceId: string;
}) => {
  const params = new URLSearchParams();
  params.set('resource_type', resourceType);
  params.set('resource_id', resourceId);
  params.set('activate', '1');
  params.set('status', ACTIVE_ALERT_STATUS);
  return `/alarm/alarms?${params.toString()}`;
};

export const buildInstanceDetailUrl = ({
  modelId,
  instId,
  instName,
}: {
  modelId: string;
  instId: string;
  instName?: string;
}) => {
  const params = new URLSearchParams({
    model_id: modelId,
    inst_id: instId,
  });
  if (instName) {
    params.set('inst_name', instName);
  }
  return `/cmdb/assetData/detail/baseInfo?${params.toString()}`;
};

export const getNodeResource = (node: NetworkStatusTopologyNode) => ({
  resourceType: normalizeId(node.resource_type || node.model_id),
  resourceId: normalizeId(node.resource_id || node.id),
});

export const buildFaultPath = ({
  nodes,
  links,
  centerId,
  selectedNodeId,
}: FaultPathInput): FaultPathResult => {
  const nodeMap = new Map(nodes.map((node) => [normalizeId(node.id), node]));
  const selected = nodeMap.get(normalizeId(selectedNodeId));
  const center = normalizeId(centerId);

  if (!selected || normalizeId(selected.id) === center) {
    return selected ? { nodeIds: [normalizeId(selected.id)], linkIds: [] } : { nodeIds: [], linkIds: [] };
  }

  const adjacency = new Map<string, Array<{ nextId: string; linkId: string }>>();
  links.forEach((link) => {
    const { source, target } = getLinkEndpoints(link);
    const linkId = getLinkId(link);
    if (!source || !target) return;
    adjacency.set(source, [...(adjacency.get(source) || []), { nextId: target, linkId }]);
    adjacency.set(target, [...(adjacency.get(target) || []), { nextId: source, linkId }]);
  });

  const queue = [normalizeId(selected.id)];
  const visited = new Set(queue);
  const previous = new Map<string, { nodeId: string; linkId: string }>();

  while (queue.length) {
    const current = queue.shift()!;
    if (current === center) break;

    const neighbors = [...(adjacency.get(current) || [])].sort((a, b) => {
      const aHop = Number(nodeMap.get(a.nextId)?.hop ?? Number.MAX_SAFE_INTEGER);
      const bHop = Number(nodeMap.get(b.nextId)?.hop ?? Number.MAX_SAFE_INTEGER);
      return aHop - bHop;
    });

    neighbors.forEach((neighbor) => {
      if (visited.has(neighbor.nextId)) return;
      visited.add(neighbor.nextId);
      previous.set(neighbor.nextId, { nodeId: current, linkId: neighbor.linkId });
      queue.push(neighbor.nextId);
    });
  }

  if (!previous.has(center)) {
    return { nodeIds: [normalizeId(selected.id)], linkIds: [] };
  }

  const nodeIds = [center];
  const linkIds: string[] = [];
  let cursor = center;

  while (cursor !== normalizeId(selected.id)) {
    const step = previous.get(cursor);
    if (!step) break;
    linkIds.push(step.linkId);
    nodeIds.push(step.nodeId);
    cursor = step.nodeId;
  }

  return {
    nodeIds: nodeIds.reverse(),
    linkIds: linkIds.reverse(),
  };
};

export const layoutGraph = ({
  nodes,
  links,
  layout,
}: {
  nodes: NetworkStatusTopologyNode[];
  links: NetworkStatusTopologyLink[];
  layout: 'hierarchical' | 'force' | 'circular';
}): { nodes: GraphNodeViewModel[]; links: GraphLinkViewModel[] } => {
  const width = 920;
  const height = 520;
  const centerX = width / 2;
  const centerY = height / 2;

  if (layout === 'circular') {
    const radius = Math.max(120, Math.min(width, height) / 2 - 60);
    return {
      nodes: nodes.map((node, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
        return {
          ...node,
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        };
      }),
      links,
    };
  }

  if (layout === 'force') {
    return {
      nodes: nodes.map((node, index) => {
        const radius = 70 + Number(node.hop || 0) * 95;
        const angle = index * 2.399963;
        return {
          ...node,
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius * 0.72,
        };
      }),
      links,
    };
  }

  const grouped = nodes.reduce<Record<number, NetworkStatusTopologyNode[]>>((acc, node) => {
    const hop = Number(node.hop || 0);
    acc[hop] = [...(acc[hop] || []), node];
    return acc;
  }, {});

  const maxHop = Math.max(...Object.keys(grouped).map(Number), 0);
  return {
    nodes: Object.entries(grouped).flatMap(([hopKey, hopNodes]) => {
      const hop = Number(hopKey);
      const x = maxHop === 0 ? centerX : 90 + (hop * (width - 180)) / maxHop;
      return hopNodes.map((node, index) => ({
        ...node,
        x,
        y: centerY + (index - (hopNodes.length - 1) / 2) * 92,
      }));
    }),
    links,
  };
};
