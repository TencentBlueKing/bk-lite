// @vitest-environment jsdom

import './x6JsdomPolyfill';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Graph } from '@antv/x6';
import { bindGraphOperationHistory } from '../graphOperationHistory';
import { useGraphHistory } from '../useGraphHistory';

const UNDO_REDO_DEBOUNCE_MS = 60;

const waitForUndoRedoUnlock = async () => {
  await act(async () => {
    await new Promise((resolve) => {
      setTimeout(resolve, UNDO_REDO_DEBOUNCE_MS);
    });
  });
};

const cellIds = (graph: Graph) => ({
  nodes: graph.getNodes().map((node) => node.id).sort(),
  edges: graph.getEdges().map((edge) => edge.id).sort(),
});

describe('topology batch delete undo granularity', () => {
  let graph: Graph;
  let container: HTMLDivElement;
  let unbindHistory: (() => void) | undefined;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    graph = new Graph({
      container,
      width: 800,
      height: 600,
    });
  });

  afterEach(() => {
    unbindHistory?.();
    unbindHistory = undefined;
    graph.dispose();
    container.remove();
  });

  const mountHistory = () => {
    const hook = renderHook(() => useGraphHistory(graph));
    unbindHistory = bindGraphOperationHistory(graph, {
      recordOperation: (operation) => hook.result.current.recordOperation(operation),
      startBatch: () => hook.result.current.startBatch(),
      stopBatch: () => hook.result.current.stopBatch(),
    });
    return hook;
  };

  const seedThreeNodesWithEdge = () => {
    const nodeA = graph.addNode({ id: 'node-a', x: 40, y: 40, width: 80, height: 40 });
    const nodeB = graph.addNode({ id: 'node-b', x: 200, y: 40, width: 80, height: 40 });
    const nodeC = graph.addNode({ id: 'node-c', x: 360, y: 40, width: 80, height: 40 });
    const edgeAB = graph.addEdge({ id: 'edge-ab', source: 'node-a', target: 'node-b' });
    return { nodeA, nodeB, nodeC, edgeAB };
  };

  it('restores a 3-node delete and its incident edge with one undo, then removes them again with one redo', async () => {
    const { result } = mountHistory();
    const { nodeA, nodeB, nodeC } = seedThreeNodesWithEdge();

    act(() => {
      result.current.finishInitialization();
    });

    act(() => {
      graph.removeCells([nodeA, nodeB, nodeC]);
    });

    expect(cellIds(graph)).toEqual({ nodes: [], edges: [] });
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(false);

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(true);

    await waitForUndoRedoUnlock();

    act(() => {
      result.current.redo();
    });

    expect(cellIds(graph)).toEqual({ nodes: [], edges: [] });
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(false);
  });

  it('does not require N undos for N deleted nodes', async () => {
    const { result } = mountHistory();
    const { nodeA, nodeB, nodeC } = seedThreeNodesWithEdge();

    act(() => {
      result.current.finishInitialization();
    });

    act(() => {
      graph.removeCells([nodeA, nodeB, nodeC]);
    });

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });

    await waitForUndoRedoUnlock();

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });
  });

  it('still undoes a single-node delete as one step, including its incident edge', async () => {
    const { result } = mountHistory();
    const { nodeA } = seedThreeNodesWithEdge();

    act(() => {
      result.current.finishInitialization();
    });

    act(() => {
      graph.removeCells([nodeA]);
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-b', 'node-c'],
      edges: [],
    });

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });

    await waitForUndoRedoUnlock();

    act(() => {
      result.current.redo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-b', 'node-c'],
      edges: [],
    });
  });

  it('restores a context-menu style single cell.remove with its incident edge in one undo', async () => {
    const { result } = mountHistory();
    const { nodeA } = seedThreeNodesWithEdge();

    act(() => {
      result.current.finishInitialization();
    });

    act(() => {
      nodeA.remove();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-b', 'node-c'],
      edges: [],
    });

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });
  });

  it('keeps sequential deletes as separate undo steps', async () => {
    const { result } = mountHistory();
    const { nodeA, nodeC } = seedThreeNodesWithEdge();

    act(() => {
      result.current.finishInitialization();
    });

    act(() => {
      graph.removeCells([nodeC]);
    });
    act(() => {
      graph.removeCells([nodeA]);
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-b'],
      edges: [],
    });

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph).nodes).toEqual(['node-a', 'node-b']);
    expect(cellIds(graph).edges).toEqual(['edge-ab']);

    await waitForUndoRedoUnlock();

    act(() => {
      result.current.undo();
    });

    expect(cellIds(graph)).toEqual({
      nodes: ['node-a', 'node-b', 'node-c'],
      edges: ['edge-ab'],
    });
  });
});

describe('bindGraphOperationHistory remove batching', () => {
  it('coalesces node and side-effect edge removals inside one X6 remove batch', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const graph = new Graph({ container, width: 400, height: 300 });

    const recorded: Array<{ action: string; cellId: string }> = [];
    const startBatch = vi.fn();
    const stopBatch = vi.fn();

    const unbind = bindGraphOperationHistory(graph, {
      recordOperation: (operation) => {
        recorded.push({ action: operation.action, cellId: operation.cellId });
      },
      startBatch,
      stopBatch,
    });

    const nodeA = graph.addNode({ id: 'a', x: 10, y: 10, width: 40, height: 20 });
    const nodeB = graph.addNode({ id: 'b', x: 80, y: 10, width: 40, height: 20 });
    graph.addEdge({ id: 'ab', source: 'a', target: 'b' });
    recorded.length = 0;
    startBatch.mockClear();
    stopBatch.mockClear();

    graph.removeCells([nodeA, nodeB]);

    expect(recorded.map((item) => item.cellId).sort()).toEqual(['a', 'ab', 'b']);
    expect(recorded.every((item) => item.action === 'delete')).toBe(true);
    expect(startBatch).toHaveBeenCalled();
    expect(stopBatch).toHaveBeenCalled();
    expect(startBatch.mock.calls.length).toBe(stopBatch.mock.calls.length);

    unbind();
    graph.dispose();
    container.remove();
  });
});
