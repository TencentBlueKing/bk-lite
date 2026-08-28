/**
 * 图形历史记录管理 Hook
 * 负责撤销/重做功能、操作记录和样式管理
 */
import { useCallback, useState, useRef } from 'react';
import type { Graph as X6Graph, Node, Edge, Cell } from '@antv/x6';
import { COLORS } from '../constants/nodeDefaults';
import { addEdgeTools } from '../utils/topologyUtils';
import {
  highlightTopologyNode,
  resetTopologyNodeChrome,
} from '../utils/topologySelectionChrome';
import type { CellOperation, HistoryEntry } from './graphOperationHistory';
import {
  redoHistoryEntry,
  undoHistoryEntry,
} from './graphOperationHistory';

const OPERATION_HISTORY_LIMIT = 50; // 操作历史记录最大数量
const UNDO_REDO_DEBOUNCE = 50; // 撤销/重做防抖时间（ms）

export type { CellOperation as OperationRecord, HistoryEntry };

export const useGraphHistory = (graphInstance: X6Graph | null) => {
  const isPerformingUndoRedo = useRef(false);
  const isInitializing = useRef(true);
  const operationIndexRef = useRef(-1);
  const batchDepthRef = useRef(0);
  const pendingBatchRef = useRef<CellOperation[]>([]);

  const [operationHistory, setOperationHistory] = useState<HistoryEntry[]>([]);
  const [operationIndex, setOperationIndex] = useState(-1);

  const resetAllStyles = useCallback((graph: X6Graph) => {
    graph.getNodes().forEach((node: Node) => {
      resetTopologyNodeChrome(node);
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
      highlightTopologyNode(cell);
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
    highlightTopologyNode(node);
  }, []);

  const resetNodeStyle = useCallback((node: Node) => {
    resetTopologyNodeChrome(node);
  }, []);

  const commitEntry = useCallback((operations: CellOperation[]) => {
    if (operations.length === 0) return;

    setOperationHistory(prev => {
      const newHistory = [
        ...prev.slice(0, operationIndexRef.current + 1),
        { operations },
      ];
      const trimmedHistory =
        newHistory.length > OPERATION_HISTORY_LIMIT
          ? newHistory.slice(-OPERATION_HISTORY_LIMIT)
          : newHistory;
      const nextIndex = trimmedHistory.length - 1;
      operationIndexRef.current = nextIndex;
      setOperationIndex(nextIndex);
      return trimmedHistory;
    });
  }, []);

  const startBatch = useCallback(() => {
    batchDepthRef.current += 1;
  }, []);

  const stopBatch = useCallback(() => {
    if (batchDepthRef.current === 0) return;
    batchDepthRef.current -= 1;
    if (batchDepthRef.current === 0) {
      const operations = pendingBatchRef.current;
      pendingBatchRef.current = [];
      commitEntry(operations);
    }
  }, [commitEntry]);

  const recordOperation = useCallback((operation: CellOperation) => {
    if (isPerformingUndoRedo.current || isInitializing.current) return;

    if (batchDepthRef.current > 0) {
      pendingBatchRef.current.push(operation);
      return;
    }

    commitEntry([operation]);
  }, [commitEntry]);

  const undo = useCallback(() => {
    if (!graphInstance || operationIndex < 0 || isPerformingUndoRedo.current) return;

    const entry = operationHistory[operationIndex];
    if (!entry) return;

    try {
      isPerformingUndoRedo.current = true;
      undoHistoryEntry(graphInstance, entry);

      const nextIndex = operationIndex - 1;
      operationIndexRef.current = nextIndex;
      setOperationIndex(nextIndex);
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

    const entry = operationHistory[operationIndex + 1];
    if (!entry) return;

    try {
      isPerformingUndoRedo.current = true;
      redoHistoryEntry(graphInstance, entry);

      const nextIndex = operationIndex + 1;
      operationIndexRef.current = nextIndex;
      setOperationIndex(nextIndex);
      setTimeout(() => {
        isPerformingUndoRedo.current = false;
      }, UNDO_REDO_DEBOUNCE);
    } catch (error) {
      console.error('重做失败:', error);
      isPerformingUndoRedo.current = false;
    }
  }, [graphInstance, operationHistory, operationIndex]);

  const clearOperationHistory = useCallback(() => {
    pendingBatchRef.current = [];
    batchDepthRef.current = 0;
    operationIndexRef.current = -1;
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
    startBatch,
    stopBatch,

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
