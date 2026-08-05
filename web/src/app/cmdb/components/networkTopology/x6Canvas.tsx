'use client';

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Button, Segmented, Tooltip } from 'antd';
import {
  DownloadOutlined,
  FullscreenOutlined,
  ReloadOutlined,
  RetweetOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { Graph } from '@antv/x6';
import { Export } from '@antv/x6-plugin-export';
import {
  XFlow,
  XFlowGraph,
  Grid,
  Minimap,
  useGraphStore,
  useGraphInstance,
} from '@antv/xflow';
import { NETWORK_TOPO_VISUAL } from './x6Visual';
import { normalizeManualEdgeVertices } from './edgeGeometry';

export interface NetworkTopologyX6GraphData {
  nodes: any[];
  edges: any[];
}

export interface NetworkTopologyToolbarConfig {
  prefix?: React.ReactNode;
  align?: 'left' | 'right' | 'split';
  layoutMode?: string;
  layoutOptions?: Array<{ label: React.ReactNode; value: string }>;
  onLayoutChange?: (value: string) => void;
  labels?: {
    zoomOut?: React.ReactNode;
    zoomIn?: React.ReactNode;
    fitView?: React.ReactNode;
    exportImage?: React.ReactNode;
    refresh?: React.ReactNode;
    resetLayout?: React.ReactNode;
  };
  showZoom?: boolean;
  showFitView?: boolean;
  showExport?: boolean;
  showRefresh?: boolean;
  showResetLayout?: boolean;
  onResetLayout?: () => void;
  exportFileName?: string;
  exportDisabled?: boolean;
  refreshLoading?: boolean;
  onRefresh?: () => void;
}

interface NetworkTopologyX6CanvasProps {
  data: NetworkTopologyX6GraphData;
  centerId?: string;
  editing?: boolean;
  nodeMovable?: boolean;
  /** 允许拖动边折点形成折线；仅布局编辑态开启 */
  edgeVerticesEditable?: boolean;
  graphRef?: React.MutableRefObject<Graph | null>;
  minimap?: {
    width: number;
    height: number;
    style?: React.CSSProperties;
  };
  fitViewOptions?: {
    padding?: number;
    maxScale?: number;
  };
  fitViewKey?: string | number;
  toolbar?: NetworkTopologyToolbarConfig;
  onGraphReady?: (graph: Graph | null) => void;
  onNodeMoved?: (nodeId: string, position: { x: number; y: number }) => void;
  onEdgeVerticesChanged?: (
    edgeId: string,
    vertices: Array<{ x: number; y: number }>,
  ) => void;
  onNodeClick?: (nodeId: string) => void;
  onNodeMouseEnter?: (nodeId: string, event: MouseEvent) => void;
  onNodeMouseMove?: (nodeId: string, event: MouseEvent) => void;
  onNodeMouseLeave?: (nodeId: string) => void;
  onNodeContextMenu?: (nodeId: string, event: MouseEvent) => void;
  onEdgeMouseEnter?: (edgeId: string, event: MouseEvent) => void;
  onEdgeMouseMove?: (edgeId: string, event: MouseEvent) => void;
  onEdgeMouseLeave?: (edgeId: string) => void;
  onEdgeContextMenu?: (edgeId: string, event: MouseEvent) => void;
  onBlankClick?: () => void;
  onBlankContextMenu?: (event: MouseEvent) => void;
}

const edgeVertexTool = {
  name: 'vertices',
  args: {
    attrs: {
      fill: 'var(--color-primary)',
      stroke: 'var(--color-bg)',
      strokeWidth: 1,
      r: 5,
      cursor: 'move',
    },
    snapRadius: 20,
    addable: true,
    removable: true,
    removeRedundancies: true,
  },
};

const normalizeEdgeVertices = (
  vertices: ReadonlyArray<{ x: number; y: number }> | undefined,
) =>
  (vertices ?? [])
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
    .map((point) => ({ x: point.x, y: point.y }));

const syncEdgeVertexTools = (graph: Graph, enabled: boolean) => {
  graph.getEdges().forEach((edge) => {
    edge.removeTools();
    if (enabled) {
      edge.addTools([edgeVertexTool]);
    }
  });
};

const NODE_WIDTH = NETWORK_TOPO_VISUAL.node.width;
const NODE_HEIGHT = NETWORK_TOPO_VISUAL.node.height;
const DEVICE_NODE_SHAPE = 'topo-network-device';
const DYNAMIC_COLOR_PATTERN = /(?:var|color-mix)\(/;

const inlineDynamicSvgStyles = (source: SVGSVGElement, target: SVGSVGElement) => {
  const sourceElements = [source, ...Array.from(source.querySelectorAll('*'))];
  const targetElements = [target, ...Array.from(target.querySelectorAll('*'))];

  targetElements.forEach((targetElement, index) => {
    const sourceElement = sourceElements[index];
    if (!sourceElement) return;

    const computedStyle = window.getComputedStyle(sourceElement);
    Array.from(targetElement.attributes).forEach(({ name, value }) => {
      if (!DYNAMIC_COLOR_PATTERN.test(value)) return;

      const computedValue = computedStyle.getPropertyValue(name).trim();
      if (computedValue) targetElement.setAttribute(name, computedValue);
    });
  });
};

const toolbarWrapperStyle: React.CSSProperties = {
  position: 'absolute',
  top: 10,
  right: 10,
  zIndex: 20,
  display: 'flex',
  alignItems: 'center',
  gap: 14,
};

const toolbarSplitWrapperStyle: React.CSSProperties = {
  position: 'absolute',
  inset: '16px 16px auto 8px',
  zIndex: 20,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  pointerEvents: 'none',
};

const toolbarShellStyle: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  alignItems: 'center',
  padding: 4,
  border: '1px solid rgba(219, 232, 246, 0.92)',
  borderRadius: 8,
  background: 'rgba(255, 255, 255, 0.9)',
  boxShadow: '0 10px 24px rgba(37, 72, 111, 0.09)',
  backdropFilter: 'blur(8px)',
  pointerEvents: 'auto',
};

const toolbarPrefixStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  pointerEvents: 'auto',
};

const toolbarActionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 4,
  alignItems: 'center',
};

const buildStructureKey = (data: NetworkTopologyX6GraphData) =>
  JSON.stringify({
    // 故意不含 x/y/vertices：几何编辑只 patch，避免 initData 重置视口与交互态
    nodes: data.nodes.map((node) => [
      node.id,
      node.width,
      node.height,
      node.shape,
      node.attrs?.img?.width,
      node.attrs?.lbl?.fontSize,
      node.attrs?.lbl?.y,
      node.attrs?.alertBadgeText?.text,
    ]),
    edges: data.edges.map((edge) => [
      edge.id,
      edge.source,
      edge.target,
      Array.isArray(edge.labels)
        ? edge.labels.map((label: any) => [
            label?.position,
            label?.attrs?.txt?.text,
          ])
        : null,
    ]),
  });

const fitGraphToView = (
  graph: Graph,
  options?: NetworkTopologyX6CanvasProps['fitViewOptions']
) => {
  graph.zoomToFit({
    padding: options?.padding ?? 112,
    maxScale: options?.maxScale ?? 1.12,
  });
};

const applyGraphInteracting = (
  graph: Graph,
  nodeMovable: boolean,
) => {
  graph.options.interacting = {
    ...(typeof graph.options.interacting === 'object' ? graph.options.interacting : {}),
    nodeMovable,
    edgeMovable: false,
  };
};

const ensureGraphPanning = (graph: Graph) => {
  const panning = (graph as any).enablePanning;
  if (typeof panning === 'function') {
    panning.call(graph);
    return;
  }
  if (typeof (graph as any).setPanning === 'function') {
    (graph as any).setPanning(true);
  }
};

const patchGraphAttrs = (graph: Graph, data: NetworkTopologyX6GraphData) => {
  data.nodes.forEach((node) => {
    const cell = graph.getCellById(node.id) as any;
    if (!cell) return;
    if (
      Number.isFinite(node.x) &&
      Number.isFinite(node.y) &&
      typeof cell.setPosition === 'function'
    ) {
      const current = cell.getPosition?.() || { x: 0, y: 0 };
      if (
        Math.abs(current.x - node.x) > 0.5 ||
        Math.abs(current.y - node.y) > 0.5
      ) {
        cell.setPosition(node.x, node.y);
      }
    }
    if (cell.setAttrs) {
      cell.setAttrs(node.attrs);
    } else {
      cell.attr?.(node.attrs);
    }
    cell.setData?.(node.data);
  });

  data.edges.forEach((edge) => {
    const cell = graph.getCellById(edge.id) as any;
    if (!cell) return;
    if (cell.setAttrs) {
      cell.setAttrs(edge.attrs);
    } else {
      cell.attr?.(edge.attrs);
    }
    if (edge.connector && cell.setConnector) {
      cell.setConnector(edge.connector);
    }
    if (edge.vertices !== undefined && cell.setVertices) {
      cell.setVertices(edge.vertices || []);
    }
    cell.setLabels?.(edge.labels);
  });
};

export const ensureNetworkTopologyDeviceNodeRegistered = () => {
  Graph.registerNode(
    DEVICE_NODE_SHAPE,
    {
      inherit: 'rect',
      markup: [
        { tagName: 'rect', selector: 'pulseHalo' },
        { tagName: 'rect', selector: 'body' },
        { tagName: 'rect', selector: 'iconColumn' },
        { tagName: 'line', selector: 'divider' },
        { tagName: 'rect', selector: 'iconPlate' },
        { tagName: 'image', selector: 'img' },
        { tagName: 'circle', selector: 'statusDot' },
        { tagName: 'circle', selector: 'alertBadge' },
        { tagName: 'text', selector: 'alertBadgeText' },
        { tagName: 'text', selector: 'lbl' },
        { tagName: 'text', selector: 'subLbl' },
      ],
      attrs: {
        pulseHalo: {
          x: -6,
          y: -6,
          width: NODE_WIDTH + 12,
          height: NODE_HEIGHT + 12,
          rx: NETWORK_TOPO_VISUAL.node.radius + 6,
          ry: NETWORK_TOPO_VISUAL.node.radius + 6,
          fill: 'none',
          stroke: '#ff4d4f',
          strokeWidth: 2,
          opacity: 0,
          style: { pointerEvents: 'none' },
        },
        body: {
          rx: NETWORK_TOPO_VISUAL.node.radius,
          ry: NETWORK_TOPO_VISUAL.node.radius,
          cursor: 'pointer',
          ...NETWORK_TOPO_VISUAL.node.defaultBody,
        },
        iconColumn: {
          x: 1,
          y: 1,
          width: NETWORK_TOPO_VISUAL.node.iconColumnWidth - 1,
          height: NODE_HEIGHT - 2,
          rx: NETWORK_TOPO_VISUAL.node.radius - 1,
          ry: NETWORK_TOPO_VISUAL.node.radius - 1,
          fill: '#f7fbff',
          stroke: 'transparent',
          strokeWidth: 0,
          style: { pointerEvents: 'none' },
        },
        divider: {
          x1: NETWORK_TOPO_VISUAL.node.iconColumnWidth,
          y1: 9,
          x2: NETWORK_TOPO_VISUAL.node.iconColumnWidth,
          y2: NODE_HEIGHT - 9,
          stroke: '#e1ebf6',
          strokeWidth: 1,
          style: { pointerEvents: 'none' },
        },
        iconPlate: {
          x: (NETWORK_TOPO_VISUAL.node.iconColumnWidth - NETWORK_TOPO_VISUAL.node.iconPlateSize) / 2,
          y: (NODE_HEIGHT - NETWORK_TOPO_VISUAL.node.iconPlateSize) / 2,
          width: NETWORK_TOPO_VISUAL.node.iconPlateSize,
          height: NETWORK_TOPO_VISUAL.node.iconPlateSize,
          rx: 11,
          ry: 11,
          fill: NETWORK_TOPO_VISUAL.node.iconPlate.fill,
          stroke: NETWORK_TOPO_VISUAL.node.iconPlate.stroke,
          strokeWidth: 1,
          style: { pointerEvents: 'none' },
        },
        img: {
          width: NETWORK_TOPO_VISUAL.node.iconSize,
          height: NETWORK_TOPO_VISUAL.node.iconSize,
          x: (NETWORK_TOPO_VISUAL.node.iconColumnWidth - NETWORK_TOPO_VISUAL.node.iconSize) / 2,
          y: (NODE_HEIGHT - NETWORK_TOPO_VISUAL.node.iconSize) / 2,
          opacity: 0.95,
          style: { pointerEvents: 'none' },
        },
        statusDot: {
          cx: NODE_WIDTH - 18,
          cy: 16,
          r: 4,
          fill: '#55d6ad',
          stroke: '#eafff7',
          strokeWidth: 2,
          style: { pointerEvents: 'none' },
        },
        alertBadge: {
          cx: NODE_WIDTH - 8,
          cy: 6,
          r: 15,
          fill: '#ff4d4f',
          stroke: '#fff',
          strokeWidth: 2.5,
          opacity: 0,
          style: { pointerEvents: 'none' },
        },
        alertBadgeText: {
          refX: NODE_WIDTH - 8,
          refY: 6,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: 18,
          fontWeight: 800,
          fill: '#fff',
          opacity: 0,
          style: { pointerEvents: 'none' },
        },
        lbl: {
          refX: NETWORK_TOPO_VISUAL.node.label.x,
          refY: 0.41,
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 14,
          fontWeight: 600,
          fill: NETWORK_TOPO_VISUAL.node.label.fill,
          textWrap: {
            width: NETWORK_TOPO_VISUAL.node.label.width,
            height: 22,
            ellipsis: true,
          },
          style: { pointerEvents: 'none' },
        },
        subLbl: {
          refX: NETWORK_TOPO_VISUAL.node.label.x,
          refY: 0.67,
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 12,
          fontWeight: 400,
          fill: NETWORK_TOPO_VISUAL.node.label.subFill,
          textWrap: {
            width: NETWORK_TOPO_VISUAL.node.label.width,
            height: 18,
            ellipsis: true,
          },
          style: { pointerEvents: 'none' },
        },
      },
    },
    true
  );
};

const GraphLoader: React.FC<NetworkTopologyX6CanvasProps> = ({
  data,
  graphRef,
  fitViewOptions,
  fitViewKey,
  onGraphReady,
  nodeMovable = true,
  edgeVerticesEditable = false,
  onNodeMoved,
  onEdgeVerticesChanged,
  onNodeClick,
  onNodeMouseEnter,
  onNodeMouseMove,
  onNodeMouseLeave,
  onNodeContextMenu,
  onEdgeMouseEnter,
  onEdgeMouseMove,
  onEdgeMouseLeave,
  onEdgeContextMenu,
  onBlankClick,
  onBlankContextMenu,
}) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();
  const structureKey = useMemo(() => buildStructureKey(data), [data]);
  const structureKeyRef = useRef('');
  const initializedRef = useRef(false);
  const fitViewKeyRef = useRef<string | number | undefined>(undefined);
  const pendingVerticesRef = useRef(
    new Map<string, Array<{ x: number; y: number }>>(),
  );
  const onNodeMovedRef = useRef(onNodeMoved);
  const onEdgeVerticesChangedRef = useRef(onEdgeVerticesChanged);
  onNodeMovedRef.current = onNodeMoved;
  onEdgeVerticesChangedRef.current = onEdgeVerticesChanged;

  useEffect(() => {
    ensureNetworkTopologyDeviceNodeRegistered();
    if (!initializedRef.current || structureKeyRef.current !== structureKey) {
      initializedRef.current = true;
      structureKeyRef.current = structureKey;
      initData({ nodes: data.nodes, edges: data.edges });
      if (graph) {
        applyGraphInteracting(graph, nodeMovable);
        ensureGraphPanning(graph);
        syncEdgeVertexTools(graph, edgeVerticesEditable);
      }
      return;
    }
    if (graph) {
      patchGraphAttrs(graph, data);
      applyGraphInteracting(graph, nodeMovable);
      ensureGraphPanning(graph);
      syncEdgeVertexTools(graph, edgeVerticesEditable);
    }
  }, [graph, initData, data, structureKey, nodeMovable, edgeVerticesEditable]);

  useEffect(() => {
    if (!graph) return undefined;
    if (graphRef) graphRef.current = graph;
    onGraphReady?.(graph);
    applyGraphInteracting(graph, nodeMovable);
    ensureGraphPanning(graph);
    if (!graph.getPlugin('export')) {
      graph.use(new Export());
    }
    syncEdgeVertexTools(graph, edgeVerticesEditable);
    return () => {
      if (graphRef) graphRef.current = null;
      onGraphReady?.(null);
    };
  }, [graph, graphRef, nodeMovable, edgeVerticesEditable, onGraphReady]);

  useEffect(() => {
    if (!graph) return undefined;
    // 只在拓扑身份 / 显式 fitViewKey 变化时适配视口，几何拖拽绝不触发
    const nextKey = fitViewKey ?? structureKey;
    if (fitViewKeyRef.current === nextKey) {
      return undefined;
    }
    fitViewKeyRef.current = nextKey;
    const timer = window.setTimeout(() => {
      try {
        fitGraphToView(graph, fitViewOptions);
      } catch {
        // ignore graph warm-up timing
      }
    }, 60);
    return () => window.clearTimeout(timer);
  }, [
    graph,
    fitViewKey,
    structureKey,
    fitViewOptions?.maxScale,
    fitViewOptions?.padding,
  ]);

  useEffect(() => {
    if (!graph) return undefined;
    const flushPendingVertices = () => {
      if (!pendingVerticesRef.current.size) return;
      const pending = pendingVerticesRef.current;
      pendingVerticesRef.current = new Map();
      pending.forEach((vertices, edgeId) => {
        const edge = graph.getCellById(edgeId) as any;
        let nextVertices = vertices;
        if (edge?.isEdge?.() || edge?.getSourcePoint) {
          const source = edge.getSourcePoint?.();
          const target = edge.getTargetPoint?.();
          if (
            source &&
            target &&
            Number.isFinite(source.x) &&
            Number.isFinite(source.y) &&
            Number.isFinite(target.x) &&
            Number.isFinite(target.y)
          ) {
            nextVertices = normalizeManualEdgeVertices(source, target, vertices);
            if (
              nextVertices.length !== vertices.length ||
              nextVertices.some(
                (point, index) =>
                  Math.abs(point.x - vertices[index].x) > 0.5 ||
                  Math.abs(point.y - vertices[index].y) > 0.5,
              )
            ) {
              edge.setVertices?.(nextVertices);
            }
          }
        }
        onEdgeVerticesChangedRef.current?.(edgeId, nextVertices);
      });
      // 折点工具拖拽期间可能临时关闭平移；结束后强制恢复
      ensureGraphPanning(graph);
      applyGraphInteracting(graph, nodeMovable);
    };
    const handleNodeClick = ({ node }: { node: any }) => onNodeClick?.(String(node.id));
    const handleNodeEnter = ({ node, e }: { node: any; e: MouseEvent }) => onNodeMouseEnter?.(String(node.id), e);
    const handleNodeMove = ({ node, e }: { node: any; e: MouseEvent }) => onNodeMouseMove?.(String(node.id), e);
    const handleNodeLeave = ({ node }: { node: any }) => onNodeMouseLeave?.(String(node.id));
    const handleNodeContext = ({ node, e }: { node: any; e: MouseEvent }) => {
      e.preventDefault();
      onNodeContextMenu?.(String(node.id), e);
    };
    const handleNodeMoved = ({ node }: { node: any }) => {
      const position = node.getPosition?.() || { x: node.getBBox?.().x, y: node.getBBox?.().y };
      if (!Number.isFinite(position?.x) || !Number.isFinite(position?.y)) return;
      onNodeMovedRef.current?.(String(node.id), { x: position.x, y: position.y });
      ensureGraphPanning(graph);
    };
    const handleEdgeEnter = ({ edge, e }: { edge: any; e: MouseEvent }) =>
      onEdgeMouseEnter?.(String(edge.id), e);
    const handleEdgeMove = ({ edge, e }: { edge: any; e: MouseEvent }) =>
      onEdgeMouseMove?.(String(edge.id), e);
    const handleEdgeLeave = ({ edge }: { edge: any }) =>
      onEdgeMouseLeave?.(String(edge.id));
    const handleEdgeContext = ({ edge, e }: { edge: any; e: MouseEvent }) => {
      e.preventDefault();
      onEdgeContextMenu?.(String(edge.id), e);
    };
    const handleEdgeVertices = ({ edge }: { edge: any }) => {
      if (!edgeVerticesEditable) return;
      const vertices = normalizeEdgeVertices(edge.getVertices?.());
      pendingVerticesRef.current.set(String(edge.id), vertices);
    };
    const handleBlankClick = () => onBlankClick?.();
    const handleBlankContext = ({ e }: { e: MouseEvent }) => {
      e.preventDefault();
      onBlankContextMenu?.(e);
    };
    graph.on('node:click', handleNodeClick);
    graph.on('node:mouseenter', handleNodeEnter);
    graph.on('node:mousemove', handleNodeMove);
    graph.on('node:mouseleave', handleNodeLeave);
    graph.on('node:contextmenu', handleNodeContext);
    graph.on('node:moved', handleNodeMoved);
    graph.on('edge:mouseenter', handleEdgeEnter);
    graph.on('edge:mousemove', handleEdgeMove);
    graph.on('edge:mouseleave', handleEdgeLeave);
    graph.on('edge:contextmenu', handleEdgeContext);
    graph.on('edge:change:vertices', handleEdgeVertices);
    graph.on('cell:mouseup', flushPendingVertices);
    graph.on('blank:mouseup', flushPendingVertices);
    graph.on('blank:click', handleBlankClick);
    graph.on('blank:contextmenu', handleBlankContext);
    window.addEventListener('mouseup', flushPendingVertices);
    window.addEventListener('pointerup', flushPendingVertices);
    return () => {
      // 卸载时只恢复交互，不再 flush，避免 cleanup 触发额外写回/重建
      window.removeEventListener('mouseup', flushPendingVertices);
      window.removeEventListener('pointerup', flushPendingVertices);
      graph.off('node:click', handleNodeClick);
      graph.off('node:mouseenter', handleNodeEnter);
      graph.off('node:mousemove', handleNodeMove);
      graph.off('node:mouseleave', handleNodeLeave);
      graph.off('node:contextmenu', handleNodeContext);
      graph.off('node:moved', handleNodeMoved);
      graph.off('edge:mouseenter', handleEdgeEnter);
      graph.off('edge:mousemove', handleEdgeMove);
      graph.off('edge:mouseleave', handleEdgeLeave);
      graph.off('edge:contextmenu', handleEdgeContext);
      graph.off('edge:change:vertices', handleEdgeVertices);
      graph.off('cell:mouseup', flushPendingVertices);
      graph.off('blank:mouseup', flushPendingVertices);
      graph.off('blank:click', handleBlankClick);
      graph.off('blank:contextmenu', handleBlankContext);
      ensureGraphPanning(graph);
    };
  }, [
    graph,
    edgeVerticesEditable,
    nodeMovable,
    onBlankClick,
    onBlankContextMenu,
    onEdgeContextMenu,
    onEdgeMouseEnter,
    onEdgeMouseLeave,
    onEdgeMouseMove,
    onNodeClick,
    onNodeContextMenu,
    onNodeMouseEnter,
    onNodeMouseLeave,
    onNodeMouseMove,
  ]);

  return null;
};

const NetworkTopologyX6Canvas: React.FC<NetworkTopologyX6CanvasProps> = ({
  data,
  graphRef,
  fitViewOptions,
  toolbar,
  onGraphReady,
  minimap = {
    width: 200,
    height: 120,
    style: NETWORK_TOPO_VISUAL.minimap,
  },
  ...loaderProps
}) => {
  const internalGraphRef = useRef<Graph | null>(null);
  const hasGraph = data.nodes.length > 0;

  const fitView = useCallback(() => {
    if (internalGraphRef.current) {
      fitGraphToView(internalGraphRef.current, fitViewOptions);
    }
  }, [fitViewOptions]);

  const handleExport = useCallback(() => {
    const graph = internalGraphRef.current;
    if (!graph) return;
    graph.exportPNG(toolbar?.exportFileName || 'network-topology', {
      padding: 40,
      backgroundColor: '#ffffff',
      copyStyles: false,
      beforeSerialize: (svg) => {
        inlineDynamicSvgStyles(graph.view.svg, svg);
        return svg;
      },
    });
  }, [toolbar?.exportFileName]);

  const handleGraphReady = useCallback(
    (graph: Graph | null) => {
      internalGraphRef.current = graph;
      if (graphRef) graphRef.current = graph;
      onGraphReady?.(graph);
    },
    [graphRef, onGraphReady],
  );

  const toolbarLabels = toolbar?.labels || {};
  const showZoom = toolbar && toolbar.showZoom !== false;
  const showFitView = toolbar && toolbar.showFitView !== false;
  const showExport = toolbar && toolbar.showExport !== false;
  const showRefresh = toolbar && toolbar.showRefresh !== false && toolbar.onRefresh;
  const showResetLayout =
    toolbar && toolbar.showResetLayout && toolbar.onResetLayout;
  const toolbarBody = toolbar && (
    <div style={toolbarShellStyle}>
      {toolbar.layoutOptions && toolbar.layoutMode && toolbar.onLayoutChange && (
        <Segmented
          value={toolbar.layoutMode}
          options={toolbar.layoutOptions}
          onChange={(value) => toolbar.onLayoutChange?.(String(value))}
        />
      )}
      <div style={toolbarActionsStyle}>
        {showResetLayout && (
          <Tooltip title={toolbarLabels.resetLayout}>
            <Button
              size="small"
              aria-label={String(toolbarLabels.resetLayout || '')}
              icon={<RetweetOutlined />}
              disabled={!hasGraph}
              onClick={toolbar.onResetLayout}
            />
          </Tooltip>
        )}
        {showZoom && (
          <>
            <Tooltip title={toolbarLabels.zoomOut}>
              <Button
                size="small"
                aria-label={String(toolbarLabels.zoomOut || '')}
                icon={<ZoomOutOutlined />}
                disabled={!hasGraph}
                onClick={() => internalGraphRef.current?.zoom(-0.1)}
              />
            </Tooltip>
            <Tooltip title={toolbarLabels.zoomIn}>
              <Button
                size="small"
                aria-label={String(toolbarLabels.zoomIn || '')}
                icon={<ZoomInOutlined />}
                disabled={!hasGraph}
                onClick={() => internalGraphRef.current?.zoom(0.1)}
              />
            </Tooltip>
          </>
        )}
        {showFitView && (
          <Tooltip title={toolbarLabels.fitView}>
            <Button
              size="small"
              aria-label={String(toolbarLabels.fitView || '')}
              icon={<FullscreenOutlined />}
              disabled={!hasGraph}
              onClick={fitView}
            />
          </Tooltip>
        )}
        {showExport && (
          <Tooltip title={toolbarLabels.exportImage}>
            <Button
              size="small"
              aria-label={String(toolbarLabels.exportImage || '')}
              icon={<DownloadOutlined />}
              disabled={!hasGraph || toolbar.exportDisabled}
              onClick={handleExport}
            />
          </Tooltip>
        )}
        {showRefresh && (
          <Tooltip title={toolbarLabels.refresh}>
            <Button
              size="small"
              aria-label={String(toolbarLabels.refresh || '')}
              icon={<ReloadOutlined />}
              loading={toolbar.refreshLoading}
              onClick={toolbar.onRefresh}
            />
          </Tooltip>
        )}
      </div>
    </div>
  );
  const toolbarPrefix = toolbar?.prefix && (
    <div style={toolbarPrefixStyle}>{toolbar.prefix}</div>
  );

  return (
    <>
      <style>
        {`
          @keyframes networkTopologyCriticalPulse {
            0% { opacity: 0.36; transform: scale(1); }
            70% { opacity: 0; transform: scale(1.16); }
            100% { opacity: 0; transform: scale(1.16); }
          }
      `}
    </style>
      {toolbar?.align === 'split' && (
        <div style={toolbarSplitWrapperStyle}>
          {toolbarBody}
          {toolbarPrefix}
        </div>
      )}
      {toolbar && toolbar.align !== 'split' && (
        <div style={toolbarWrapperStyle}>
          {toolbar.align === 'left' ? toolbarPrefix : null}
          {toolbarBody}
          {toolbar.align === 'left' ? null : toolbarPrefix}
        </div>
      )}
      <XFlow>
        <XFlowGraph zoomable pannable minScale={0.2} maxScale={4} />
        <Grid
          type="dot"
          options={{
            color: NETWORK_TOPO_VISUAL.grid.color,
            thickness: NETWORK_TOPO_VISUAL.grid.thickness,
          }}
        />
        <Minimap
          width={minimap.width}
          height={minimap.height}
          style={minimap.style || NETWORK_TOPO_VISUAL.minimap}
        />
        <GraphLoader
          data={data}
          minimap={minimap}
          graphRef={internalGraphRef}
          fitViewOptions={fitViewOptions}
          onGraphReady={handleGraphReady}
          {...loaderProps}
        />
      </XFlow>
    </>
  );
};

export { DEVICE_NODE_SHAPE };
export default NetworkTopologyX6Canvas;
