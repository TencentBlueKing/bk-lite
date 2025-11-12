import { useState, useRef, useCallback } from 'react';
import type { Graph, Edge } from '@antv/x6';
import {
  EdgeData,
  GraphState,
  ContextMenuState,
  EdgeConfigState,
  NodeEditState,
  TopologyNodeData,
} from '@/app/ops-analysis/types/topology';

export const useTopologyState = () => {
  // 图形核心状态
  const [graphState, setGraphState] = useState<GraphState>({
    instance: null,
    scale: 1,
    selectedCells: [],
    isSelectMode: true,
    isEditMode: false,
    collapsed: true,
  });

  // 右键菜单状态
  const [contextMenuState, setContextMenuState] = useState<ContextMenuState>({
    nodeId: '',
    visible: false,
    position: { x: 0, y: 0 },
    targetType: 'node',
  });

  // 边配置状态
  const [edgeConfigState, setEdgeConfigState] = useState<EdgeConfigState>({
    visible: false,
    data: null,
  });

  // 节点编辑状态
  const [nodeEditState, setNodeEditState] = useState<NodeEditState>({
    visible: false,
    data: null,
  });

  // 视图配置状态
  const [viewConfigVisible, setViewConfigVisible] = useState(false);

  // Refs
  const isDrawingRef = useRef(false);
  const drawingEdgeRef = useRef<Edge | null>(null);
  const isEditModeRef = useRef(graphState.isEditMode);

  // 状态更新助手函数
  const updateGraphState = useCallback((updates: Partial<GraphState>) => {
    setGraphState(prev => ({ ...prev, ...updates }));
  }, []);

  const updateContextMenuState = useCallback((updates: Partial<ContextMenuState>) => {
    setContextMenuState(prev => ({ ...prev, ...updates }));
  }, []);

  const updateEdgeConfigState = useCallback((updates: Partial<EdgeConfigState>) => {
    setEdgeConfigState(prev => ({ ...prev, ...updates }));
  }, []);

  const updateNodeEditState = useCallback((updates: Partial<NodeEditState>) => {
    setNodeEditState(prev => ({ ...prev, ...updates }));
  }, []);

  // 更新绘制状态
  const updateDrawingState = useCallback((drawing: boolean) => {
    isDrawingRef.current = drawing;
  }, []);

  const resetAllStates = useCallback(() => {
    // 重置图形状态
    updateGraphState({
      isEditMode: false,
      isSelectMode: true,
      selectedCells: [],
    });
    isEditModeRef.current = false;

    // 重置右键菜单状态
    updateContextMenuState({
      visible: false,
      nodeId: '',
      position: { x: 0, y: 0 },
    });

    // 重置边配置状态
    updateEdgeConfigState({
      visible: false,
      data: null,
    });

    // 重置节点编辑状态
    updateNodeEditState({
      visible: false,
      data: null,
    });
    setViewConfigVisible(false);

    // 重置绘制状态
    isDrawingRef.current = false;
    drawingEdgeRef.current = null;

    // 清理图形选择状态
    if (graphState.instance) {
      graphState.instance.disablePlugins(['selection']);
      graphState.instance.cleanSelection();
    }
  }, [graphState.instance, updateGraphState, updateContextMenuState, updateEdgeConfigState, updateNodeEditState]);

  return {
    // 图形相关状态和操作
    graphInstance: graphState.instance,
    setGraphInstance: (instance: Graph | null) => updateGraphState({ instance }),
    scale: graphState.scale,
    setScale: (scale: number) => updateGraphState({ scale }),
    selectedCells: graphState.selectedCells,
    setSelectedCells: (cells: string[]) => updateGraphState({ selectedCells: cells }),
    isSelectMode: graphState.isSelectMode,
    setIsSelectMode: (mode: boolean) => updateGraphState({ isSelectMode: mode }),
    isEditMode: graphState.isEditMode,
    setIsEditMode: (mode: boolean) => {
      updateGraphState({ isEditMode: mode });
      isEditModeRef.current = mode;
    },
    collapsed: graphState.collapsed,
    setCollapsed: (collapsed: boolean) => updateGraphState({ collapsed }),

    // 右键菜单状态和操作
    contextMenuNodeId: contextMenuState.nodeId,
    setContextMenuNodeId: (nodeId: string) => updateContextMenuState({ nodeId }),
    contextMenuVisible: contextMenuState.visible,
    setContextMenuVisible: (visible: boolean) => updateContextMenuState({ visible }),
    contextMenuPosition: contextMenuState.position,
    setContextMenuPosition: (position: { x: number; y: number }) => updateContextMenuState({ position }),
    contextMenuTargetType: contextMenuState.targetType,
    setContextMenuTargetType: (targetType: 'node' | 'edge') => updateContextMenuState({ targetType }),

    // 边配置状态和操作
    edgeConfigVisible: edgeConfigState.visible,
    setEdgeConfigVisible: (visible: boolean) => updateEdgeConfigState({ visible }),
    currentEdgeData: edgeConfigState.data,
    setCurrentEdgeData: (data: EdgeData | null) => updateEdgeConfigState({ data }),

    // 节点编辑状态和操作
    nodeEditVisible: nodeEditState.visible,
    setNodeEditVisible: (visible: boolean) => updateNodeEditState({ visible }),
    editingNodeData: nodeEditState.data,
    setEditingNodeData: (data: TopologyNodeData | null) => updateNodeEditState({ data }),

    // 视图配置状态
    viewConfigVisible,
    setViewConfigVisible,

    // 工具函数
    resetAllStates,

    // Refs
    isDrawingRef,
    drawingEdgeRef,
    isEditModeRef,
    updateDrawingState,
  };
};
