import type { WorkflowExecutionDetailItem } from '@/app/opspilot/types/studio';

export interface ExecutionPreviewWorkflowNode {
  id: string;
}

export interface ExecutionPreviewWorkflowEdge {
  source: string;
  target: string;
}

function hasValidWorkflowEdge(
  nodes: ExecutionPreviewWorkflowNode[],
  edges: ExecutionPreviewWorkflowEdge[],
) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  return edges.some((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
}

export function buildExecutionPreviewNodeOrder(
  nodes: ExecutionPreviewWorkflowNode[] = [],
  edges: ExecutionPreviewWorkflowEdge[] = [],
) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const indegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  nodes.forEach((node) => {
    indegree.set(node.id, 0);
    adjacency.set(node.id, []);
  });

  edges.forEach((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      return;
    }

    adjacency.get(edge.source)?.push(edge.target);
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
  });

  const visualOrder = new Map(nodes.map((node, index) => [node.id, index]));
  const queue = nodes
    .filter((node) => (indegree.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const order = new Map<string, number>();
  let index = 0;

  while (queue.length > 0) {
    queue.sort((left, right) => (visualOrder.get(left) ?? 0) - (visualOrder.get(right) ?? 0));
    const nodeId = queue.shift();

    if (!nodeId || order.has(nodeId)) {
      continue;
    }

    order.set(nodeId, index);
    index += 1;

    (adjacency.get(nodeId) ?? []).forEach((targetId) => {
      const nextIndegree = (indegree.get(targetId) ?? 0) - 1;
      indegree.set(targetId, nextIndegree);

      if (nextIndegree === 0) {
        queue.push(targetId);
      }
    });
  }

  nodes.forEach((node) => {
    if (!order.has(node.id)) {
      order.set(node.id, index);
      index += 1;
    }
  });

  return order;
}

export function sortExecutionPreviewItems(
  items: WorkflowExecutionDetailItem[],
  nodes: ExecutionPreviewWorkflowNode[] = [],
  edges: ExecutionPreviewWorkflowEdge[] = [],
) {
  const workflowOrder = hasValidWorkflowEdge(nodes, edges)
    ? buildExecutionPreviewNodeOrder(nodes, edges)
    : new Map<string, number>();
  const originalOrder = new Map(items.map((item, index) => [item.node_id, index]));

  return [...items].sort((left, right) => {
    const leftWorkflowIndex = workflowOrder.get(left.node_id);
    const rightWorkflowIndex = workflowOrder.get(right.node_id);

    if (leftWorkflowIndex !== undefined || rightWorkflowIndex !== undefined) {
      return (leftWorkflowIndex ?? Number.MAX_SAFE_INTEGER) - (rightWorkflowIndex ?? Number.MAX_SAFE_INTEGER)
        || (originalOrder.get(left.node_id) ?? 0) - (originalOrder.get(right.node_id) ?? 0);
    }

    const leftNodeIndex = left.node_index ?? Number.MAX_SAFE_INTEGER;
    const rightNodeIndex = right.node_index ?? Number.MAX_SAFE_INTEGER;

    return leftNodeIndex - rightNodeIndex
      || (originalOrder.get(left.node_id) ?? 0) - (originalOrder.get(right.node_id) ?? 0);
  });
}