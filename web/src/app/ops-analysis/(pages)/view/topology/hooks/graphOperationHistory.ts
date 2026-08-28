/**
 * 拓扑画布操作历史：单步记录、remove 批次合并，以及撤销/重做应用。
 * X6 `removeCells` / `cell.remove()` 会打 `remove` batch，连接边作为副作用一并移除；
 * 这些移除必须合成一个撤销步。
 */
import type { Edge, Graph as X6Graph, Node } from '@antv/x6';
import type { Attr } from '@antv/x6/es/registry/attr';

export const REMOVE_BATCH_NAME = 'remove';

export interface OperationSnapshot extends Record<string, unknown> {
  attrs?: Attr.CellAttrs;
  data?: unknown;
  size?: { width: number; height: number };
  position?: { x: number; y: number };
  vertices?: Array<{ x: number; y: number }>;
}

export interface CellOperation {
  action: 'add' | 'delete' | 'update' | 'move';
  data: {
    before?: OperationSnapshot;
    after?: OperationSnapshot;
  };
  cellType: 'node' | 'edge';
  cellId: string;
}

export interface HistoryEntry {
  operations: CellOperation[];
}

type NodePositionSnapshot = ReturnType<Node['getPosition']>;
type EdgeVerticesSnapshot = ReturnType<Edge['getVertices']>;

export interface GraphOperationHistoryBinding {
  recordOperation: (operation: CellOperation) => void;
  startBatch: () => void;
  stopBatch: () => void;
  onNodeRemoved?: () => void;
}

const addCellFromSnapshot = (
  graph: X6Graph,
  operation: CellOperation,
  snapshot?: OperationSnapshot,
) => {
  if (!snapshot || graph.getCellById(operation.cellId)) return;
  if (operation.cellType === 'node') {
    graph.addNode(snapshot);
    return;
  }
  graph.addEdge(snapshot);
};

const removeCellIfPresent = (graph: X6Graph, cellId: string) => {
  const cell = graph.getCellById(cellId);
  if (cell) {
    graph.removeCell(cell);
  }
};

const applyCellUndo = (graph: X6Graph, operation: CellOperation) => {
  switch (operation.action) {
    case 'add':
      removeCellIfPresent(graph, operation.cellId);
      return;
    case 'delete':
      addCellFromSnapshot(graph, operation, operation.data.before);
      return;
    case 'move': {
      const movedCell = graph.getCellById(operation.cellId);
      if (!movedCell || !operation.data.before) return;
      if (operation.cellType === 'node' && movedCell.isNode()) {
        (movedCell as Node).setPosition(
          operation.data.before.position as { x: number; y: number },
        );
      } else if (
        operation.cellType === 'edge' &&
        movedCell.isEdge() &&
        operation.data.before.vertices
      ) {
        (movedCell as Edge).setVertices(
          operation.data.before.vertices as { x: number; y: number }[],
        );
      }
      return;
    }
    case 'update': {
      const updatedCell = graph.getCellById(operation.cellId);
      if (!updatedCell || !operation.data.before) return;
      if (operation.data.before.attrs) {
        updatedCell.setAttrs(operation.data.before.attrs);
      }
      if (operation.data.before.data) {
        updatedCell.setData(operation.data.before.data);
      }
      if (
        operation.data.before.size &&
        operation.cellType === 'node' &&
        updatedCell.isNode()
      ) {
        (updatedCell as Node).setSize(
          operation.data.before.size as { width: number; height: number },
        );
      }
    }
  }
};

const applyCellRedo = (graph: X6Graph, operation: CellOperation) => {
  switch (operation.action) {
    case 'add':
      addCellFromSnapshot(graph, operation, operation.data.after);
      return;
    case 'delete':
      removeCellIfPresent(graph, operation.cellId);
      return;
    case 'move': {
      const cellToMove = graph.getCellById(operation.cellId);
      if (!cellToMove || !operation.data.after) return;
      if (operation.cellType === 'node' && cellToMove.isNode()) {
        (cellToMove as Node).setPosition(
          operation.data.after.position as { x: number; y: number },
        );
      } else if (
        operation.cellType === 'edge' &&
        cellToMove.isEdge() &&
        operation.data.after.vertices
      ) {
        (cellToMove as Edge).setVertices(
          operation.data.after.vertices as { x: number; y: number }[],
        );
      }
      return;
    }
    case 'update': {
      const cellToUpdate = graph.getCellById(operation.cellId);
      if (!cellToUpdate || !operation.data.after) return;
      if (operation.data.after.attrs) {
        cellToUpdate.setAttrs(operation.data.after.attrs);
      }
      if (operation.data.after.data) {
        cellToUpdate.setData(operation.data.after.data);
      }
      if (
        operation.data.after.size &&
        operation.cellType === 'node' &&
        cellToUpdate.isNode()
      ) {
        (cellToUpdate as Node).setSize(
          operation.data.after.size as { width: number; height: number },
        );
      }
    }
  }
};

const partitionOperations = (operations: CellOperation[]) => {
  const deletes: CellOperation[] = [];
  const others: CellOperation[] = [];
  operations.forEach((operation) => {
    if (operation.action === 'delete') {
      deletes.push(operation);
    } else {
      others.push(operation);
    }
  });
  return { deletes, others };
};

const applyDeleteOperations = (
  operations: CellOperation[],
  apply: (operation: CellOperation) => void,
) => {
  // 节点必须先于边恢复，否则悬空边无法挂上端点；重做删除时先删节点，
  // 连边会作为副作用消失，再删剩余的显式选中边。
  operations
    .filter((operation) => operation.cellType === 'node')
    .forEach(apply);
  operations
    .filter((operation) => operation.cellType === 'edge')
    .forEach(apply);
};

export const undoHistoryEntry = (graph: X6Graph, entry: HistoryEntry) => {
  const { deletes, others } = partitionOperations(entry.operations);
  for (let index = others.length - 1; index >= 0; index -= 1) {
    applyCellUndo(graph, others[index]);
  }
  applyDeleteOperations(deletes, (operation) => applyCellUndo(graph, operation));
};

export const redoHistoryEntry = (graph: X6Graph, entry: HistoryEntry) => {
  const { deletes, others } = partitionOperations(entry.operations);
  others.forEach((operation) => applyCellRedo(graph, operation));
  applyDeleteOperations(deletes, (operation) => applyCellRedo(graph, operation));
};

export const bindGraphOperationHistory = (
  graph: X6Graph,
  {
    recordOperation,
    startBatch,
    stopBatch,
    onNodeRemoved,
  }: GraphOperationHistoryBinding,
) => {
  const handleBatchStart = ({ name }: { name: string }) => {
    if (name === REMOVE_BATCH_NAME) {
      startBatch();
    }
  };

  const handleBatchStop = ({ name }: { name: string }) => {
    if (name === REMOVE_BATCH_NAME) {
      stopBatch();
    }
  };

  const handleNodeAdded = ({ node }: { node: Node }) => {
    recordOperation({
      action: 'add',
      cellType: 'node',
      cellId: node.id,
      data: {
        after: node.toJSON(),
      },
    });
  };

  const handleNodeRemoved = ({ node }: { node: Node }) => {
    recordOperation({
      action: 'delete',
      cellType: 'node',
      cellId: node.id,
      data: {
        before: node.toJSON(),
      },
    });
    onNodeRemoved?.();
  };

  const handleEdgeAdded = ({ edge }: { edge: Edge }) => {
    recordOperation({
      action: 'add',
      cellType: 'edge',
      cellId: edge.id,
      data: {
        after: edge.toJSON(),
      },
    });
  };

  const handleEdgeRemoved = ({ edge }: { edge: Edge }) => {
    recordOperation({
      action: 'delete',
      cellType: 'edge',
      cellId: edge.id,
      data: {
        before: edge.toJSON(),
      },
    });
  };

  const nodePositions = new Map<string, NodePositionSnapshot>();
  const edgeVertices = new Map<string, EdgeVerticesSnapshot>();

  const handleNodeMoveStart = ({ node }: { node: Node }) => {
    nodePositions.set(node.id, node.getPosition());
  };

  const handleNodeMoved = ({ node }: { node: Node }) => {
    const oldPosition = nodePositions.get(node.id);
    if (oldPosition) {
      const newPosition = node.getPosition();
      if (oldPosition.x !== newPosition.x || oldPosition.y !== newPosition.y) {
        recordOperation({
          action: 'move',
          cellType: 'node',
          cellId: node.id,
          data: {
            before: { position: oldPosition },
            after: { position: newPosition },
          },
        });
      }
      nodePositions.delete(node.id);
    }
  };

  const handleEdgeVerticesStart = ({ edge }: { edge: Edge }) => {
    edgeVertices.set(edge.id, edge.getVertices());
  };

  const handleEdgeVerticesChanged = ({ edge }: { edge: Edge }) => {
    const oldVertices = edgeVertices.get(edge.id);
    if (oldVertices) {
      const newVertices = edge.getVertices();
      recordOperation({
        action: 'move',
        cellType: 'edge',
        cellId: edge.id,
        data: {
          before: { vertices: oldVertices },
          after: { vertices: newVertices },
        },
      });
      edgeVertices.delete(edge.id);
    }
  };

  graph.on('batch:start', handleBatchStart);
  graph.on('batch:stop', handleBatchStop);
  graph.on('node:added', handleNodeAdded);
  graph.on('node:removed', handleNodeRemoved);
  graph.on('edge:added', handleEdgeAdded);
  graph.on('edge:removed', handleEdgeRemoved);
  graph.on('node:move', handleNodeMoveStart);
  graph.on('node:moved', handleNodeMoved);
  graph.on('edge:change:vertices', handleEdgeVerticesStart);
  graph.on('edge:change:vertices', handleEdgeVerticesChanged);

  return () => {
    graph.off('batch:start', handleBatchStart);
    graph.off('batch:stop', handleBatchStop);
    graph.off('node:added', handleNodeAdded);
    graph.off('node:removed', handleNodeRemoved);
    graph.off('edge:added', handleEdgeAdded);
    graph.off('edge:removed', handleEdgeRemoved);
    graph.off('node:move', handleNodeMoveStart);
    graph.off('node:moved', handleNodeMoved);
    graph.off('edge:change:vertices', handleEdgeVerticesStart);
    graph.off('edge:change:vertices', handleEdgeVerticesChanged);
    nodePositions.clear();
    edgeVertices.clear();
  };
};
