'use client';

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { Button, Segmented, Tooltip } from 'antd';
import {
  DownloadOutlined,
  FullscreenOutlined,
  ReloadOutlined,
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
  };
  showZoom?: boolean;
  showFitView?: boolean;
  showExport?: boolean;
  showRefresh?: boolean;
  exportFileName?: string;
  exportDisabled?: boolean;
  refreshLoading?: boolean;
  onRefresh?: () => void;
}

interface NetworkTopologyX6CanvasProps {
  data: NetworkTopologyX6GraphData;
  centerId?: string;
  editing?: boolean;
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
  onNodeClick?: (nodeId: string) => void;
  onNodeMouseEnter?: (nodeId: string, event: MouseEvent) => void;
  onNodeMouseMove?: (nodeId: string, event: MouseEvent) => void;
  onNodeMouseLeave?: (nodeId: string) => void;
  onNodeContextMenu?: (nodeId: string, event: MouseEvent) => void;
  onEdgeContextMenu?: (edgeId: string, event: MouseEvent) => void;
  onBlankClick?: () => void;
  onBlankContextMenu?: (event: MouseEvent) => void;
}

const NODE_WIDTH = NETWORK_TOPO_VISUAL.node.width;
const NODE_HEIGHT = NETWORK_TOPO_VISUAL.node.height;
const DEVICE_NODE_SHAPE = 'topo-network-device';

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
    nodes: data.nodes.map((node) => [
      node.id,
      node.x,
      node.y,
      node.width,
      node.height,
      node.shape,
    ]),
    edges: data.edges.map((edge) => [
      edge.id,
      edge.source,
      edge.target,
      edge.vertices,
    ]),
  });

const patchGraphAttrs = (graph: Graph, data: NetworkTopologyX6GraphData) => {
  data.nodes.forEach((node) => {
    const cell = graph.getCellById(node.id) as any;
    if (!cell) return;
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
  onNodeClick,
  onNodeMouseEnter,
  onNodeMouseMove,
  onNodeMouseLeave,
  onNodeContextMenu,
  onEdgeContextMenu,
  onBlankClick,
  onBlankContextMenu,
}) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();
  const structureKey = useMemo(() => buildStructureKey(data), [data]);
  const structureKeyRef = useRef('');
  const initializedRef = useRef(false);

  useEffect(() => {
    ensureNetworkTopologyDeviceNodeRegistered();
    if (!initializedRef.current || structureKeyRef.current !== structureKey) {
      initializedRef.current = true;
      structureKeyRef.current = structureKey;
      initData({ nodes: data.nodes, edges: data.edges });
      return;
    }
    if (graph) {
      patchGraphAttrs(graph, data);
    }
  }, [graph, initData, data, structureKey]);

  useEffect(() => {
    if (!graph) return undefined;
    if (graphRef) graphRef.current = graph;
    onGraphReady?.(graph);
    if (!graph.getPlugin('export')) {
      graph.use(new Export());
    }
    return () => {
      if (graphRef) graphRef.current = null;
      onGraphReady?.(null);
    };
  }, [graph, graphRef, onGraphReady]);

  useEffect(() => {
    if (!graph) return undefined;
    const timer = window.setTimeout(() => {
      try {
        graph.zoomToFit({
          padding: fitViewOptions?.padding ?? 112,
          maxScale: fitViewOptions?.maxScale ?? 1.12,
        });
      } catch {
        // ignore graph warm-up timing
      }
    }, 60);
    return () => window.clearTimeout(timer);
  }, [
    graph,
    fitViewKey ?? data,
    fitViewOptions?.maxScale,
    fitViewOptions?.padding,
  ]);

  useEffect(() => {
    if (!graph) return undefined;
    const handleNodeClick = ({ node }: { node: any }) => onNodeClick?.(String(node.id));
    const handleNodeEnter = ({ node, e }: { node: any; e: MouseEvent }) => onNodeMouseEnter?.(String(node.id), e);
    const handleNodeMove = ({ node, e }: { node: any; e: MouseEvent }) => onNodeMouseMove?.(String(node.id), e);
    const handleNodeLeave = ({ node }: { node: any }) => onNodeMouseLeave?.(String(node.id));
    const handleNodeContext = ({ node, e }: { node: any; e: MouseEvent }) => {
      e.preventDefault();
      onNodeContextMenu?.(String(node.id), e);
    };
    const handleEdgeContext = ({ edge, e }: { edge: any; e: MouseEvent }) => {
      e.preventDefault();
      onEdgeContextMenu?.(String(edge.id), e);
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
    graph.on('edge:contextmenu', handleEdgeContext);
    graph.on('blank:click', handleBlankClick);
    graph.on('blank:contextmenu', handleBlankContext);
    return () => {
      graph.off('node:click', handleNodeClick);
      graph.off('node:mouseenter', handleNodeEnter);
      graph.off('node:mousemove', handleNodeMove);
      graph.off('node:mouseleave', handleNodeLeave);
      graph.off('node:contextmenu', handleNodeContext);
      graph.off('edge:contextmenu', handleEdgeContext);
      graph.off('blank:click', handleBlankClick);
      graph.off('blank:contextmenu', handleBlankContext);
    };
  }, [
    graph,
    onBlankClick,
    onBlankContextMenu,
    onEdgeContextMenu,
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
    internalGraphRef.current?.zoomToFit({
      padding: fitViewOptions?.padding ?? 112,
      maxScale: fitViewOptions?.maxScale ?? 1.12,
    });
  }, [fitViewOptions?.maxScale, fitViewOptions?.padding]);

  const handleExport = useCallback(() => {
    const graph = internalGraphRef.current;
    if (!graph) return;
    graph.exportPNG(toolbar?.exportFileName || 'network-topology', {
      padding: 40,
      backgroundColor: '#ffffff',
      copyStyles: false,
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
        <XFlowGraph zoomable pannable minScale={0.2} maxScale={4} fitView />
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
