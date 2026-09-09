import type { IntegrationLogInstance } from '@/app/log/types/integration';

export const unusedIntegrationNodes = <TNode extends { id?: unknown }>(
  dataSource: IntegrationLogInstance[],
  nodeList: TNode[],
  currentId: string
): TNode[] => {
  const usedNodeIds = new Set(
    dataSource
      .map((item) => item.node_ids)
      .filter((item) => item != null && item !== currentId)
      .map((item) => String(item))
  );
  return nodeList.filter((item) => !usedNodeIds.has(String(item.id ?? '')));
};
