export const NETWORK_TOPOLOGY_RUNTIME_CONCURRENCY = 4;

interface RuntimeLinkEndpoints {
  source_node_id?: string;
  target_node_id?: string;
}

interface RuntimeTaskPoolOptions {
  concurrency?: number;
  isActive?: () => boolean;
}

export const indexRuntimeNodes = <T extends { id: string }>(
  nodes: T[],
): Map<string, T> => new Map(nodes.map((node) => [node.id, node]));

export const selectLinkEndpointNodes = <T>(
  nodesById: ReadonlyMap<string, T>,
  link: RuntimeLinkEndpoints,
): T[] => {
  const result: T[] = [];
  const sourceNode = link.source_node_id
    ? nodesById.get(link.source_node_id)
    : undefined;
  const targetNode = link.target_node_id
    ? nodesById.get(link.target_node_id)
    : undefined;
  if (sourceNode) result.push(sourceNode);
  if (targetNode && targetNode !== sourceNode) result.push(targetNode);
  return result;
};

export const runRuntimeTasks = async <T>(
  tasks: Array<() => Promise<T>>,
  options: RuntimeTaskPoolOptions = {},
): Promise<Array<PromiseSettledResult<T>>> => {
  const {
    concurrency = NETWORK_TOPOLOGY_RUNTIME_CONCURRENCY,
    isActive = () => true,
  } = options;
  const results = new Array<PromiseSettledResult<T>>(tasks.length);
  const workerCount = Math.min(Math.max(concurrency, 1), tasks.length);
  let cursor = 0;

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (cursor < tasks.length && isActive()) {
        const index = cursor;
        cursor += 1;
        try {
          results[index] = {
            status: 'fulfilled',
            value: await tasks[index](),
          };
        } catch (reason) {
          results[index] = { status: 'rejected', reason };
        }
      }
    }),
  );

  return results.filter((result) => result !== undefined);
};
