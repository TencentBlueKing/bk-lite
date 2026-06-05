/**
 * 拓扑图操作管理核心 Hook，负责图形的初始化、事件处理、节点操作和用户交互
 */
import { useCallback, useEffect, useRef } from 'react';
import type { Graph as X6Graph, Node, Edge } from '@antv/x6';
import { v4 as uuidv4 } from 'uuid';
import { buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import { Graph } from '@antv/x6';
import { Selection } from '@antv/x6-plugin-selection';
import { Transform } from '@antv/x6-plugin-transform';
import { MiniMap } from '@antv/x6-plugin-minimap';
import { COLORS } from '../constants/nodeDefaults';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { TopologyNodeData } from '@/app/ops-analysis/types/topology';
import type { UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import { fetchCompareData, extractComparableValue, getChangePercent, toComparableNumber } from '@/app/ops-analysis/utils/compareQuery';
import { updateNodeAttributes, registerNodes, createNodeByType } from '../utils/registerNode';
import { useTranslation } from '@/utils/i18n';
import { registerEdges } from '../utils/registerEdge';
import { useGraphData } from './useGraphData';
import { useGraphHistory } from './useGraphHistory';
import { buildValueConfig } from '../utils/namespaceUtils';
import type {
  NodeConfigFormValues,
  ViewConfigFormValues
} from '@/app/ops-analysis/types/topology';
import {
  getEdgeStyleWithConfig,
  hideAllPorts,
  hideAllEdgeTools,
  showPorts,
  showEdgeTools,
  addEdgeTools,
  formatDisplayValue,
  createPortConfig,
  adjustSingleValueNodeSize,
} from '../utils/topologyUtils';
import { getColorByThreshold } from '../utils/thresholdUtils';

const LOADING_ANIMATION_INTERVAL = 300; // 加载动画间隔时间（ms）

/** 构造 fetchCompareData 所需的最小 DataSource 占位对象 */
/** 对数值应用换算系数和小数位数，返回格式化后的字符串 */
function formatNumericValue(
  rawValue: unknown,
  conversionFactor?: number,
  decimalPlaces?: number,
): string {
  const numericValue = typeof rawValue === 'string' ? parseFloat(rawValue) : rawValue;

  if (typeof numericValue === 'number' && !isNaN(numericValue)) {
    const factor = conversionFactor !== undefined ? conversionFactor : 1;
    const places = decimalPlaces !== undefined ? decimalPlaces : 2;
    return parseFloat((numericValue * factor).toFixed(places)).toString();
  }

  return formatDisplayValue(rawValue, undefined, undefined, conversionFactor);
}

/** 构建周期对比后缀文本 */
function buildCompareSuffix(
  compareLabel: string,
  changePercent: number | null,
): string {
  if (changePercent === null) {
    return ` (${compareLabel} --)`;
  }
  const arrow = changePercent > 0 ? '↑' : changePercent < 0 ? '↓' : '';
  return ` (${compareLabel} ${arrow}${Math.abs(changePercent).toFixed(1)}%)`;
}

/** 合并样式字段：优先取 values 中有值的字段，否则回退到 existing */
function mergeStyleConfig(
  values: Record<string, any>,
  existing: Record<string, any> | undefined,
  keys: string[],
): Record<string, any> {
  const result: Record<string, any> = {};
  for (const key of keys) {
    result[key] = values[key] !== undefined ? values[key] : existing?.[key];
  }
  return result;
}

export const useGraphOperations = (
  containerRef: React.RefObject<HTMLDivElement | null>,
  state: ReturnType<typeof import('./useTopologyState').useTopologyState>,
  minimapContainerRef?: React.RefObject<HTMLDivElement | null>,
  onNodeRemoved?: () => void,
  isZoomLocked = false,
) => {
  const { t } = useTranslation();
  const { getSourceDataByApiId } = useDataSourceApi();
  const isZoomLockedRef = useRef(isZoomLocked);

  useEffect(() => {
    isZoomLockedRef.current = isZoomLocked;
  }, [isZoomLocked]);

  const {
    graphInstance,
    setGraphInstance,
    scale,
    setScale,
    selectedCells,
    setSelectedCells,
    setIsEditMode,
    isEditModeRef,
    setContextMenuVisible,
    setContextMenuPosition,
    setContextMenuNodeId,
    setContextMenuTargetType,
    setCurrentEdgeData,
  } = state;

  // 使用历史记录管理 hook
  const history = useGraphHistory(graphInstance);
  const {
    resetAllStyles,
    highlightCell,
    highlightNode,
    resetNodeStyle,
    recordOperation,
    undo,
    redo,
    canUndo,
    canRedo,
    clearOperationHistory,
    startInitialization,
    finishInitialization,
  } = history;

  const updateSingleNodeData = useCallback(async (
    nodeConfig: TopologyNodeData,
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    namespaceId?: number
  ) => {
    if (!nodeConfig || !graphInstance || !nodeConfig.id) return;

    const node = graphInstance.getCellById(nodeConfig.id);
    const { valueConfig } = nodeConfig || {};
    if (!node) return;

    if (nodeConfig.type !== 'single-value' || !valueConfig?.dataSource || !valueConfig?.selectedFields?.length) {
      return;
    }

    // 设置加载状态并启动加载动画
    node.setData({ ...node.getData(), isLoading: true, hasError: false }, { overwrite: true });
    if (node.isNode()) {
      startLoadingAnimation(node as Node);
    }

    try {
      const effectiveFilterBindings = valueConfig.filterBindings || 
        buildDefaultFilterBindings(valueConfig.dataSourceParams || [], filterDefinitions || [], undefined);

      const compareResult = await fetchCompareData({
        dataSourceId: Number(valueConfig.dataSource),
        getSourceDataByApiId,
        config: valueConfig,
        dataSource: { params: valueConfig.dataSourceParams || [] },
        extraParams: namespaceId !== undefined ? { namespace_id: namespaceId } : undefined,
        unifiedFilterValues,
        filterBindings: effectiveFilterBindings,
        filterDefinitions,
      });

      const dataToExtract = compareResult.currentData;
      if (!dataToExtract) {
        throw new Error(t('topology.noData'));
      }

      // 提取当前值与基线值
      const field = valueConfig.selectedFields[0];
      const value = extractComparableValue(dataToExtract, field);
      const baselineValue = extractComparableValue(compareResult.baselineData, field);
      const changePercent = valueConfig.compare
        ? getChangePercent(toComparableNumber(value), toComparableNumber(baselineValue))
        : null;

      // 格式化显示文本
      let displayValue = formatNumericValue(value, nodeConfig.conversionFactor, nodeConfig.decimalPlaces);
      if (nodeConfig.unit?.trim()) {
        displayValue = `${displayValue} ${nodeConfig.unit}`;
      }

      const compareSuffix = valueConfig.compare
        ? buildCompareSuffix(t('dashboard.comparePreviousShortLabel'), changePercent)
        : '';
      const nodeText = `${displayValue}${compareSuffix}`;

      // 根据阈值配置计算文本颜色
      let textColor = nodeConfig.styleConfig?.textColor;
      if (nodeConfig.styleConfig?.thresholdColors?.length) {
        const numValue = typeof value === 'string' ? parseFloat(value) : (typeof value === 'number' ? value : null);
        textColor = getColorByThreshold(numValue, nodeConfig.styleConfig.thresholdColors, nodeConfig.styleConfig.textColor);
      }

      // 更新节点
      node.setData({ ...node.getData(), isLoading: false, hasError: false }, { overwrite: true });
      node.setAttrByPath('label/text', nodeText);
      node.setAttrByPath('label/fill', textColor);

      if (node.isNode()) {
        adjustSingleValueNodeSize(node, nodeText);
      }
    } catch (error) {
      console.error('更新单值节点数据失败:', error);
      node.setData({ ...node.getData(), isLoading: false, hasError: true }, { overwrite: true });
      node.setAttrByPath('label/text', '--');
      if (node.isNode()) {
        adjustSingleValueNodeSize(node, '--');
      }
    }
  }, [graphInstance, getSourceDataByApiId]);

  const startLoadingAnimation = useCallback((node: Node) => {
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

      setTimeout(updateLoading, LOADING_ANIMATION_INTERVAL);
    };

    setTimeout(updateLoading, LOADING_ANIMATION_INTERVAL);
  }, []);

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
  }, [graphInstance, setIsEditMode]);

  const initMiniMap = useCallback((graph: X6Graph) => {
    if (minimapContainerRef?.current) {
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
  }, [minimapContainerRef]);

  const dataOperations = useGraphData(graphInstance, updateSingleNodeData, startLoadingAnimation, handleSave);

  // 监听图形变化，记录操作而不是保存完整状态
  useEffect(() => {
    if (!graphInstance) return;

    const handleNodeAdded = ({ node }: { node: Node }) => {
      recordOperation({
        action: 'add',
        cellType: 'node',
        cellId: node.id,
        data: {
          after: node.toJSON()
        }
      });
    };

    const handleNodeRemoved = ({ node }: { node: Node }) => {
      recordOperation({
        action: 'delete',
        cellType: 'node',
        cellId: node.id,
        data: {
          before: node.toJSON()
        }
      });
      onNodeRemoved?.();
    };

    const handleEdgeAdded = ({ edge }: { edge: Edge }) => {
      recordOperation({
        action: 'add',
        cellType: 'edge',
        cellId: edge.id,
        data: {
          after: edge.toJSON()
        }
      });
    };

    const handleEdgeRemoved = ({ edge }: { edge: Edge }) => {
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
              after: { position: newPosition }
            }
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

      nodePositions.clear();
      edgeVertices.clear();
    };
  }, [graphInstance, recordOperation, onNodeRemoved]);

  const bindGraphEvents = (graph: X6Graph) => {
    const hideCtx = () => setContextMenuVisible(false);
    document.addEventListener('click', hideCtx);

    graph.on('scale', ({ sx }) => {
      setScale(sx);
    });

    const handleWheel = (e: WheelEvent) => {
      if (isZoomLockedRef.current) {
        return;
      }

      if (e.ctrlKey || e.metaKey) {
        return;
      }

      const eventTarget = e.target as HTMLElement | null;
      if (eventTarget?.closest('.chart-legend')) {
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

      nodeOriginalSizes.clear();
    };

    graph.on('node:contextmenu', ({ e, node }) => {
      e.preventDefault();
      if (!isEditModeRef.current) {
        return;
      }
      setContextMenuVisible(true);
      setContextMenuPosition({ x: e.clientX, y: e.clientY });
      setContextMenuNodeId(node.id);
      setContextMenuTargetType('node');
    });

    graph.on('node:click', ({ e }) => {
      if (e.shiftKey) {
        return;
      }
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

    graph.on('edge:connected', ({ edge }: { edge: Edge }) => {
      if (!edge || !isEditModeRef.current) return;

      const edgeData = edge.getData() || {};
      const arrowDirection = edgeData.arrowDirection || 'single';
      const styleConfig = edgeData.styleConfig;

      edge.setAttrs(getEdgeStyleWithConfig(arrowDirection, styleConfig).attrs);
      addEdgeTools(edge);

    });

    // 监听边的拐点变化并保存
    graph.on('edge:change:vertices', ({ edge }: { edge: Edge }) => {
      if (!edge || !isEditModeRef.current) return;

      const vertices = edge.getVertices();
      const currentData = edge.getData() || {};

      edge.setData({
        ...currentData,
        vertices: vertices
      }, { overwrite: true });
    });

    graph.on('edge:connecting', () => {
      if (isEditModeRef.current) {
        graph.getNodes().forEach((node: Node) => {
          showPorts(graph, node);
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

    graph.on('blank:click', () => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      setContextMenuVisible(false);

      resetAllStyles(graph);

      graph.cleanSelection();
      setSelectedCells([]);
    });

    graph.on('node:mouseenter', ({ node }) => {
      hideAllPorts(graph);
      hideAllEdgeTools(graph);
      showPorts(graph, node);
      const isSelected = selectedCells.includes(node.id);
      if (!isSelected) {
        highlightNode(node);
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

    /** 记录大小变更到操作历史（如果大小确实改变了） */
    const recordResizeIfChanged = (node: Node, updatedConfig: any) => {
      const originalState = nodeOriginalSizes.get(node.id);
      if (!originalState) return;

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
              attrs: originalState.attrs,
            },
            after: {
              size: { width: newSize.width, height: newSize.height },
              data: updatedConfig,
              attrs: node.getAttrs(),
            },
          },
        });
      }
      nodeOriginalSizes.delete(node.id);
    };

    const handleNodeSizeUpdate = (node: Node, isRealtime = false) => {
      const nodeData = node.getData();
      const size = node.getSize();

      // 记录开始大小变化时的原始大小
      if (isRealtime && !nodeOriginalSizes.has(node.id)) {
        nodeOriginalSizes.set(node.id, {
          size: { width: size.width, height: size.height },
          data: nodeData,
          attrs: node.getAttrs(),
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
      node.setData(updatedConfig, { overwrite: true });

      if (nodeData.type === 'icon' || nodeData.type === 'single-value') {
        if (!isRealtime) {
          updateNodeAttributes(node, updatedConfig);
          recordResizeIfChanged(node, updatedConfig);
        }
      } else if (nodeData.type === 'chart') {
        node.prop('ports', createPortConfig());
        if (!isRealtime) {
          recordResizeIfChanged(node, updatedConfig);
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
      ['top', 'bottom', 'left', 'right'].forEach((port) =>
        node.setPortProp(port, 'attrs/circle/opacity', 0)
      );
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

    // 初始化 minimap
    initMiniMap(graph);

    const cleanup = bindGraphEvents(graph);
    setGraphInstance(graph);

    return () => {
      cleanup();
      graph.dispose();
      setGraphInstance(null);
    };
  }, []);

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

  const addNewNode = useCallback((nodeConfig: TopologyNodeData, skipInitialFetch?: boolean) => {
    if (!graphInstance) {
      return null;
    }
    const nodeData = createNodeByType(nodeConfig);
    const { valueConfig } = nodeConfig || {};
    const addedNode = graphInstance.addNode(nodeData as any);
    if (nodeConfig.type === 'single-value') {
      adjustSingleValueNodeSize(addedNode, nodeConfig.name || '');
    }
    if (!skipInitialFetch && nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length) {
      startLoadingAnimation(addedNode);
      updateSingleNodeData({ ...nodeConfig, id: addedNode.id });
    } else if (skipInitialFetch && nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length) {
      startLoadingAnimation(addedNode);
    }
    return addedNode.id;
  }, [graphInstance, updateSingleNodeData, startLoadingAnimation]);

  function getUpdatedNodeConfig(editingNode: TopologyNodeData, values: NodeConfigFormValues): TopologyNodeData {
    const { valueConfig, styleConfig } = editingNode || {};
    return {
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
        compare: values.compare ?? valueConfig?.compare,
        selectedFields: values.selectedFields || valueConfig?.selectedFields,
        chartType: values.chartType || valueConfig?.chartType,
        dataSource: values.dataSource || valueConfig?.dataSource,
        dataSourceParams: values.dataSourceParams || valueConfig?.dataSourceParams,
        topNLabelField: values.topNLabelField ?? valueConfig?.topNLabelField,
        topNValueField: values.topNValueField ?? valueConfig?.topNValueField,
      },
      styleConfig: mergeStyleConfig(values, styleConfig, [
        'textColor', 'fontSize', 'fontWeight', 'backgroundColor',
        'borderColor', 'borderWidth', 'iconPadding', 'renderEffect',
        'width', 'height', 'lineType', 'shapeType',
        'nameColor', 'nameFontSize', 'thresholdColors',
      ]),
    } as TopologyNodeData;
  }

  const handleNodeUpdate = useCallback(async (
    values: NodeConfigFormValues,
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    namespaceId?: number
  ) => {
    if (!values) return;
    const editingNode = state.editingNodeData;
    if (!editingNode || !graphInstance) return;
    try {
      const updatedConfig = getUpdatedNodeConfig(editingNode, values);
      if (!updatedConfig.id) return;
      const node = graphInstance.getCellById(updatedConfig.id);
      if (!node || !node.isNode()) return;
      updateNodeAttributes(node as Node, updatedConfig);
      if (
        updatedConfig.type === 'single-value' &&
        updatedConfig.valueConfig?.dataSource &&
        updatedConfig.valueConfig?.selectedFields?.length
      ) {
        node.setData({ ...node.getData(), isLoading: true, hasError: false }, { overwrite: true });
        startLoadingAnimation(node as Node);
        updateSingleNodeData(updatedConfig, unifiedFilterValues, filterDefinitions, namespaceId);
      }
      state.setNodeEditVisible(false);
      state.setEditingNodeData(null);
    } catch (error) {
      console.error('节点更新失败:', error);
    }
  }, [graphInstance, updateSingleNodeData, state]);

  const handleViewConfigConfirm = useCallback((
    values: ViewConfigFormValues,
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number
  ) => {
    if (state.editingNodeData && graphInstance) {
      const node = graphInstance.getCellById(
        state.editingNodeData.id
      );
      if (node) {
        const valueConfig = buildValueConfig(values);
        const updatedData = {
          ...state.editingNodeData,
          name: values.name,
          valueConfig,
          isLoading: !!values.dataSource,
          hasError: false,
        };
        node.setData(updatedData, { overwrite: true });

        if (state.editingNodeData.type === 'chart' && values.dataSource) {
          const dataSource = dataSources?.find(
            (ds) => ds.id === values.dataSource
          );
          dataOperations.loadChartNodeData(
            state.editingNodeData.id,
            updatedData.valueConfig,
            unifiedFilterValues,
            filterDefinitions,
            dataSource,
            namespaceId
          );
        }
      }
    }
    state.setViewConfigVisible(false);
  }, [graphInstance, state, dataOperations]);


  const handleAddChartNode = useCallback(async (values: ViewConfigFormValues, skipInitialFetch?: boolean) => {
    if (!graphInstance) {
      return null;
    }
    const valueConfig = buildValueConfig(values, true);
    const nodeConfig: TopologyNodeData = {
      id: `node_${uuidv4()}`,
      type: 'chart',
      name: values.name,
      description: values.description || '',
      position: state.editingNodeData.position,
      styleConfig: {},
      valueConfig,
    };
    const nodeId = addNewNode(nodeConfig);
    if (!skipInitialFetch && nodeConfig.valueConfig?.dataSource && nodeId) {
      dataOperations.loadChartNodeData(nodeId, nodeConfig.valueConfig);
    }
    return { nodeId, valueConfig: nodeConfig.valueConfig };
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
      }
    }
  }, [state, graphInstance]);



  const handleNodeEditClose = useCallback(() => {
    state.setNodeEditVisible(false);
    state.setEditingNodeData(null);
  }, [state]);

  // 刷新所有单值节点
  const refreshAllSingleValueNodes = useCallback((
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
    dataSources?: DatasourceItem[],
    shouldRefreshNode?: (nodeData: TopologyNodeData, dataSource?: DatasourceItem) => boolean,
  ) => {
    if (!graphInstance) return;

    const nodes = graphInstance.getNodes();
    nodes.forEach((node: Node) => {
      const nodeData = node.getData();
      if (nodeData.type === 'single-value' && nodeData.valueConfig?.dataSource && nodeData.valueConfig?.selectedFields?.length) {
        const dataSource = dataSources?.find(
          (source) => source.id === nodeData.valueConfig.dataSource,
        );
        if (shouldRefreshNode && !shouldRefreshNode(nodeData, dataSource)) {
          return;
        }
        updateSingleNodeData(nodeData, unifiedFilterValues, filterDefinitions, namespaceId);
      }
    });
  }, [graphInstance, updateSingleNodeData]);

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
    refreshAllSingleValueNodes,
    updateSingleNodeData,
    ...dataOperations,
  };
};
