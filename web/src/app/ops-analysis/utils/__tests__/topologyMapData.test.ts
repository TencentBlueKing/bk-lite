import assert from 'node:assert/strict';
import test from 'node:test';

import {
  layoutTopologyMap,
  parseTopologyMapPayload,
} from '../topologyMapData';

const node = (id: string, overrides: Record<string, unknown> = {}) => ({
  id,
  instance_id: id,
  instance_name: `Node ${id}`,
  model_name: 'Application',
  alert_count: 0,
  ...overrides,
});

test('parses an empty topology as a valid empty graph', () => {
  assert.deepEqual(parseTopologyMapPayload({ nodes: [], edges: [] }), {
    ok: true,
    data: { nodes: [], edges: [] },
  });
});

test('normalizes edge defaults and optional text', () => {
  const result = parseTopologyMapPayload({
    nodes: [node('a', { subtitle: '  Primary  ' }), node('b')],
    edges: [{ source: 'a', target: 'b', label: '  owns  ' }],
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.data.nodes[0].subtitle, 'Primary');
  assert.deepEqual(result.data.edges, [{
    source: 'a',
    target: 'b',
    label: 'owns',
    line_style: 'solid',
    connection_type: 'none',
  }]);
});

test('accepts reverse edges but rejects a second edge in the same direction', () => {
  const reverse = parseTopologyMapPayload({
    nodes: [node('a'), node('b')],
    edges: [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'a', connection_type: 'single' },
    ],
  });
  assert.equal(reverse.ok, true);

  const duplicate = parseTopologyMapPayload({
    nodes: [node('a'), node('b')],
    edges: [
      { source: 'a', target: 'b', label: 'first' },
      { source: 'a', target: 'b', label: 'second', line_style: 'dashed' },
    ],
  });
  assert.equal(duplicate.ok, false);
  if (duplicate.ok) return;
  assert.match(duplicate.error, /source.*target|重复/i);
});

test('rejects invalid node identity, alert count and dangling edge', () => {
  for (const payload of [
    { nodes: [node('')], edges: [] },
    { nodes: [node('a', { alert_count: -1 })], edges: [] },
    { nodes: [node('a', { alert_count: 1.5 })], edges: [] },
    { nodes: [node('a')], edges: [{ source: 'a', target: 'missing' }] },
  ]) {
    assert.equal(parseTopologyMapPayload(payload).ok, false);
  }
});

test('preserves unknown alert level for neutral visual fallback', () => {
  const result = parseTopologyMapPayload({
    nodes: [node('a', { alert_count: 4, alert_level: 'custom' })],
    edges: [],
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.data.nodes[0].alert_level, 'custom');
});

test('dagre layout produces finite stable positions for representative graphs', async () => {
  const cases = [
    {
      name: 'chain',
      nodes: [node('a'), node('b'), node('c')],
      edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }],
    },
    {
      name: 'tree',
      nodes: [node('a'), node('b'), node('c')],
      edges: [{ source: 'a', target: 'b' }, { source: 'a', target: 'c' }],
    },
    {
      name: 'cyclic',
      nodes: [node('a'), node('b'), node('c')],
      edges: [
        { source: 'a', target: 'b' },
        { source: 'b', target: 'c' },
        { source: 'c', target: 'a' },
      ],
    },
    {
      name: 'disconnected',
      nodes: [node('a'), node('b'), node('c'), node('d')],
      edges: [{ source: 'a', target: 'b' }, { source: 'c', target: 'd' }],
    },
    {
      name: 'isolated',
      nodes: [node('solo')],
      edges: [],
    },
    {
      name: 'reverse-pair',
      nodes: [node('a'), node('b')],
      edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'a' }],
    },
  ];
  for (const payload of cases) {
    const parsed = parseTopologyMapPayload(payload);
    assert.equal(parsed.ok, true, payload.name);
    if (!parsed.ok) continue;
    const first = await layoutTopologyMap(parsed.data);
    const second = await layoutTopologyMap(parsed.data);
    assert.deepEqual(first, second, payload.name);
    assert.equal(first.nodes.length, payload.nodes.length, payload.name);
    first.nodes.forEach((item) => {
      assert.equal(
        Number.isFinite(item.x) && Number.isFinite(item.y),
        true,
        `${payload.name}:${item.id}`,
      );
    });
    assert.equal(
      new Set(first.nodes.map((item) => `${item.x}:${item.y}`)).size,
      payload.nodes.length,
      payload.name,
    );
  }
});

test('tree layout forks without requiring root or hop fields', async () => {
  const parsed = parseTopologyMapPayload({
    nodes: [node('root'), node('left'), node('right')],
    edges: [
      { source: 'root', target: 'left' },
      { source: 'root', target: 'right' },
    ],
  });
  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  const layout = await layoutTopologyMap(parsed.data);
  const byId = Object.fromEntries(layout.nodes.map((item) => [item.id, item]));
  assert.ok(byId.root);
  assert.ok(byId.left);
  assert.ok(byId.right);
  assert.notEqual(
    `${byId.left.x}:${byId.left.y}`,
    `${byId.right.x}:${byId.right.y}`,
  );
  assert.equal('hop' in byId.root, false);
  assert.equal('center' in byId.root, false);
});

test('isolated node receives a finite position without edges', async () => {
  const parsed = parseTopologyMapPayload({
    nodes: [node('lonely')],
    edges: [],
  });
  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  const layout = await layoutTopologyMap(parsed.data);
  assert.equal(layout.nodes.length, 1);
  assert.equal(Number.isFinite(layout.nodes[0].x), true);
  assert.equal(Number.isFinite(layout.nodes[0].y), true);
  assert.deepEqual(layout.edges, []);
});
