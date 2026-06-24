import { useCallback, useEffect } from 'react';
import type { MutableRefObject } from 'react';
import type { Edge, Graph as X6Graph, Node } from '@antv/x6';
import { Graph } from '@antv/x6';
import { MiniMap } from '@antv/x6-plugin-minimap';
import { Selection } from '@antv/x6-plugin-selection';
import { Transform } from '@antv/x6-plugin-transform';
import { COLORS, SPACING } from '../constants/nodeDefaults';
import { registerEdges } from '../utils/registerEdge';
import { registerNodes, updateNodeAttributes } from '../utils/registerNode';
import {
  addEdgeTools,
  createPortConfig,
  getEdgeStyleWithConfig,
  hideAllEdgeTools,
  hideAllPorts,
  showEdgeTools,
  showPorts,
} from '../utils/topologyUtils';
import type { useGraphHistory } from './useGraphHistory';
import type { useTopologyState } from './useTopologyState';

interface UseGraphInitializerParams {
  containerRef: React.RefObject<HTMLDivElement | null>;
  minimapContainerRef?: React.RefObject<HTMLDivElement | null>;
  state: ReturnType<typeof useTopologyState>;
  history: ReturnType<typeof useGraphHistory>;
  selectedCells: string[];
  onNodeRemoved?: () => void;
  isZoomLockedRef: MutableRefObject<boolean>;
}

export const useGraphInitializer = ({
  containerRef,
  minimapContainerRef,
  state,
  history,
  selectedCells,
  onNodeRemoved,
  isZoomLockedRef,
}: UseGraphInitializerParams) => {
  const {
    graphInstance,
    setGraphInstance,
    setScale,
    setSelectedCells,
    isEditModeRef,
    setContextMenuVisible,
    setContextMenuPosition,
    setContextMenuNodeId,
    setContextMenuTargetType,
    setCurrentEdgeData,
  } = state;

  const {
    resetAllStyles,
    highlightCell,
    highlightNode,
    resetNodeStyle,
    recordOperation,
  } = history;

  const initMiniMap = useCallback(
    (graph: X6Graph) => {
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
          }),
        );
      }
    },
    [minimapContainerRef],
  );

  useEffect(() => {
    if (!graphInstance) return;

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

    const nodePositions = new Map<string, any>();
    const edgeVertices = new Map<string, any>();

    const handleNodeMoveStart = ({ node }: { node: Node }) => {
      nodePositions.set(node.id, node.getPosition());
    };

    const handleNodeMoved = ({ node }: { node: Node }) => {
      const oldPosition = nodePositions.get(node.id);
      if (oldPosition) {
        const newPosition = node.getPosition();
        if (
          oldPosition.x !== newPosition.x ||
          oldPosition.y !== newPosition.y
        ) {
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

    graphInstance.on('node:added', handleNodeAdded);
    graphInstance.on('node:removed', handleNodeRemoved);
    graphInstance.on('edge:added', handleEdgeAdded);
    graphInstance.on('edge:removed', handleEdgeRemoved);

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
          center: { x: clientX, y: clientY },
        });
      } else {
        graph.zoom(newScale, { absolute: true });
      }
    };

    if (containerRef.current) {
      containerRef.current.addEventListener('wheel', handleWheel, {
        passive: false,
      });
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
          styleConfig: edgeData.styleConfig || {
            lineColor: COLORS.EDGE.DEFAULT,
            lineWidth: SPACING.STROKE_WIDTH.THIN,
            lineStyle: 'line',
            enableAnimation: false,
          },
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

    graph.on('edge:change:vertices', ({ edge }: { edge: Edge }) => {
      if (!edge || !isEditModeRef.current) return;

      const vertices = edge.getVertices();
      const currentData = edge.getData() || {};

      edge.setData(
        {
          ...currentData,
          vertices: vertices,
        },
        { overwrite: true },
      );
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

    const nodeOriginalSizes = new Map<string, any>();

    const recordResizeIfChanged = (node: Node, updatedConfig: any) => {
      const originalState = nodeOriginalSizes.get(node.id);
      if (!originalState) return;

      const newSize = node.getSize();
      if (
        originalState.size.width !== newSize.width ||
        originalState.size.height !== newSize.height
      ) {
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
        node.setPortProp(port, 'attrs/circle/opacity', 0),
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
        minScale: 0.05,
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
              lineWidth: SPACING.STROKE_WIDTH.THIN,
              lineStyle: 'line',
              enableAnimation: false,
            }),
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
      }),
    );

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
            return (
              nodeData?.type === 'icon' || nodeData?.type === 'single-value'
            );
          },
        },
        rotating: false,
      }),
    );

    initMiniMap(graph);

    const cleanup = bindGraphEvents(graph);
    setGraphInstance(graph);

    return () => {
      cleanup();
      graph.dispose();
      setGraphInstance(null);
    };
  }, []);
};
