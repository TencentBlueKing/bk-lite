/**
 * 拓扑图操作管理 facade，组合图初始化、历史记录、节点数据操作和基础视口命令。
 */
import { useCallback, useEffect, useRef } from 'react';
import { hideAllEdgeTools, hideAllPorts } from '../utils/topologyUtils';
import { useGraphHistory } from './useGraphHistory';
import { useGraphInitializer } from './useGraphInitializer';
import { useGraphNodeOperations } from './useGraphNodeOperations';

export const useGraphOperations = (
  containerRef: React.RefObject<HTMLDivElement | null>,
  state: ReturnType<typeof import('./useTopologyState').useTopologyState>,
  minimapContainerRef?: React.RefObject<HTMLDivElement | null>,
  onNodeRemoved?: () => void,
  isZoomLocked = false,
) => {
  const isZoomLockedRef = useRef(isZoomLocked);

  useEffect(() => {
    isZoomLockedRef.current = isZoomLocked;
  }, [isZoomLocked]);

  const {
    graphInstance,
    scale,
    selectedCells,
    setSelectedCells,
    setIsEditMode,
    isEditModeRef,
    setContextMenuVisible,
  } = state;

  const history = useGraphHistory(graphInstance);
  const {
    undo,
    redo,
    canUndo,
    canRedo,
    clearOperationHistory,
    startInitialization,
    finishInitialization,
  } = history;

  const handleSave = useCallback(() => {
    setIsEditMode(false);
    isEditModeRef.current = false;

    if (graphInstance) {
      graphInstance.disablePlugins(['selection']);
      hideAllPorts(graphInstance);
      hideAllEdgeTools(graphInstance);

      setContextMenuVisible(false);
      graphInstance.cleanSelection();
      setSelectedCells([]);
    }
  }, [
    graphInstance,
    isEditModeRef,
    setContextMenuVisible,
    setIsEditMode,
    setSelectedCells,
  ]);

  const nodeOperations = useGraphNodeOperations({
    graphInstance,
    state,
    handleSave,
  });

  useGraphInitializer({
    containerRef,
    minimapContainerRef,
    state,
    history,
    selectedCells,
    onNodeRemoved,
    isZoomLockedRef,
  });

  const zoomIn = useCallback(() => {
    if (isZoomLockedRef.current) {
      return;
    }

    if (graphInstance) {
      const next = scale + 0.1;
      graphInstance.zoom(next, { absolute: true });
    }
  }, [graphInstance, scale]);

  const zoomOut = useCallback(() => {
    if (isZoomLockedRef.current) {
      return;
    }

    if (graphInstance) {
      const next = scale - 0.1 > 0.1 ? scale - 0.1 : 0.1;
      graphInstance.zoom(next, { absolute: true });
    }
  }, [graphInstance, scale]);

  const handleFit = useCallback(() => {
    if (isZoomLockedRef.current) {
      return;
    }

    if (graphInstance && containerRef.current) {
      graphInstance.zoomToFit({ padding: 20, maxScale: 1 });
    }
  }, [containerRef, graphInstance]);

  const handleDelete = useCallback(() => {
    if (graphInstance && selectedCells.length > 0) {
      graphInstance.removeCells(selectedCells);
      setSelectedCells([]);
    }
  }, [graphInstance, selectedCells, setSelectedCells]);

  const handleSelectMode = useCallback(() => {
    if (graphInstance) {
      graphInstance.enableSelection();
    }
  }, [graphInstance]);

  const resizeCanvas = useCallback(
    (width?: number, height?: number) => {
      if (!graphInstance) return;
      if (width && height) {
        graphInstance.resize(width, height);
      } else {
        graphInstance.resize();
      }
    },
    [graphInstance],
  );

  const toggleEditMode = useCallback(() => {
    const newEditMode = !state.isEditMode;
    state.setIsEditMode(newEditMode);
    state.isEditModeRef.current = newEditMode;

    if (graphInstance) {
      if (newEditMode) {
        graphInstance.enablePlugins(['selection']);
      } else {
        graphInstance.disablePlugins(['selection']);
      }
    }
  }, [state, graphInstance]);

  return {
    zoomIn,
    zoomOut,
    handleFit,
    handleDelete,
    handleSelectMode,
    handleSave,
    addNewNode: nodeOperations.addNewNode,
    handleNodeUpdate: nodeOperations.handleNodeUpdate,
    handleViewConfigConfirm: nodeOperations.handleViewConfigConfirm,
    handleAddChartNode: nodeOperations.handleAddChartNode,
    resizeCanvas,
    toggleEditMode,
    handleNodeEditClose: nodeOperations.handleNodeEditClose,
    undo,
    redo,
    canUndo,
    canRedo,
    finishInitialization,
    startInitialization,
    clearOperationHistory,
    refreshAllSingleValueNodes: nodeOperations.refreshAllSingleValueNodes,
    updateSingleNodeData: nodeOperations.updateSingleNodeData,
    loading: nodeOperations.loading,
    setLoading: nodeOperations.setLoading,
    handleSaveTopology: nodeOperations.handleSaveTopology,
    handleLoadTopology: nodeOperations.handleLoadTopology,
    loadChartNodeData: nodeOperations.loadChartNodeData,
    refreshAllChartNodes: nodeOperations.refreshAllChartNodes,
  };
};
