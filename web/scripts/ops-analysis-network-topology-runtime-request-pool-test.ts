import assert from 'node:assert/strict';

import {
  NETWORK_TOPOLOGY_RUNTIME_CONCURRENCY,
  indexRuntimeNodes,
  runRuntimeTasks,
  selectLinkEndpointNodes,
} from '../src/app/ops-analysis/(pages)/view/networkTopology/runtimeRequestPool.ts';

const nodeCount = 100;
const linkCount = 150;
const nodes = Array.from({ length: nodeCount }, (_, index) => ({
  id: `node-${index}`,
}));
const nodeIndex = indexRuntimeNodes(nodes);

assert.deepEqual(
  selectLinkEndpointNodes(nodeIndex, {
    source_node_id: 'node-2',
    target_node_id: 'node-99',
  }).map((node) => node.id),
  ['node-2', 'node-99'],
  'link runtime payload should contain only the two endpoint nodes',
);

assert.deepEqual(
  selectLinkEndpointNodes(nodeIndex, {
    source_node_id: 'node-2',
    target_node_id: 'missing-node',
  }).map((node) => node.id),
  ['node-2'],
  'missing endpoints should not add undefined payload entries',
);

const main = async () => {
  let activeRequests = 0;
  let peakRequests = 0;
  let startedRequests = 0;
  const requestCount = nodeCount + linkCount;
  const tasks = Array.from({ length: requestCount }, (_, index) => async () => {
    startedRequests += 1;
    activeRequests += 1;
    peakRequests = Math.max(peakRequests, activeRequests);
    await new Promise<void>((resolve) => setImmediate(resolve));
    activeRequests -= 1;
    if (index === 17) throw new Error('single request failed');
  });

  const results = await runRuntimeTasks(tasks);

  assert.equal(startedRequests, requestCount, 'a failed request should not stop queued runtime tasks');
  assert.equal(
    peakRequests,
    NETWORK_TOPOLOGY_RUNTIME_CONCURRENCY,
    'large canvases should never exceed the fixed runtime request concurrency',
  );
  assert.equal(
    results.filter((result) => result.status === 'rejected').length,
    1,
    'the scheduler should preserve per-request settled results',
  );

  let current = true;
  let staleStartedRequests = 0;
  const staleResults = await runRuntimeTasks(
    Array.from({ length: 10 }, () => async () => {
      staleStartedRequests += 1;
      await new Promise<void>((resolve) => setImmediate(resolve));
      current = false;
    }),
    { concurrency: 2, isActive: () => current },
  );
  assert.equal(staleStartedRequests, 2, 'generation changes should discard queued stale requests');
  assert.equal(staleResults.length, 2, 'settled results should include only tasks that actually started');

  const baselineSerializedNodes = nodeCount * linkCount;
  const optimizedSerializedNodes = 2 * linkCount;
  assert.equal(baselineSerializedNodes, 15_000);
  assert.equal(optimizedSerializedNodes, 300);

  console.log(
    JSON.stringify({
      input: { nodeCount, linkCount },
      before: {
        requests: requestCount,
        peakConcurrency: requestCount,
        serializedLinkNodes: baselineSerializedNodes,
      },
      after: {
        requests: requestCount,
        peakConcurrency: peakRequests,
        serializedLinkNodes: optimizedSerializedNodes,
      },
    }),
  );
};

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
