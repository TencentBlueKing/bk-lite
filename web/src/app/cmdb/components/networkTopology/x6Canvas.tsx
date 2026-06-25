'use client';

import React, { useEffect } from 'react';
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
  onGraphReady?: (graph: Graph | null) => void;
  onNodeClick?: (nodeId: string) => void;
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
        { tagName: 'title', selector: 'tt' },
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
  onGraphReady,
  onNodeClick,
  onNodeMouseMove,
  onNodeMouseLeave,
  onNodeContextMenu,
  onEdgeContextMenu,
  onBlankClick,
  onBlankContextMenu,
}) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();

  useEffect(() => {
    ensureNetworkTopologyDeviceNodeRegistered();
    initData({ nodes: data.nodes, edges: data.edges });
  }, [initData, data]);

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
    data,
    fitViewOptions?.maxScale,
    fitViewOptions?.padding,
  ]);

  useEffect(() => {
    if (!graph) return undefined;
    const handleNodeClick = ({ node }: { node: any }) => onNodeClick?.(String(node.id));
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
    graph.on('node:mousemove', handleNodeMove);
    graph.on('node:mouseleave', handleNodeLeave);
    graph.on('node:contextmenu', handleNodeContext);
    graph.on('edge:contextmenu', handleEdgeContext);
    graph.on('blank:click', handleBlankClick);
    graph.on('blank:contextmenu', handleBlankContext);
    return () => {
      graph.off('node:click', handleNodeClick);
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
    onNodeMouseLeave,
    onNodeMouseMove,
  ]);

  return null;
};

const NetworkTopologyX6Canvas: React.FC<NetworkTopologyX6CanvasProps> = ({
  data,
  minimap = {
    width: 200,
    height: 120,
    style: NETWORK_TOPO_VISUAL.minimap,
  },
  ...loaderProps
}) => (
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
      <GraphLoader data={data} minimap={minimap} {...loaderProps} />
    </XFlow>
  </>
);

export { DEVICE_NODE_SHAPE };
export default NetworkTopologyX6Canvas;
