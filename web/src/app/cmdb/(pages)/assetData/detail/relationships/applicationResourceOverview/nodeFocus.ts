import type { ApplicationResourceLink, ApplicationResourceNode } from '@/app/cmdb/types/applicationResourceOverview';

export interface NeighborhoodFocus {
  nodeIds: Set<string>;
  linkIds: Set<string>;
}

const normalizeQuery = (query: string) => query.trim().toLowerCase();

export function resolveNeighborhood(
  links: Array<Pick<ApplicationResourceLink, 'id' | 'source' | 'target'>>,
  nodeId: string | null | undefined
): NeighborhoodFocus {
  if (!nodeId) {
    return { nodeIds: new Set(), linkIds: new Set() };
  }

  const nodeIds = new Set<string>([nodeId]);
  const linkIds = new Set<string>();
  links.forEach((link) => {
    if (link.source !== nodeId && link.target !== nodeId) return;
    linkIds.add(link.id);
    nodeIds.add(link.source);
    nodeIds.add(link.target);
  });
  return { nodeIds, linkIds };
}

export interface TopologyNodeSearchItem {
  id: string;
  name: string;
  model_id?: string;
}

export interface TopologyGraphLocator {
  getCellById: (id: string) => unknown;
  centerCell: (cell: unknown) => void;
}

const DEFAULT_NODE_SEARCH_LIMIT = 30;

export function filterTopologyNodes<T extends TopologyNodeSearchItem>(
  nodes: T[],
  query: string,
  limit = DEFAULT_NODE_SEARCH_LIMIT
): T[] {
  const needle = normalizeQuery(query);
  if (!needle) return [];
  const matched: T[] = [];
  for (const node of nodes) {
    if (!node.name.toLowerCase().includes(needle)) continue;
    matched.push(node);
    if (matched.length >= limit) break;
  }
  return matched;
}

export function centerTopologyNode(
  graph: TopologyGraphLocator | null | undefined,
  nodeId: string
): boolean {
  if (!graph || !nodeId) return false;
  const cell = graph.getCellById(nodeId);
  if (!cell) return false;
  graph.centerCell(cell);
  return true;
}

export function filterRelationLinks<T extends Pick<ApplicationResourceLink, 'source' | 'target' | 'asst_id' | 'model_asst_id'>>(
  links: T[],
  nodes: Map<string, Pick<ApplicationResourceNode, 'name'>>,
  query: string,
  focusNodeId?: string | null
): T[] {
  const scoped = focusNodeId
    ? links.filter((link) => link.source === focusNodeId || link.target === focusNodeId)
    : links;
  const needle = normalizeQuery(query);
  if (!needle) return scoped;
  return scoped.filter((link) => {
    const source = nodes.get(link.source);
    const target = nodes.get(link.target);
    const haystack = [
      link.source,
      link.target,
      link.asst_id || '',
      link.model_asst_id || '',
      source?.name || '',
      target?.name || '',
    ]
      .join('\n')
      .toLowerCase();
    return haystack.includes(needle);
  });
}
