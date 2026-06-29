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

const ACTIVE_ALERT_STATUS = 'pending,processing,unassigned';

const normalizeId = (value: unknown) => String(value ?? '');

export const getLinkId = (link: NetworkStatusTopologyLink) =>
  normalizeId(link.id || link.relationship_id || `${getLinkEndpoints(link).source}-${getLinkEndpoints(link).target}`);

export const getLinkEndpoints = (link: NetworkStatusTopologyLink) => ({
  source: normalizeId(link.source || link.source_device),
  target: normalizeId(link.target || link.target_device),
});

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
