'use client';

import React, { useEffect, useRef } from 'react';
import { Graph } from '@antv/g6';
import { GraphEdge, GraphNode } from '@/app/opspilot/types/wiki';

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  height?: number;
}

const PALETTE = ['#5B8FF9', '#61DDAA', '#F6BD16', '#F08BB4', '#65789B', '#7262FD', '#78D3F8', '#9661BC'];

const GraphCanvas: React.FC<GraphCanvasProps> = ({ nodes, edges, height = 420 }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !nodes.length) return;

    const graph = new Graph({
      container,
      autoResize: true,
      data: {
        nodes: nodes.map((n) => ({
          id: String(n.id),
          data: { label: n.title, community: n.community ?? 0 },
        })),
        edges: edges.map((e) => ({ source: String(e.from), target: String(e.to) })),
      },
      node: {
        style: {
          labelText: (d) => String((d.data?.label as string) ?? d.id),
          labelPlacement: 'bottom',
          fill: (d) => PALETTE[Number(d.data?.community ?? 0) % PALETTE.length],
          size: 28,
        },
      },
      edge: { style: { stroke: '#C2C8D5', endArrow: true } },
      layout: { type: 'force', linkDistance: 120 },
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
    });

    graphRef.current = graph;
    graph.render();

    return () => {
      graph.destroy();
      graphRef.current = null;
    };
  }, [nodes, edges]);

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};

export default GraphCanvas;
