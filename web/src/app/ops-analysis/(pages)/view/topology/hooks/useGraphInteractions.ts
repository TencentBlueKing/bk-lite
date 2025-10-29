/**
 * 拓扑图交互功能管理 Hook，专注于处理用户交互操作和模态框管理
 */
import type { Edge, Node, Cell } from '@antv/x6';
import { useCallback } from 'react';
import { message } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import { useTranslation } from '@/utils/i18n';
import { COLORS } from '../constants/nodeDefaults';
import { createEdgeLabel, getEdgeStyleWithConfig } from '../utils/topologyUtils';
import { createEdgeByType } from '../utils/registerEdge';
import {
  TopologyState,
  MenuClickEvent,
  UseContextMenuAndModalReturn,
  Point,
} from '@/app/ops-analysis/types/topology';

const removeAllEdgeLabels = (edge: Edge) => {
  const labels = edge.getLabels();
  if (labels?.length) {
    for (let i = labels.length - 1; i >= 0; i--) {
      edge.removeLabelAt(i);
    }
  }
};

export const useContextMenuAndModal = (
  containerRef: React.RefObject<HTMLDivElement>,
  state: TopologyState
): UseContextMenuAndModalReturn => {
  const { t } = useTranslation();
  const {
    graphInstance,
    contextMenuNodeId,
    setContextMenuVisible,
    isEditMode,
    currentEdgeData,
    setCurrentEdgeData,
    isDrawingRef,
    drawingEdgeRef,
    updateDrawingState,
  } = state;

  const handleEdgeConfigConfirm = useCallback(
    (values: {
      lineType: 'common_line' | 'network_line';
      lineName?: string;
      styleConfig?: {
        lineColor?: string;
        lineWidth?: number;
        lineStyle?: 'line' | 'dotted' | 'point';
        enableAnimation?: boolean;
      }
    }) => {
      if (!currentEdgeData?.id || !graphInstance) return;

      const edge = graphInstance.getCellById(currentEdgeData.id) as Edge;
      if (!edge) return;

      const currentVertices = edge.getVertices();

      edge.setData({
        ...edge.getData(),
        lineType: values.lineType,
        lineName: values.lineName,
        styleConfig: values.styleConfig,
        vertices: currentVertices
      });

      if (values.styleConfig) {
        const lineAttrs: any = {
          ...edge.getAttrs().line,
        };

        if (values.styleConfig.lineColor) {
          lineAttrs.stroke = values.styleConfig.lineColor;
        }

        if (values.styleConfig.lineWidth) {
          lineAttrs.strokeWidth = values.styleConfig.lineWidth;
        }

        if (values.styleConfig.lineStyle === 'dotted') {
          lineAttrs.strokeDasharray = '3 3';
        } else if (values.styleConfig.lineStyle === 'point') {
          lineAttrs.strokeDasharray = '1 3';
        } else if (values.styleConfig.lineStyle === 'line') {
          lineAttrs.strokeDasharray = null;
        }

        const arrowDirection = currentEdgeData.arrowDirection || 'single';
        if (
          arrowDirection === 'single' &&
          values.styleConfig.enableAnimation &&
          (values.styleConfig.lineStyle === 'dotted' || values.styleConfig.lineStyle === 'point')
        ) {
          lineAttrs.class = 'edge-flow-animation';
        } else {
          lineAttrs.class = null;
        }

        edge.setAttrs({ line: lineAttrs });
      }

      if (values.lineType === 'network_line') {
        removeAllEdgeLabels(edge);
      } else if (values.lineType === 'common_line') {
        if (values.lineName?.trim()) {
          edge.setLabels([createEdgeLabel(values.lineName)]);
        } else {
          removeAllEdgeLabels(edge);
        }
      }

      setCurrentEdgeData({
        ...currentEdgeData,
        lineType: values.lineType,
        lineName: values.lineName,
        styleConfig: values.styleConfig
      });
    },
    [currentEdgeData, graphInstance, setCurrentEdgeData]
  );

  const closeEdgeConfig = useCallback(() => {
    state.setEdgeConfigVisible(false);
    setCurrentEdgeData(null);
  }, [setCurrentEdgeData, state]);

  const handleEdgeConfiguration = useCallback(
    (selectedCell: Cell) => {
      if (!selectedCell.isEdge()) return;

      const edge = selectedCell as Edge;
      const edgeData = edge.getData();
      const sourceNode = edge.getSourceNode();
      const targetNode = edge.getTargetNode();

      if (edgeData && sourceNode && targetNode) {
        const sourceNodeData = sourceNode.getData();
        const targetNodeData = targetNode.getData();

        setCurrentEdgeData({
          id: edge.id,
          lineType: edgeData.lineType || 'common_line',
          lineName: edgeData.lineName || '',
          arrowDirection: edgeData.arrowDirection,
          styleConfig: edgeData.styleConfig || { lineColor: COLORS.EDGE.DEFAULT, },
          sourceNode: {
            id: sourceNode.id,
            name: sourceNodeData?.name || sourceNode.id,
          },
          targetNode: {
            id: targetNode.id,
            name: targetNodeData?.name || targetNode.id,
          },
          sourceInterface: edgeData.sourceInterface,
          targetInterface: edgeData.targetInterface,
        });
        state.setEdgeConfigVisible(true);
      }
    },
    [setCurrentEdgeData, state]
  );

  const handleViewModeMenuClick = useCallback(
    (key: string, sourceNode: any) => {
      const nodeName = sourceNode.getAttrs()?.label?.text || sourceNode.id;

      if (key === 'viewAlarms') {
        console.log('查看告警列表:', nodeName);
      } else if (key === 'viewMonitor') {
        console.log('查看监控详情:', nodeName);
      }
    },
    []
  );

  const handleNodeLayerOperation = useCallback(
    (key: string, targetNode: Cell) => {
      if (!graphInstance) return false;

      const currentZIndex = targetNode.getZIndex() || 0;
      const cells = graphInstance.getCells();
      let newZIndex = currentZIndex;

      if (key === 'bringToFront') {
        targetNode.toFront();
        newZIndex = targetNode.getZIndex() || 0;
        message.success(t('topology.layerMessages.bringToFrontSuccess'));
      } else if (key === 'bringToBack') {
        targetNode.toBack();
        newZIndex = targetNode.getZIndex() || 0;
        message.success(t('topology.layerMessages.bringToBackSuccess'));
      } else if (key === 'bringForward') {
        const maxZIndex = Math.max(...cells.map(cell => cell.getZIndex() || 0));

        if (currentZIndex < maxZIndex) {
          newZIndex = currentZIndex + 1;
          targetNode.setZIndex(newZIndex);
          message.success(t('topology.layerMessages.bringForwardSuccess').replace('{zIndex}', String(newZIndex)));
        } else {
          message.info(t('topology.layerMessages.alreadyTop'));
          return true;
        }
      } else if (key === 'sendBackward') {
        const minZIndex = Math.min(...cells.map(cell => cell.getZIndex() || 0));

        if (currentZIndex > minZIndex && currentZIndex > 0) {
          newZIndex = Math.max(0, currentZIndex - 1);
          targetNode.setZIndex(newZIndex);
          message.success(t('topology.layerMessages.sendBackwardSuccess').replace('{zIndex}', String(newZIndex)));
        } else {
          message.info(t('topology.layerMessages.alreadyBottom'));
          return true;
        }
      } else {
        return false;
      }

      if (targetNode.isNode()) {
        const nodeData = targetNode.getData() || {};
        targetNode.setData({
          ...nodeData,
          zIndex: newZIndex
        });
      }

      return true;
    },
    [graphInstance]
  );

  const handleNodeEdit = useCallback(
    (selectedCell: Cell) => {
      if (!selectedCell.isNode()) return;

      const clickedNodeData = selectedCell.getData();

      if (clickedNodeData?.type === 'chart') {
        const chartNodeData = {
          ...clickedNodeData,
          id: selectedCell.id,
          label: selectedCell.prop('label'),
        };
        state.setEditingNodeData(chartNodeData);
        state.setViewConfigVisible(true);
      } else {
        const nodeWidth = clickedNodeData.styleConfig?.width;
        const nodeHeight = clickedNodeData.styleConfig?.height;
        state.setEditingNodeData({
          ...clickedNodeData,
          id: selectedCell.id,
          label: selectedCell.prop('label'),
          width: nodeWidth,
          height: nodeHeight,
        });
        state.setNodeEditVisible(true);
      }
    },
    [state]
  );

  const handleNodeCopy = useCallback(
    (selectedCell: Cell) => {
      if (!selectedCell.isNode() || !graphInstance) return;

      try {
        const originalNodeData = selectedCell.getData();
        const originalPosition = selectedCell.getPosition();
        const originalSize = selectedCell.getSize();
        const originalAttrs = selectedCell.getAttrs();

        const newNodeId = `node_${uuidv4()}`;
        const newPosition = {
          x: originalPosition.x + 200,
          y: originalPosition.y,
        };

        const newNodeData = {
          ...originalNodeData,
          id: newNodeId,
        };

        const newNode = graphInstance.addNode({
          id: newNodeId,
          shape: selectedCell.shape,
          x: newPosition.x,
          y: newPosition.y,
          width: originalSize.width,
          height: originalSize.height,
          attrs: { ...originalAttrs },
          data: newNodeData,
          zIndex: selectedCell.getZIndex(),
        });

        message.success(t('topology.nodeCopySuccess'));

        if (state.isEditMode) {
          setTimeout(() => {
            graphInstance.select(newNode);
          }, 100);
        }
      } catch {
        message.error(t('topology.nodeCopyFailed'));
      }
    },
    [graphInstance, state.isEditMode, t]
  );

  const handleConnectionDrawing = useCallback(
    (connectionType: 'none' | 'single' | 'double') => {
      if (!graphInstance || !contextMenuNodeId) return;

      const sourceNode = graphInstance.getCellById(contextMenuNodeId);
      if (!sourceNode) return;

      const getCurrentMousePosition = (e: MouseEvent): Point => {
        if (!graphInstance) throw new Error('Graph instance is null');
        return graphInstance.clientToLocal(e.clientX, e.clientY);
      };

      let tempEdge: Edge | null = null;

      const cleanup = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.removeEventListener('keydown', onKeyDown);

        tempEdge?.remove();
        updateDrawingState(false);
        drawingEdgeRef.current = null;
        tempEdge = null;
      };

      const onKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && tempEdge && isDrawingRef.current) {
          e.preventDefault();
          e.stopPropagation();
          cleanup();
        }
      };

      const onMouseMove = (e: MouseEvent) => {
        if (!graphInstance) return;

        const currentPoint = getCurrentMousePosition(e);

        if (!tempEdge) {
          // 临时边的默认样式配置
          const tempEdgeStyleConfig = {
            lineColor: COLORS.EDGE.DEFAULT,
            lineWidth: 1,
            lineStyle: 'line' as const,
            enableAnimation: false,
          };

          tempEdge = graphInstance.addEdge({
            source: { cell: contextMenuNodeId },
            target: currentPoint,
            ...getEdgeStyleWithConfig(connectionType, tempEdgeStyleConfig),
            data: { connectionType, isTemporary: true },
            zIndex: 1000,
          });
          drawingEdgeRef.current = tempEdge;
          updateDrawingState(true);
        } else {
          tempEdge.setTarget(currentPoint);
        }
      };

      const onMouseUp = (e: MouseEvent) => {
        if (!tempEdge || !isDrawingRef.current || !graphInstance || !contextMenuNodeId) {
          return;
        }

        cleanup();

        const localPoint = getCurrentMousePosition(e);

        let targetCell: Node | null = null;
        for (const node of graphInstance.getNodes()) {
          if (node.id === contextMenuNodeId) continue;

          const bbox = node.getBBox();
          if (
            localPoint.x >= bbox.x &&
            localPoint.x <= bbox.x + bbox.width &&
            localPoint.y >= bbox.y &&
            localPoint.y <= bbox.y + bbox.height
          ) {
            targetCell = node;
            break;
          }
        }

        if (targetCell && targetCell.id !== contextMenuNodeId) {
          const sourceNode = graphInstance.getCellById(contextMenuNodeId);
          if (sourceNode) {
            const { edge: finalEdge, edgeData } = createEdgeByType(
              graphInstance,
              contextMenuNodeId,
              targetCell.id,
              connectionType
            );

            if (finalEdge && edgeData) {
              setCurrentEdgeData(edgeData);
              state.setEdgeConfigVisible(true);
            }
          }
        }
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      document.addEventListener('keydown', onKeyDown);

      containerRef.current?.focus();
    },
    [
      graphInstance,
      containerRef,
      contextMenuNodeId,
      isDrawingRef,
      drawingEdgeRef,
      updateDrawingState,
      setCurrentEdgeData,
      state,
    ]
  );

  const handleMenuClick = useCallback(
    ({ key }: MenuClickEvent) => {
      setContextMenuVisible(false);

      if (!graphInstance || !contextMenuNodeId) return;

      const selectedCell = graphInstance.getCellById(contextMenuNodeId);
      if (!selectedCell) return;

      if (selectedCell.isEdge() && key === 'configure') {
        handleEdgeConfiguration(selectedCell);
        return;
      }

      if (key === 'delete') {
        selectedCell.remove();
        return;
      }

      if (selectedCell.isNode()) {
        if (!isEditMode) {
          handleViewModeMenuClick(key, selectedCell);
          return;
        }

        if (key === 'edit') {
          handleNodeEdit(selectedCell);
          return;
        }

        if (key === 'copy') {
          handleNodeCopy(selectedCell);
          return;
        }

        if (handleNodeLayerOperation(key, selectedCell)) {
          return;
        }

        const connectionType = key as 'none' | 'single' | 'double';
        if (['none', 'single', 'double'].includes(connectionType)) {
          handleConnectionDrawing(connectionType);
        }
      }
    },
    [
      graphInstance,
      contextMenuNodeId,
      setContextMenuVisible,
      isEditMode,
      handleEdgeConfiguration,
      handleViewModeMenuClick,
      handleNodeEdit,
      handleNodeCopy,
      handleNodeLayerOperation,
      handleConnectionDrawing,
      state,
    ]
  );

  return {
    handleEdgeConfigConfirm,
    closeEdgeConfig,
    handleMenuClick
  };
};