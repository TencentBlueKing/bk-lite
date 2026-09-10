import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_NODE_GRAPH_MAX_EDGES,
  buildNodeGraph,
  isNodeGraphMappingComplete,
  layoutNodeGraphBipartite,
} from '../nodeGraphData';

const mapping = {
  identityMode: 'ip' as const,
  sourceField: 'src',
  targetField: 'dst',
  valueField: 'value',
};

test('incomplete mapping is not ready and builds an empty graph', () => {
  assert.equal(isNodeGraphMappingComplete({ sourceField: 'src' }), false);
  assert.deepEqual(buildNodeGraph([{ src: '10.0.0.1', dst: '10.0.0.2', value: 9 }], {
    sourceField: 'src',
    targetField: 'dst',
  }), { nodes: [], edges: [] });
});

test('service mode requires a destination port field', () => {
  assert.equal(
    isNodeGraphMappingComplete({
      identityMode: 'service',
      sourceField: 'src',
      targetField: 'dst',
      valueField: 'value',
    }),
    false,
  );
});

test('ip mode aggregates duplicate pairs and drops self-loops and blank rows', () => {
  const graph = buildNodeGraph(
    [
      { src: '10.0.0.1', dst: '10.0.0.2', value: 8 },
      { src: '10.0.0.1', dst: '10.0.0.2', value: 2 },
      { src: '10.0.0.2', dst: '10.0.0.2', value: 99 },
      { src: '', dst: '10.0.0.3', value: 4 },
      { src: '10.0.0.3', dst: '10.0.0.1', value: 5 },
    ],
    mapping,
  );
  assert.deepEqual(
    graph.edges.map((edge) => [edge.source, edge.target, edge.value]),
    [
      ['10.0.0.1', '10.0.0.2', 10],
      ['10.0.0.3', '10.0.0.1', 5],
    ],
  );
  const nodeById = Object.fromEntries(graph.nodes.map((node) => [node.id, node]));
  assert.equal(nodeById['10.0.0.1'].outbound, 10);
  assert.equal(nodeById['10.0.0.1'].inbound, 5);
  assert.equal(nodeById['10.0.0.2'].inbound, 10);
  assert.equal(nodeById['10.0.0.3'].outbound, 5);
});

test('service mode uses destination IP:port and skips missing ports', () => {
  const graph = buildNodeGraph(
    [
      { src: '10.0.0.1', dst: '10.0.0.9', dst_port: 443, value: 7 },
      { src: '10.0.0.2', dst: '10.0.0.9', dst_port: 443, value: 3 },
      { src: '10.0.0.1', dst: '10.0.0.9', value: 50 },
    ],
    {
      identityMode: 'service',
      sourceField: 'src',
      targetField: 'dst',
      targetPortField: 'dst_port',
      valueField: 'value',
    },
  );
  assert.deepEqual(
    graph.edges.map((edge) => [edge.source, edge.target, edge.value]),
    [
      ['10.0.0.1', '10.0.0.9:443', 7],
      ['10.0.0.2', '10.0.0.9:443', 3],
    ],
  );
});

test('keeps the highest-traffic edges up to the cap', () => {
  const rows = Array.from({ length: 5 }, (_, index) => ({
    src: `10.0.0.${index + 1}`,
    dst: '10.0.0.9',
    value: index + 1,
  }));
  const graph = buildNodeGraph(rows, { ...mapping, maxEdges: 2 });
  assert.equal(graph.edges.length, 2);
  assert.equal(graph.edges[0].value, 5);
  assert.equal(graph.edges[1].value, 4);
  assert.equal(DEFAULT_NODE_GRAPH_MAX_EDGES, 100);
});

test('unwraps { items: [...] } like other rank widgets', () => {
  const graph = buildNodeGraph(
    { items: [{ src: 'a', dst: 'b', value: 1 }] },
    mapping,
  );
  assert.equal(graph.edges[0].source, 'a');
});

test('bipartite layout puts sources on the left and targets on the right', () => {
  const graph = buildNodeGraph(
    [
      { src: '10.0.0.1', dst: '10.0.0.9', value: 30 },
      { src: '10.0.0.2', dst: '10.0.0.9', value: 10 },
      { src: '10.0.0.9', dst: '10.0.0.3', value: 5 },
    ],
    mapping,
  );
  const placed = layoutNodeGraphBipartite(graph, 400, 240);
  const sources = placed.nodes.filter((node) => node.role === 'source');
  const targets = placed.nodes.filter((node) => node.role === 'target');

  assert.deepEqual(
    sources.map((node) => node.label),
    ['10.0.0.1', '10.0.0.2', '10.0.0.9'],
  );
  assert.deepEqual(
    targets.map((node) => node.label),
    ['10.0.0.9', '10.0.0.3'],
  );
  assert.ok(sources.every((node) => node.x < 120));
  assert.ok(targets.every((node) => node.x > 220));
  assert.equal(
    placed.edges.filter((edge) => edge.source === 'source:10.0.0.9' && edge.target === 'target:10.0.0.3').length,
    1,
  );
  assert.equal(placed.nodes.filter((node) => node.label === '10.0.0.9').length, 2);
});

test('bipartite layout returns empty positions for an empty graph', () => {
  assert.deepEqual(layoutNodeGraphBipartite({ nodes: [], edges: [] }, 400, 240), {
    nodes: [],
    edges: [],
  });
});
