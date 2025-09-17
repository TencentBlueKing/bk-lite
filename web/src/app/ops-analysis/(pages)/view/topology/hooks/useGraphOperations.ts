/**
 * 拓扑图操作管理核心 Hook，负责图形的初始化、事件处理、节点操作和用户交互
 */
import { useCallback, useEffect, useState, useRef } from 'react';
import type { Graph as X6Graph } from '@antv/x6';
import { v4 as uuidv4 } from 'uuid';
import { formatTimeRange } from '@/app/ops-analysis/utils/widgetDataTransform';
import { Graph } from '@antv/x6';
import { Selection } from '@antv/x6-plugin-selection';
import { Transform } from '@antv/x6-plugin-transform';
import { MiniMap } from '@antv/x6-plugin-minimap';
import { COLORS } from '../constants/nodeDefaults';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { TopologyNodeData } from '@/app/ops-analysis/types/topology';
import { DataSourceParam } from '@/app/ops-analysis/types/dashBoard';
import { updateNodeAttributes, registerNodes, createNodeByType } from '../utils/registerNode';
import { registerEdges } from '../utils/registerEdge';
import { useGraphData } from './useGraphData';
import {
  getEdgeStyleWithConfig,
  hideAllPorts,
  hideAllEdgeTools,
  showPorts,
  showEdgeTools,
  addEdgeTools,
  getValueByPath,
  formatDisplayValue,
  createPortConfig,
  adjustSingleValueNodeSize,
} from '../utils/topologyUtils';
import { getColorByThreshold } from '../utils/thresholdUtils';

export const useGraphOperations = (
  containerRef: React.RefObject<HTMLDivElement>,
  state: any,
  minimapContainerRef?: React.RefObject<HTMLDivElement>,
  minimapVisible?: boolean
) => {
  const { getSourceDataByApiId } = useDataSourceApi();

  const isPerformingUndoRedo = useRef(false);
  const isInitializing = useRef(true);

  const resetAllStyles = useCallback((graph: X6Graph) => {
    graph.getNodes().forEach((node: any) => {
      const nodeData = node.getData();
      if (nodeData?.type !== 'text') {
        const borderColor = nodeData?.type === 'single-value'
          ? (nodeData.styleConfig?.borderColor || 'transparent')
          : nodeData.styleConfig?.borderColor;
        node.setAttrByPath('body/stroke', borderColor);
      }
    });

    graph.getEdges().forEach((edge: any) => {
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

  const highlightCell = useCallback((cell: any) => {
    if (cell.isNode()) {
      const nodeData = cell.getData();
      if (nodeData?.type !== 'text') {
        cell.setAttrByPath('body/stroke', '#1890ff');
      }
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

  const highlightNode = useCallback((node: any) => {
    const nodeData = node.getData();
    if (nodeData?.type !== 'text') {
      node.setAttrByPath('body/stroke', '#1890ff');
    }
  }, []);

  const resetNodeStyle = useCallback((node: any) => {
    const nodeData = node.getData();
    if (nodeData?.type !== 'text') {
      // 对于单值节点，如果没有边框颜色则使用透明
      const borderColor = nodeData?.type === 'single-value'
        ? (nodeData.styleConfig?.borderColor || 'transparent')
        : (nodeData.styleConfig?.borderColor || '#ddd');
      node.setAttrByPath('body/stroke', borderColor);
    }
  }, []);

  const {
    graphInstance,
    setGraphInstance,
    scale,
    setScale,
    selectedCells,
    setSelectedCells,
    setIsEditMode,
    isEditModeRef,
    isEditingText,
    setOriginalText,
    setEditPosition,
    setInputWidth,
    setIsEditingText,
    setEditingNodeId,
    setTempTextInput,
    setContextMenuVisible,
    setContextMenuPosition,
    setContextMenuNodeId,
    setContextMenuTargetType,
    setCurrentEdgeData,
    startTextEditRef,
    finishTextEditRef,
  } = state;

  // 撤销/恢复相关函数 - 基于操作记录
  const [operationHistory, setOperationHistory] = useState<Array<{
    action: 'add' | 'delete' | 'update' | 'move';
    data: {
      before?: any;
      after?: any;
    };
    cellType: 'node' | 'edge';
    cellId: string;
  }>>([]);
  const [operationIndex, setOperationIndex] = useState(-1);

  const recordOperation = useCallback((operation: {
    action: 'add' | 'delete' | 'update' | 'move';
    data: {
      before?: any;
      after?: any;
    };
    cellType: 'node' | 'edge';
    cellId: string;
  }) => {
    if (isPerformingUndoRedo.current || isInitializing.current) return;

    setOperationHistory(prev => {
      const newHistory = [...prev.slice(0, operationIndex + 1), operation];
      if (newHistory.length > 50) {
        const trimmedHistory = newHistory.slice(-50);
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
            if (operation.cellType === 'node') {
              movedCell.setPosition(operation.data.before.position);
            } else if (operation.cellType === 'edge' && operation.data.before.vertices) {
              movedCell.setVertices(operation.data.before.vertices);
            }
          }
          break;

        case 'update':
          // 撤销更新：恢复到之前的状态
          const updatedCell = graphInstance.getCellById(operation.cellId);
          if (updatedCell && operation.data.before) {
            // 根据操作类型恢复不同的属性
            if (operation.data.before.attrs) {
              updatedCell.setAttrs(operation.data.before.attrs);
            }
            if (operation.data.before.data) {
              updatedCell.setData(operation.data.before.data);
            }
            if (operation.data.before.size && operation.cellType === 'node') {
              updatedCell.setSize(operation.data.before.size);
            }
          }
          break;
      }

      setOperationIndex(prev => prev - 1);
      setTimeout(() => {
        isPerformingUndoRedo.current = false;
      }, 50);
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
            if (operation.cellType === 'node') {
              cellToMove.setPosition(operation.data.after.position);
            } else if (operation.cellType === 'edge' && operation.data.after.vertices) {
              cellToMove.setVertices(operation.data.after.vertices);
            }
          }
          break;

        case 'update':
          // 重做更新：应用新的状态
          const cellToUpdate = graphInstance.getCellById(operation.cellId);
          if (cellToUpdate && operation.data.after) {
            if (operation.data.after.attrs) {
              cellToUpdate.setAttrs(operation.data.after.attrs);
            }
            if (operation.data.after.data) {
              cellToUpdate.setData(operation.data.after.data);
            }
            if (operation.data.after.size && operation.cellType === 'node') {
              cellToUpdate.setSize(operation.data.after.size);
            }
          }
          break;
      }

      setOperationIndex(prev => prev + 1);
      setTimeout(() => {
        isPerformingUndoRedo.current = false;
      }, 50);
    } catch (error) {
      console.error('重做失败:', error);
      isPerformingUndoRedo.current = false;
    }
  }, [graphInstance, operationHistory, operationIndex]);

  const canUndo = operationIndex >= 0 && operationIndex < operationHistory.length;
  const canRedo = operationIndex >= -1 && operationIndex < operationHistory.length - 1;

  const updateSingleNodeData = useCallback(async (nodeConfig: TopologyNodeData) => {
    if (!nodeConfig || !graphInstance) return;

    const node = graphInstance.getCellById(nodeConfig.id);
    const { valueConfig } = nodeConfig || {};
    if (!node) return;

    if (nodeConfig.type !== 'single-value' || !valueConfig?.dataSource || !valueConfig?.selectedFields?.length) {
      return;
    }

    try {
      let requestParams = {};

      if (valueConfig.dataSourceParams && Array.isArray(valueConfig.dataSourceParams)) {
        requestParams = valueConfig.dataSourceParams.reduce((acc: any, param: DataSourceParam) => {
          if (param.value !== undefined) {
            acc[param.name] = (param.type === 'timeRange')
              ? formatTimeRange(param.value)
              : param.value;
          }
          return acc;
        }, {});
      }

      const resData = await getSourceDataByApiId(valueConfig.dataSource, requestParams);
      if (resData && Array.isArray(resData) && resData.length > 0) {
        const latestData = resData[resData.length - 1];
        const field = valueConfig.selectedFields[0];
        const value = getValueByPath(latestData, field);

        let displayValue;
        const numericValue = typeof value === 'string' ? parseFloat(value) : value;

        if (typeof numericValue === 'number' && !isNaN(numericValue)) {
          // 应用换算系数
          const conversionFactor = nodeConfig.conversionFactor !== undefined ? nodeConfig.conversionFactor : 1;
          const convertedValue = numericValue * conversionFactor;

          const decimalPlaces = nodeConfig.decimalPlaces !== undefined ? nodeConfig.decimalPlaces : 2;
          displayValue = parseFloat(convertedValue.toFixed(decimalPlaces)).toString();
        } else {
          displayValue = formatDisplayValue(value, undefined, undefined, nodeConfig.conversionFactor);
        }
        if (nodeConfig.unit && nodeConfig.unit.trim()) {
          displayValue = `${displayValue} ${nodeConfig.unit}`;
        }

        // 根据阈值配置计算文本颜色
        let textColor = nodeConfig.styleConfig?.textColor;
        if (nodeConfig.styleConfig?.thresholdColors?.length) {
          textColor = getColorByThreshold(value, nodeConfig.styleConfig.thresholdColors, nodeConfig.styleConfig.textColor);
        }

        const currentNodeData = node.getData();
        const updatedData = {
          ...currentNodeData,
          isLoading: false,
          hasError: false,
        };
        node.setData(updatedData);
        node.setAttrByPath('label/text', displayValue);
        node.setAttrByPath('label/fill', textColor);

        adjustSingleValueNodeSize(node, displayValue);
      } else {
        throw new Error('无数据');
      }
    } catch (error) {
      console.error('更新单值节点数据失败:', error);
      const currentNodeData = node.getData();
      const updatedData = {
        ...currentNodeData,
        isLoading: false,
        hasError: true,
      };
      node.setData(updatedData);
      node.setAttrByPath('label/text', '--');
      adjustSingleValueNodeSize(node, '--');
    }
  }, [graphInstance, getSourceDataByApiId]);

  const startLoadingAnimation = useCallback((node: any) => {
    const loadingStates = ['○ ○ ○', '● ○ ○', '○ ● ○', '○ ○ ●', '○ ○ ○'];
    let currentIndex = 0;

    const updateLoading = () => {
      const nodeData = node.getData();
      if (!nodeData?.isLoading) {
        return;
      }

      const currentLoadingText = loadingStates[currentIndex];
      node.setAttrByPath('label/text', currentLoadingText);

      adjustSingleValueNodeSize(node, currentLoadingText, 80);

      currentIndex = (currentIndex + 1) % loadingStates.length;

      setTimeout(updateLoading, 300);
    };

    setTimeout(updateLoading, 300);
  }, []);

  const handleSave = useCallback(() => {
    setIsEditMode(false);
    isEditModeRef.current = false;

    if (graphInstance) {
      graphInstance.disablePlugins(['selection']);
      hideAllPorts(graphInstance);
      hideAllEdgeTools(graphInstance);

      graphInstance.getEdges().forEach((edge: any) => {
        const edgeData = edge.getData();
        const customColor = edgeData?.styleConfig?.lineColor;

        edge.setAttrs({
          line: {
            ...edge.getAttrs().line,
            stroke: customColor || COLORS.EDGE.DEFAULT,
            strokeWidth: 1,
          },
        });
      });

      if (isEditingText) {
        setIsEditingText(false);
        setEditingNodeId(null);
        setTempTextInput('');
        setEditPosition({ x: 0, y: 0 });
        setInputWidth(120);
        setOriginalText('');
      }

      setContextMenuVisible(false);
      graphInstance.cleanSelection();
      setSelectedCells([]);
    }
  }, [graphInstance, isEditingText, setIsEditMode]);

  // 缩略图插件初始化函数
  const initMiniMap = useCallback((graph: X6Graph) => {
    if (minimapContainerRef?.current && minimapVisible) {
      graph.disposePlugins(['minimap']);
      graph.use(
        new MiniMap({
          container: minimapContainerRef.current,
          width: 200,
          height: 117,
          padding: 6,
          scalable: true,
          minScale: 0.01,
          maxScale: 16,
          graphOptions: {
            grid: {
              visible: false,
            },
            background: {
              color: 'rgba(248, 249, 250, 0.8)',
            },
            interacting: false,
          },
        })
      );
    }
  }, [minimapContainerRef, minimapVisible]);

  // 监听缩略图可见性变化，重新初始化缩略图
  useEffect(() => {
    if (graphInstance) {
      if (minimapVisible) {
        setTimeout(() => {
          initMiniMap(graphInstance);
        }, 100);
      } else {
        try {
          graphInstance.disposePlugins(['minimap']);
        } catch (e) {
          console.log(e);
        }
      }
    }
  }, [graphInstance, minimapVisible, initMiniMap]);

  const dataOperations = useGraphData(graphInstance, updateSingleNodeData, startLoadingAnimation, handleSave);

  // 监听图形变化，记录操作而不是保存完整状态
  useEffect(() => {
    if (!graphInstance) return;

    const handleNodeAdded = ({ node }: any) => {
      recordOperation({
        action: 'add',
        cellType: 'node',
        cellId: node.id,
        data: {
          after: node.toJSON()
        }
      });
    };

    const handleNodeRemoved = ({ node }: any) => {
      recordOperation({
        action: 'delete',
        cellType: 'node',
        cellId: node.id,
        data: {
          before: node.toJSON()
        }
      });
    };

    const handleEdgeAdded = ({ edge }: any) => {
      recordOperation({
        action: 'add',
        cellType: 'edge',
        cellId: edge.id,
        data: {
          after: edge.toJSON()
        }
      });
    };

    const handleEdgeRemoved = ({ edge }: any) => {
      recordOperation({
        action: 'delete',
        cellType: 'edge',
        cellId: edge.id,
        data: {
          before: edge.toJSON()
        }
      });
    };

    // 记录移动操作
    const nodePositions = new Map<string, any>();
    const edgeVertices = new Map<string, any>();

    const handleNodeMoveStart = ({ node }: any) => {
      nodePositions.set(node.id, node.getPosition());
    };

    const handleNodeMoved = ({ node }: any) => {
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
              after: { position: newPosition }
            }
          });
        }
        nodePositions.delete(node.id);
      }
    };

    const handleEdgeVerticesStart = ({ edge }: any) => {
      edgeVertices.set(edge.id, edge.getVertices());
    };

    const handleEdgeVerticesChanged = ({ edge }: any) => {
      const oldVertices = edgeVertices.get(edge.id);
      if (oldVertices) {
        const newVertices = edge.getVertices();
        recordOperation({
          action: 'move',
          cellType: 'edge',
          cellId: edge.id,
          data: {
            before: { vertices: oldVertices },
            after: { vertices: newVertices }
          }
        });
        edgeVertices.delete(edge.id);
      }
    };

    graphInstance.on('node:added', handleNodeAdded);
    graphInstance.on('node:removed', handleNodeRemoved);
    graphInstance.on('edge:added', handleEdgeAdded);
    graphInstance.on('edge:removed', handleEdgeRemoved);

    // 监听移动事件
    graphInstance.on('node:move', handleNodeMoveStart);
    graphInstance.on('node:moved', handleNodeMoved);
    graphInstance.on('edge:change:vertices', handleEdgeVerticesStart);
    graphInstance.on('edge:change:vertices', handleEdgeVerticesChanged);

    return () => {
      graphInstance.off('node:added', handleNodeAdded);
      graphInstance.off('node:removed', handleNodeRemoved);
      graphInstance.off('edge:added', handleEdgeAdded);
      graphInstance.off('edge:removed', handleEdgeRemoved);
      graphInstance.off('node:move', handleNodeMoveStart);
      graphInstance.off('node:moved', handleNodeMoved);
      graphInstance.off('edge:change:vertices', handleEdgeVerticesStart);
      graphInstance.off('edge:change:vertices', handleEdgeVerticesChanged);
    };
  }, [graphInstance, recordOperation]);

  const bindGraphEvents = (graph: X6Graph) => {
    const hideCtx = () => setContextMenuVisible(false);
    document.addEventListener('click', hideCtx);

    graph.on('scale', ({ sx }) => {
      setScale(sx);
    });

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      const delta = e.deltaY;
      const factor = 1.1;
      const currentScale = graph.zoom();
      const maxScale = 3;
      const minScale = 0.05;

      let newScale;
      if (delta > 0) {
        newScale = currentScale / factor;
      } else {
        newScale = currentScale * factor;
      }

      newScale = Math.max(minScale, Math.min(maxScale, newScale));

      const rect = containerRef.current?.getBoundingClientRect();
      if (rect) {
        const clientX = e.clientX - rect.left;
        const clientY = e.clientY - rect.top;

        graph.zoom(newScale, {
          absolute: true,
          center: { x: clientX, y: clientY }
        });
      } else {
        graph.zoom(newScale, { absolute: true });
      }
    };

    if (containerRef.current) {
      containerRef.current.addEventListener('wheel', handleWheel, { passive: false });
    }

    const cleanup = () => {
      document.removeEventListener('click', hideCtx);
      if (containerRef.current) {
        containerRef.current.removeEventListener('wheel', handleWheel);
      }
    };

    graph.on('node:contextmenu', ({ e, node }) => {
      e.preventDefault();
      setContextMenuVisible(true);
      setContextMenuPosition({ x: e.clientX, y: e.clientY });
      setContextMenuNodeId(node.id);
      setContextMenuTargetType('node');
    });

    graph.on('node:click', ({ e }) => {
      if (e.shiftKey) {
        return;
      }
      // 移除直接打开配置面板的逻辑，改为通过右键菜单的"编辑"选项
    });

    graph.on('edge:contextmenu', ({ e, edge }) => {
      e.preventDefault();
      setContextMenuVisible(true);
      setContextMenuPosition({ x: e.clientX, y: e.clientY });
      setContextMenuNodeId(edge.id);
      setContextMenuTargetType('edge');

      // 设置边数据用于配置
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
      }
    });

    graph.on('edge:connected', ({ edge }: any) => {
      if (!edge || !isEditModeRef.current) return;

      const edgeData = edge.getData() || {};
      const arrowDirection = edgeData.arrowDirection || 'single';
      const defaultStyleConfig = {
        lineColor: COLORS.EDGE.DEFAULT,
        lineWidth: 1,
        lineStyle: 'line' as const,
        enableAnimation: false,
      };

      edge.setAttrs(getEdgeStyleWithConfig(arrowDirection, defaultStyleConfig).attrs);
      addEdgeTools(edge);
      edge.setData({
        lineType: 'common_line',
        lineName: '',
        arrowDirection: arrowDirection,
        styleConfig: defaultStyleConfig
      });
    });

    // 监听边的拐点变化并保存
    graph.on('edge:change:vertices', ({ edge }: any) => {
      if (!edge || !isEditModeRef.current) return;

      const vertices = edge.getVertices();
      const currentData = edge.getData() || {};

      edge.setData({
        ...currentData,
        vertices: vertices
      });
    });

    graph.on('edge:connecting', () => {
      if (isEditModeRef.current) {
        graph.getNodes().forEach((node: any) => {
          const nodeData = node.getData();
          if (nodeData?.type !== 'text') {
            showPorts(graph, node);
          }
        });
      }
    });

    graph.on('edge:connected edge:disconnected', () => {
      hideAllPorts(graph);
    });

    graph.on('selection:changed', ({ selected }) => {
      if (!isEditModeRef.current) return;

      setSelectedCells(selected.map((cell) => cell.id));
      resetAllStyles(graph);
      selected.forEach(highlightCell);
    });

    graph.on('edge:dblclick', ({ edge }) => {
      addEdgeTools(edge);
    });

    graph.on('node:dblclick', ({ node }) => {
      const nodeData = node.getData();
      if (nodeData?.type === 'text') {
        const currentText = String(
          node.getAttrs()?.label?.text || '双击编辑文本'
        );
        const textToEdit =
          nodeData?.isPlaceholder || currentText === '双击编辑文本'
            ? ''
            : currentText;
        startTextEditRef.current?.(node.id, textToEdit);
      }
    });

    graph.on('blank:click', () => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      setContextMenuVisible(false);

      resetAllStyles(graph);

      graph.cleanSelection();
      setSelectedCells([]);

      setTimeout(() => {
        finishTextEditRef.current?.();
      }, 0);
    });

    graph.on('node:mouseenter', ({ node }) => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      const nodeData = node.getData();
      if (nodeData?.type !== 'text') {
        showPorts(graph, node);
        const isSelected = selectedCells.includes(node.id);
        if (!isSelected) {
          highlightNode(node);
        }
      }
    });

    graph.on('edge:mouseenter', ({ edge }) => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      showPorts(graph, edge);
      showEdgeTools(edge);
    });

    graph.on('node:mouseleave', ({ node }) => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      const isSelected = selectedCells.includes(node.id);
      if (!isSelected) {
        resetNodeStyle(node);
      }
    });

    graph.on('edge:mouseleave', () => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
    });

    // 记录节点大小变化操作
    const nodeOriginalSizes = new Map<string, any>();

    const handleNodeSizeUpdate = (node: any, isRealtime = false) => {
      const nodeData = node.getData();
      const size = node.getSize();

      // 记录开始大小变化时的原始大小
      if (isRealtime && !nodeOriginalSizes.has(node.id)) {
        const originalSize = node.getSize();
        const originalData = node.getData();
        nodeOriginalSizes.set(node.id, {
          size: { width: originalSize.width, height: originalSize.height },
          data: originalData,
          attrs: node.getAttrs()
        });
      }

      const updatedConfig = {
        ...nodeData,
        styleConfig: {
          ...(nodeData.styleConfig || {}),
          width: size.width,
          height: size.height,
        },
      };

      node.setData(updatedConfig);

      if (nodeData.type === 'icon' || nodeData.type === 'single-value') {
        if (!isRealtime) {
          updateNodeAttributes(node, updatedConfig);

          // 大小变化结束时记录操作
          const originalState = nodeOriginalSizes.get(node.id);
          if (originalState) {
            const newSize = node.getSize();
            // 只有大小真正发生变化时才记录
            if (originalState.size.width !== newSize.width || originalState.size.height !== newSize.height) {
              recordOperation({
                action: 'update',
                cellType: 'node',
                cellId: node.id,
                data: {
                  before: {
                    size: originalState.size,
                    data: originalState.data,
                    attrs: originalState.attrs
                  },
                  after: {
                    size: { width: newSize.width, height: newSize.height },
                    data: updatedConfig,
                    attrs: node.getAttrs()
                  }
                }
              });
            }
            nodeOriginalSizes.delete(node.id);
          }
        }
      } else if (nodeData.type === 'chart') {
        const chartPortConfig = createPortConfig();
        node.prop('ports', chartPortConfig);

        if (!isRealtime) {
          // 图表节点大小变化结束时记录操作
          const originalState = nodeOriginalSizes.get(node.id);
          if (originalState) {
            const newSize = node.getSize();
            if (originalState.size.width !== newSize.width || originalState.size.height !== newSize.height) {
              recordOperation({
                action: 'update',
                cellType: 'node',
                cellId: node.id,
                data: {
                  before: {
                    size: originalState.size,
                    data: originalState.data,
                    attrs: originalState.attrs
                  },
                  after: {
                    size: { width: newSize.width, height: newSize.height },
                    data: updatedConfig,
                    attrs: node.getAttrs()
                  }
                }
              });
            }
            nodeOriginalSizes.delete(node.id);
          }
        }
      }
    };

    graph.on('node:resize', ({ node }) => {
      handleNodeSizeUpdate(node, true);
    });

    graph.on('node:resized', ({ node }) => {
      handleNodeSizeUpdate(node, false);
    });

    graph.getNodes().forEach((node) => {
      const nodeData = node.getData();
      if (nodeData?.type !== 'text') {
        ['top', 'bottom', 'left', 'right'].forEach((port) =>
          node.setPortProp(port, 'attrs/circle/opacity', 0)
        );
      }
    });

    return cleanup;
  };

  useEffect(() => {
    if (!containerRef.current) return;

    registerNodes();
    registerEdges();

    const graph: X6Graph = new Graph({
      container: containerRef.current,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      grid: true,
      panning: true,
      autoResize: true,
      mousewheel: {
        enabled: true,
        modifiers: ['ctrl', 'meta'],
        factor: 1.1,
        maxScale: 3,
        minScale: 0.05
      },
      connecting: {
        anchor: {
          name: 'center',
          args: { dx: 0, dy: 0 },
        },
        connectionPoint: { name: 'boundary' },
        connector: { name: 'normal' },
        router: { name: 'manhattan' },
        allowBlank: false,
        allowMulti: true,
        allowLoop: false,
        highlight: true,
        snap: { radius: 20 },
        createEdge: () =>
          graph.createEdge({
            shape: 'edge',
            ...getEdgeStyleWithConfig('single', {
              lineColor: COLORS.EDGE.DEFAULT,
              lineWidth: 1,
              lineStyle: 'line',
              enableAnimation: false
            })
          }),
        validateMagnet: ({ magnet }) => {
          return (
            isEditModeRef.current && magnet.getAttribute('magnet') === 'true'
          );
        },
        validateConnection: ({
          sourceMagnet,
          targetMagnet,
          sourceView,
          targetView,
        }) => {
          if (!isEditModeRef.current) return false;
          if (!sourceMagnet || !targetMagnet) return false;
          if (sourceView === targetView) return false;

          const sourceNode = sourceView?.cell;
          const targetNode = targetView?.cell;

          if (
            sourceNode?.getData()?.type === 'text' ||
            targetNode?.getData()?.type === 'text'
          ) {
            return false;
          }

          const sourceMagnetType = sourceMagnet.getAttribute('magnet');
          const targetMagnetType = targetMagnet.getAttribute('magnet');

          return sourceMagnetType === 'true' && targetMagnetType === 'true';
        },
      },
      interacting: () => ({
        nodeMovable: state.isEditModeRef.current,
        edgeMovable: state.isEditModeRef.current,
        arrowheadMovable: state.isEditModeRef.current,
        vertexMovable: state.isEditModeRef.current,
        vertexAddable: state.isEditModeRef.current,
        vertexDeletable: state.isEditModeRef.current,
        magnetConnectable: state.isEditModeRef.current,
      }),
    });

    graph.use(
      new Selection({
        enabled: true,
        rubberband: true,
        showNodeSelectionBox: false,
        modifiers: 'shift',
        filter: (cell) => cell.isNode() || cell.isEdge(),
      })
    );

    // 节点缩放插件
    graph.use(
      new Transform({
        resizing: {
          enabled: (node) => {
            const nodeData = node.getData();
            return state.isEditModeRef.current && nodeData?.type !== 'text';
          },
          minWidth: 32,
          minHeight: 32,
          preserveAspectRatio: (node) => {
            const nodeData = node.getData();
            return nodeData?.type === 'icon' || nodeData?.type === 'single-value';
          },
        },
        rotating: false,
      })
    );

    const cleanup = bindGraphEvents(graph);
    setGraphInstance(graph);

    return () => {
      cleanup();
      graph.dispose();
    };
  }, []);

  const zoomIn = useCallback(() => {
    if (graphInstance) {
      const next = scale + 0.1;
      graphInstance.zoom(next, { absolute: true });
    }
  }, [graphInstance, scale]);

  const zoomOut = useCallback(() => {
    if (graphInstance) {
      const next = scale - 0.1 > 0.1 ? scale - 0.1 : 0.1;
      graphInstance.zoom(next, { absolute: true });
    }
  }, [graphInstance, scale]);

  const handleFit = useCallback(() => {
    if (graphInstance && containerRef.current) {
      graphInstance.zoomToFit({ padding: 20, maxScale: 1 });
    }
  }, [graphInstance]);

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

  const addNewNode = useCallback((nodeConfig: any) => {
    if (!graphInstance) {
      return null;
    }
    const nodeData = createNodeByType(nodeConfig);
    const { valueConfig } = nodeConfig || {};
    const addedNode = graphInstance.addNode(nodeData);
    if (nodeConfig.type === 'single-value') {
      adjustSingleValueNodeSize(addedNode, nodeConfig.name || '单值节点');
    }
    if (nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length) {
      startLoadingAnimation(addedNode);
      updateSingleNodeData({ ...nodeConfig, id: addedNode.id });
    }
    return addedNode.id;
  }, [graphInstance, updateSingleNodeData, startLoadingAnimation]);

  const handleNodeUpdate = useCallback(async (values: any) => {
    if (!values) {
      return;
    }
    const editingNode = state.editingNodeData;
    const { valueConfig, styleConfig } = editingNode || {};
    try {
      const updatedConfig = {
        id: editingNode.id,
        type: editingNode.type,
        name: values.name,
        unit: values.unit,
        conversionFactor: values.conversionFactor,
        decimalPlaces: values.decimalPlaces,
        description: values.description,
        position: editingNode.position,
        logoType: values.logoType || editingNode.logoType,
        logoIcon: values.logoIcon || editingNode.logoIcon,
        logoUrl: values.logoUrl || editingNode.logoUrl,
        valueConfig: {
          selectedFields: values.selectedFields || valueConfig?.selectedFields,
          chartType: values.chartType || valueConfig?.chartType,
          dataSource: values.dataSource || valueConfig?.dataSource,
          dataSourceParams: values.dataSourceParams || valueConfig?.dataSourceParams,
        },
        styleConfig: {
          textColor: values.textColor !== undefined ? values.textColor : styleConfig?.textColor,
          fontSize: values.fontSize !== undefined ? values.fontSize : styleConfig?.fontSize,
          backgroundColor: values.backgroundColor !== undefined ? values.backgroundColor : styleConfig?.backgroundColor,
          borderColor: values.borderColor !== undefined ? values.borderColor : styleConfig?.borderColor,
          borderWidth: values.borderWidth !== undefined ? values.borderWidth : styleConfig?.borderWidth,
          iconPadding: values.iconPadding !== undefined ? values.iconPadding : styleConfig?.iconPadding,
          width: values.width !== undefined ? values.width : styleConfig?.width,
          height: values.height !== undefined ? values.height : styleConfig?.height,
          lineType: values.lineType !== undefined ? values.lineType : styleConfig?.lineType,
          shapeType: values.shapeType !== undefined ? values.shapeType : styleConfig?.shapeType,
          nameColor: values.nameColor !== undefined ? values.nameColor : styleConfig?.nameColor,
          nameFontSize: values.nameFontSize !== undefined ? values.nameFontSize : styleConfig?.nameFontSize,
          thresholdColors: values.thresholdColors !== undefined ? values.thresholdColors : styleConfig?.thresholdColors,
        },
      };

      if (!graphInstance) {
        return;
      }

      const node = graphInstance.getCellById(updatedConfig.id);
      if (!node) {
        return;
      }

      updateNodeAttributes(node, updatedConfig);

      if (updatedConfig.type === 'single-value' && updatedConfig.valueConfig?.dataSource && updatedConfig.valueConfig?.selectedFields?.length) {
        // 先设置loading状态
        const nodeData = node.getData();
        node.setData({
          ...nodeData,
          isLoading: true,
          hasError: false
        });
        startLoadingAnimation(node);
        updateSingleNodeData(updatedConfig);
      }

      state.setNodeEditVisible(false);
      state.setEditingNodeData(null);
    } catch (error) {
      console.error('节点更新失败:', error);
    }
  }, [graphInstance, updateSingleNodeData, state]);

  const handleViewConfigConfirm = useCallback((values: any) => {
    if (state.editingNodeData && graphInstance) {
      const node = graphInstance.getCellById(
        state.editingNodeData.id
      );
      if (node) {
        const updatedData = {
          ...state.editingNodeData,
          name: values.name,
          valueConfig: {
            chartType: values.chartType,
            dataSource: values.dataSource,
            dataSourceParams: values.dataSourceParams,
          },
          isLoading: !!values.dataSource,
          hasError: false,
        };
        node.setData(updatedData);

        if (state.editingNodeData.type === 'chart' && values.dataSource) {
          dataOperations.loadChartNodeData(state.editingNodeData.id, updatedData.valueConfig);
        }
      }
    }
    state.setViewConfigVisible(false);
  }, [graphInstance, state, dataOperations]);


  const handleAddChartNode = useCallback(async (values: any) => {
    if (!graphInstance) {
      return null;
    }
    const nodeConfig = {
      id: `node_${uuidv4()}`,
      type: 'chart',
      name: values.name,
      description: values.description || '',
      position: state.editingNodeData.position,
      styleConfig: {},
      valueConfig: {
        chartType: values.chartType,
        dataSource: values.dataSource,
        dataSourceParams: values.dataSourceParams,
      },
    };
    const nodeId = addNewNode(nodeConfig);
    if (nodeConfig.valueConfig?.dataSource && nodeId) {
      dataOperations.loadChartNodeData(nodeId, nodeConfig.valueConfig);
    }
  }, [graphInstance, addNewNode, dataOperations]);


  const resizeCanvas = useCallback((width?: number, height?: number) => {
    if (!graphInstance) return;
    if (width && height) {
      graphInstance.resize(width, height);
    } else {
      graphInstance.resize();
    }
  }, [graphInstance]);

  const toggleEditMode = useCallback(() => {
    const newEditMode = !state.isEditMode;
    state.setIsEditMode(newEditMode);
    state.isEditModeRef.current = newEditMode;

    if (graphInstance) {
      if (newEditMode) {
        graphInstance.enablePlugins(['selection']);
      } else {
        graphInstance.disablePlugins(['selection']);

        if (state.isEditingText) {
          state.setIsEditingText(false);
          state.setEditingNodeId(null);
          state.setTempTextInput('');
          state.setEditPosition({ x: 0, y: 0 });
          state.setInputWidth(120);
          state.setOriginalText('');
        }

        state.setContextMenuVisible(false);
        graphInstance.cleanSelection();
        state.setSelectedCells([]);
      }
    }
  }, [state, graphInstance]);



  const handleNodeEditClose = useCallback(() => {
    state.setNodeEditVisible(false);
    state.setEditingNodeData(null);
  }, [state]);

  // 手动完成初始化，启用操作记录
  const finishInitialization = useCallback(() => {
    isInitializing.current = false;
  }, []);

  // 重新开始初始化，禁用操作记录
  const startInitialization = useCallback(() => {
    isInitializing.current = true;
  }, []);

  // 清空操作历史记录
  const clearOperationHistory = useCallback(() => {
    setOperationHistory([]);
    setOperationIndex(-1);
  }, []);

  return {
    zoomIn,
    zoomOut,
    handleFit,
    handleDelete,
    handleSelectMode,
    handleSave,
    addNewNode,
    handleNodeUpdate,
    handleViewConfigConfirm,
    handleAddChartNode,
    resizeCanvas,
    toggleEditMode,
    handleNodeEditClose,
    undo,
    redo,
    canUndo,
    canRedo,
    finishInitialization,
    startInitialization,
    clearOperationHistory,
    ...dataOperations,
  };
};
