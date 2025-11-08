/**
 * 图形历史记录管理 Hook
 * 负责撤销/重做功能、操作记录和样式管理
 */
import { useCallback, useState, useRef } from 'react';
import type { Graph as X6Graph, Node, Edge, Cell } from '@antv/x6';
import { COLORS } from '../constants/nodeDefaults';
import { addEdgeTools } from '../utils/topologyUtils';

const OPERATION_HISTORY_LIMIT = 50; // 操作历史记录最大数量
const UNDO_REDO_DEBOUNCE = 50; // 撤销/重做防抖时间（ms）

interface OperationRecord {
  action: 'add' | 'delete' | 'update' | 'move';
  data: {
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
  };
  cellType: 'node' | 'edge';
  cellId: string;
}

export const useGraphHistory = (graphInstance: X6Graph | null) => {
  const isPerformingUndoRedo = useRef(false);
  const isInitializing = useRef(true);

  const [operationHistory, setOperationHistory] = useState<OperationRecord[]>([]);
  const [operationIndex, setOperationIndex] = useState(-1);

  const resetAllStyles = useCallback((graph: X6Graph) => {
    graph.getNodes().forEach((node: Node) => {
      const nodeData = node.getData();
      let borderColor;
      if (nodeData?.type === 'single-value') {
        borderColor = nodeData.styleConfig?.borderColor || 'transparent';
      } else if (nodeData?.type === 'text') {
        borderColor = 'transparent';
      } else {
        borderColor = nodeData.styleConfig?.borderColor || COLORS.BORDER.DEFAULT;
      }
      node.setAttrByPath('body/stroke', borderColor);
      node.setAttrByPath('body/strokeWidth', 1);
    });

    graph.getEdges().forEach((edge: Edge) => {
      const edgeData = edge.getData();
      const customColor = edgeData?.styleConfig?.lineColor;

      edge.setAttrs({
        line: {
          ...edge.getAttrs().line,
          stroke: customColor || COLORS.EDGE.DEFAULT,
        },
      });
    });
  }, []);

  const highlightCell = useCallback((cell: Cell) => {
    if (cell.isNode()) {
      cell.setAttrByPath('body/stroke', '#1890ff');
      cell.setAttrByPath('body/strokeWidth', 2);
    } else if (cell.isEdge()) {
      cell.setAttrs({
        line: {
          ...cell.getAttrs().line,
          stroke: COLORS.EDGE.SELECTED,
          strokeWidth: 1,
        },
      });
      addEdgeTools(cell);
    }
  }, []);

  const highlightNode = useCallback((node: Node) => {
    node.setAttrByPath('body/stroke', '#1890ff');
    node.setAttrByPath('body/strokeWidth', 2);
  }, []);

  const resetNodeStyle = useCallback((node: Node) => {
    const nodeData = node.getData();
    let borderColor;
    if (nodeData?.type === 'single-value') {
      borderColor = nodeData.styleConfig?.borderColor || 'transparent';
    } else if (nodeData?.type === 'text') {
      borderColor = 'transparent';
    } else {
      borderColor = nodeData.styleConfig?.borderColor || COLORS.BORDER.DEFAULT;
    }
    node.setAttrByPath('body/stroke', borderColor);
    node.setAttrByPath('body/strokeWidth', 1);
  }, []);

  const recordOperation = useCallback((operation: OperationRecord) => {
    if (isPerformingUndoRedo.current || isInitializing.current) return;

    setOperationHistory(prev => {
      const newHistory = [...prev.slice(0, operationIndex + 1), operation];
      if (newHistory.length > OPERATION_HISTORY_LIMIT) {
        const trimmedHistory = newHistory.slice(-OPERATION_HISTORY_LIMIT);
        setOperationIndex(trimmedHistory.length - 1);
        return trimmedHistory;
      }
      setOperationIndex(newHistory.length - 1);
      return newHistory;
    });
  }, [operationIndex]);


  const undo = useCallback(() => {
    if (!graphInstance || operationIndex < 0 || isPerformingUndoRedo.current) return;

    const operation = operationHistory[operationIndex];
    if (!operation) return;

    try {
      isPerformingUndoRedo.current = true;

      switch (operation.action) {
        case 'add':
          // 撤销添加：删除节点/边
          const addedCell = graphInstance.getCellById(operation.cellId);
          if (addedCell) {
            graphInstance.removeCell(addedCell);
          }
          break;

        case 'delete':
          // 撤销删除：重新添加节点/边
          if (operation.data.before) {
            if (operation.cellType === 'node') {
              graphInstance.addNode(operation.data.before);
            } else {
              graphInstance.addEdge(operation.data.before);
            }
          }
          break;

        case 'move':
          // 撤销移动：恢复到之前的位置
          const movedCell = graphInstance.getCellById(operation.cellId);
          if (movedCell && operation.data.before) {
            if (operation.cellType === 'node' && movedCell.isNode()) {
              (movedCell as Node).setPosition(operation.data.before.position as { x: number; y: number });
            } else if (operation.cellType === 'edge' && movedCell.isEdge() && operation.data.before.vertices) {
              (movedCell as Edge).setVertices(operation.data.before.vertices as { x: number; y: number }[]);
            }
          }
          break;

        case 'update':
          // 撤销更新：恢复到之前的状态
          const updatedCell = graphInstance.getCellById(operation.cellId);
          if (updatedCell && operation.data.before) {
            if (operation.data.before.attrs) {
              updatedCell.setAttrs(operation.data.before.attrs as any);
            }
            if (operation.data.before.data) {
              updatedCell.setData(operation.data.before.data);
            }
            if (operation.data.before.size && operation.cellType === 'node' && updatedCell.isNode()) {
              (updatedCell as Node).setSize(operation.data.before.size as { width: number; height: number });
            }
          }
          break;
      }

      setOperationIndex(prev => prev - 1);
      setTimeout(() => {
        isPerformingUndoRedo.current = false;
      }, UNDO_REDO_DEBOUNCE);
    } catch (error) {
      console.error('撤销失败:', error);
      isPerformingUndoRedo.current = false;
    }
  }, [graphInstance, operationHistory, operationIndex]);

  const redo = useCallback(() => {
    if (!graphInstance || operationIndex >= operationHistory.length - 1 || isPerformingUndoRedo.current) return;

    const operation = operationHistory[operationIndex + 1];
    if (!operation) return;

    try {
      isPerformingUndoRedo.current = true;

      switch (operation.action) {
        case 'add':
          // 重做添加：添加节点/边
          if (operation.data.after) {
            if (operation.cellType === 'node') {
              graphInstance.addNode(operation.data.after);
            } else {
              graphInstance.addEdge(operation.data.after);
            }
          }
          break;

        case 'delete':
          // 重做删除：删除节点/边
          const cellToDelete = graphInstance.getCellById(operation.cellId);
          if (cellToDelete) {
            graphInstance.removeCell(cellToDelete);
          }
          break;

        case 'move':
          // 重做移动：移动到新位置
          const cellToMove = graphInstance.getCellById(operation.cellId);
          if (cellToMove && operation.data.after) {
            if (operation.cellType === 'node' && cellToMove.isNode()) {
              (cellToMove as Node).setPosition(operation.data.after.position as { x: number; y: number });
            } else if (operation.cellType === 'edge' && cellToMove.isEdge() && operation.data.after.vertices) {
              (cellToMove as Edge).setVertices(operation.data.after.vertices as { x: number; y: number }[]);
            }
          }
          break;

        case 'update':
          // 重做更新：应用新的状态
          const cellToUpdate = graphInstance.getCellById(operation.cellId);
          if (cellToUpdate && operation.data.after) {
            if (operation.data.after.attrs) {
              cellToUpdate.setAttrs(operation.data.after.attrs as any);
            }
            if (operation.data.after.data) {
              cellToUpdate.setData(operation.data.after.data);
            }
            if (operation.data.after.size && operation.cellType === 'node' && cellToUpdate.isNode()) {
              (cellToUpdate as Node).setSize(operation.data.after.size as { width: number; height: number });
            }
          }
          break;
      }

      setOperationIndex(prev => prev + 1);
      setTimeout(() => {
        isPerformingUndoRedo.current = false;
      }, UNDO_REDO_DEBOUNCE);
    } catch (error) {
      console.error('重做失败:', error);
      isPerformingUndoRedo.current = false;
    }
  }, [graphInstance, operationHistory, operationIndex]);

  const clearOperationHistory = useCallback(() => {
    setOperationHistory([]);
    setOperationIndex(-1);
  }, []);

  const startInitialization = useCallback(() => {
    isInitializing.current = true;
  }, []);

  const finishInitialization = useCallback(() => {
    isInitializing.current = false;
  }, []);

  const canUndo = operationIndex >= 0 && operationIndex < operationHistory.length;
  const canRedo = operationIndex >= -1 && operationIndex < operationHistory.length - 1;

  return {
    // 样式管理
    resetAllStyles,
    highlightCell,
    highlightNode,
    resetNodeStyle,

    // 操作记录
    recordOperation,

    // 撤销/重做
    undo,
    redo,
    canUndo,
    canRedo,

    // 历史管理
    clearOperationHistory,
    startInitialization,
    finishInitialization,

    // 内部状态（供外部监听事件使用）
    isPerformingUndoRedo,
  };
};
