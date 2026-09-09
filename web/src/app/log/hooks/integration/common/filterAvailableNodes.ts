const buildSelectedNodeIdSet = (
  dataSource: Array<{ node_ids?: unknown }>
): Set<unknown> => {
  const selectedNodeIds = new Set<unknown>();
  for (const row of dataSource) {
    selectedNodeIds.add(row.node_ids);
  }
  return selectedNodeIds;
};

const filterAvailableNodes = <T extends { id?: unknown }>(
  nodeList: T[],
  selectedNodeIds: Set<unknown>,
  currentRowNodeId: unknown
): T[] => {
  return nodeList.filter(
    (item) => item.id === currentRowNodeId || !selectedNodeIds.has(item.id)
  );
};

export { buildSelectedNodeIdSet, filterAvailableNodes };
