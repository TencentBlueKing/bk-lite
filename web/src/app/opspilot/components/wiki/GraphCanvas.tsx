'use client';

import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { Graph, type IElementEvent } from '@antv/g6';
import { GraphEdge, GraphNode } from '@/app/opspilot/types/wiki';

// 社区配色:柔和的现代主题色,饱和度适中、不刺眼(导出供图例复用,保证颜色一致)
export const GRAPH_PALETTE = ['#5B8FF9', '#5AD8A6', '#5D7092', '#F6BD16', '#E8684A', '#6DC8EC', '#9270CA', '#FF9D4D', '#269A99', '#FF99C3'];
export const communityColor = (community: number) => GRAPH_PALETTE[community % GRAPH_PALETTE.length];

export interface GraphCanvasHandle {
  zoomBy: (ratio: number) => void;
  resetView: () => void;
}

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  height?: number | string; // 数值固定高;传 '100%' 由父容器(全幅/全屏)撑满
  nodeScale?: number; // 节点大小系数(过滤器「节点大小」滑块),默认 1
  linkDistance?: number; // 力导链接距离(过滤器「间距」滑块),默认 160
}

const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  ({ nodes, edges, height = 460, nodeScale = 1, linkDistance = 160 }, ref) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const graphRef = useRef<Graph | null>(null);
    // 用 ref 持有最新的尺寸/间距,供「创建图」时读取,而不把它们放进创建 effect 的依赖(否则改滑块会整图重建+重排)
    const nodeScaleRef = useRef(nodeScale);
    nodeScaleRef.current = nodeScale;
    const linkDistanceRef = useRef(linkDistance);
    linkDistanceRef.current = linkDistance;

    // 连接度(决定节点大小层级),仅随 edges 变化
    const degree = useMemo(() => {
      const m = new Map<string, number>();
      edges.forEach((e) => {
        m.set(String(e.from), (m.get(String(e.from)) || 0) + 1);
        m.set(String(e.to), (m.get(String(e.to)) || 0) + 1);
      });
      return m;
    }, [edges]);
    const baseSize = useCallback((id: string) => Math.min(54, 26 + (degree.get(id) || 0) * 4), [degree]);

    useImperativeHandle(
      ref,
      () => ({
        zoomBy: (ratio: number) => {
          try {
            graphRef.current?.zoomBy(ratio);
          } catch {
            /* 已销毁忽略 */
          }
        },
        resetView: () => {
          try {
            graphRef.current?.fitView({ when: 'always', direction: 'both' });
          } catch {
            /* 已销毁忽略 */
          }
        },
      }),
      []
    );

    // 创建图:仅在 nodes/edges 变化时重建(滑块改尺寸/间距不在此触发,避免整图重排)
    useEffect(() => {
      const container = containerRef.current;
      if (!container || !nodes.length) return;

      const graph = new Graph({
        container,
        autoResize: true,
        animation: false,
        data: {
          nodes: nodes.map((n) => ({
            id: String(n.id),
            data: { label: n.title, community: n.community ?? 0, size: Math.round(baseSize(String(n.id)) * nodeScaleRef.current) },
          })),
          edges: edges.map((e) => ({ source: String(e.from), target: String(e.to) })),
        },
        node: {
          style: {
            size: (d) => Number(d.data?.size ?? 28),
            fill: (d) => communityColor(Number(d.data?.community ?? 0)),
            opacity: 1,
            labelOpacity: 1,
            stroke: '#ffffff',
            lineWidth: 2,
            shadowColor: 'rgba(15, 23, 42, 0.18)',
            shadowBlur: 12,
            shadowOffsetY: 2,
            labelText: (d) => String((d.data?.label as string) ?? d.id),
            labelPlacement: 'bottom',
            labelFill: '#1f2937',
            labelFontSize: 12,
            labelFontWeight: 500,
            labelBackground: true,
            labelBackgroundFill: 'rgba(255,255,255,0.85)',
            labelBackgroundRadius: 4,
            labelPadding: [2, 6],
            labelMaxWidth: 120,
            labelWordWrap: true,
            labelMaxLines: 2,
          },
          state: {
            active: { lineWidth: 3, halo: true, haloLineWidth: 8 },
            inactive: { opacity: 0.2, labelOpacity: 0.15 },
          },
        },
        edge: {
          style: {
            stroke: '#D0D5DD',
            lineWidth: 1.2,
            strokeOpacity: 0.75,
            endArrow: true,
            endArrowType: 'vee',
            endArrowSize: 3,
          },
          state: {
            active: { stroke: '#5B8FF9', strokeOpacity: 1, lineWidth: 2 },
            inactive: { strokeOpacity: 0.06 },
          },
        },
        layout: { type: 'force', linkDistance: linkDistanceRef.current, preventOverlap: true, nodeSize: 80, nodeSpacing: 24, collideStrength: 0.9 },
        behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
      });

      graphRef.current = graph;

      // hover 聚焦高亮:进入节点→高亮该节点及邻居与相连边、其余淡化;离开→清空
      const applyFocus = (id: string) => {
        const keep = new Set<string>([id, ...graph.getNeighborNodesData(id).map((n) => String(n.id))]);
        const states: Record<string, string> = {};
        graph.getNodeData().forEach((n) => {
          states[String(n.id)] = keep.has(String(n.id)) ? 'active' : 'inactive';
        });
        graph.getEdgeData().forEach((e) => {
          states[String(e.id)] = keep.has(String(e.source)) && keep.has(String(e.target)) ? 'active' : 'inactive';
        });
        graph.setElementState(states, false);
      };
      const clearFocus = () => {
        const states: Record<string, string[]> = {};
        graph.getNodeData().forEach((n) => (states[String(n.id)] = []));
        graph.getEdgeData().forEach((e) => (states[String(e.id)] = []));
        graph.setElementState(states, false);
      };
      graph.on('node:pointerenter', (e: IElementEvent) => applyFocus(String(e.target.id)));
      graph.on('node:pointerleave', clearFocus);

      const fit = () => {
        try {
          graph.fitView({ when: 'always', direction: 'both' });
        } catch {
          /* 图谱已销毁或无节点时忽略 */
        }
      };
      graph.on('afterlayout', fit);
      graph.render().then(fit);

      return () => {
        graph.destroy();
        graphRef.current = null;
      };
    }, [nodes, edges, baseSize]);

    // 「节点大小」滑块:原地更新尺寸,不重跑布局 → 位置不动,只是变大变小(跳过首渲染,避免与创建重复)
    const firstScale = useRef(true);
    useEffect(() => {
      if (firstScale.current) {
        firstScale.current = false;
        return;
      }
      const g = graphRef.current;
      if (!g) return;
      try {
        // 尺寸映射读 d.data.size,故更新 data.size(更新 style.size 无效);draw 重渲染不重布局,位置不动
        g.updateNodeData(nodes.map((n) => ({ id: String(n.id), data: { size: Math.round(baseSize(String(n.id)) * nodeScale) } })));
        g.draw();
      } catch {
        /* 忽略 */
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodeScale]);

    // 「间距」滑块:改 linkDistance → 从当前位置重跑一次布局(父组件用 onChangeComplete 触发,拖动中不持续触发)
    const firstDist = useRef(true);
    useEffect(() => {
      if (firstDist.current) {
        firstDist.current = false;
        return;
      }
      const g = graphRef.current;
      if (!g) return;
      (async () => {
        try {
          g.setLayout((prev) => ({ ...prev, linkDistance }));
          await g.layout();
          g.fitView({ when: 'always', direction: 'both' });
        } catch {
          /* 忽略 */
        }
      })();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [linkDistance]);

    return <div ref={containerRef} style={{ width: '100%', height }} />;
  }
);

GraphCanvas.displayName = 'GraphCanvas';
export default GraphCanvas;
