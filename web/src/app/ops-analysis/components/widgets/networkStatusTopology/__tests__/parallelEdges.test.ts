import assert from 'node:assert/strict';
import test from 'node:test';
import {
  assignParallelOffsets,
  buildParallelConnectorPath,
  buildParallelEdgeVertices,
  getDevicePairKey,
} from '../parallelEdges';

test('getDevicePairKey is order-independent', () => {
  assert.equal(getDevicePairKey('a', 'b'), getDevicePairKey('b', 'a'));
});

test('assignParallelOffsets spreads multiple links symmetrically', () => {
  const withOffset = assignParallelOffsets(
    [
      { id: '1', source: 'a', target: 'b' },
      { id: '2', source: 'b', target: 'a' },
      { id: '3', source: 'a', target: 'b' },
    ],
    16,
  );
  assert.deepEqual(
    withOffset.map((link) => link.parallelOffset),
    [-16, 0, 16],
  );
});

test('assignParallelOffsets keeps single link at zero', () => {
  const withOffset = assignParallelOffsets([
    { id: '1', source: 'a', target: 'b' },
  ]);
  assert.equal(withOffset[0].parallelOffset, 0);
});

test('buildParallelEdgeVertices returns undefined when offset is 0', () => {
  assert.equal(
    buildParallelEdgeVertices({ x: 0, y: 0 }, { x: 100, y: 0 }, 0),
    undefined,
  );
});

test('buildParallelEdgeVertices offsets perpendicular to the segment', () => {
  const vertices = buildParallelEdgeVertices({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
  assert.ok(vertices);
  assert.equal(vertices!.length, 2);
  // 水平线的法向为 (0,1)，偏移应主要在 y
  assert.ok(Math.abs(vertices![0].y - 10) < 1e-6);
  assert.ok(Math.abs(vertices![1].y - 10) < 1e-6);
});

test('buildParallelConnectorPath follows endpoints for drag-safe routing', () => {
  const path = buildParallelConnectorPath({ x: 0, y: 0 }, { x: 100, y: 0 }, 10);
  assert.match(path, /^M 0 0 L /);
  assert.match(path, / L 100 0$/);
});
