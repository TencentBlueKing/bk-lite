'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Spin } from 'antd';
import { Graph } from '@antv/x6';
import { useTranslation } from '@/utils/i18n';
import WidgetState from '@/app/ops-analysis/components/widget-state';
import {
  getOpsChartColorsByMode,
  getOpsChartThemeByMode,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import type {
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { formatVisibleChartValue } from '@/app/ops-analysis/utils/chartValueFormat';
import {
  NODE_GRAPH_NODE_HEIGHT,
  NODE_GRAPH_NODE_WIDTH,
  buildNodeGraph,
  isNodeGraphMappingComplete,
  layoutNodeGraphBipartite,
  toNodeGraphMapping,
} from '@/app/ops-analysis/utils/nodeGraphData';

interface NodeGraphProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
  componentSwitchControl?: React.ReactNode;
  errorMessage?: string;
  screenRenderContext?: ScreenRenderContext;
}

type HoverInfo =
  | { kind: 'node'; id: string; role: 'source' | 'target'; inbound: number; outbound: number }
  | { kind: 'edge'; source: string; target: string; value: number };

const EDGE_MIN_WIDTH = 1.5;
const EDGE_MAX_WIDTH = 7;

const scaleEdgeWidth = (value: number, minValue: number, maxValue: number) => {
  if (maxValue <= minValue) {
    return (EDGE_MIN_WIDTH + EDGE_MAX_WIDTH) / 2;
  }
  return (
    EDGE_MIN_WIDTH
    + ((value - minValue) / (maxValue - minValue)) * (EDGE_MAX_WIDTH - EDGE_MIN_WIDTH)
  );
};

const scaleEdgeOpacity = (value: number, minValue: number, maxValue: number) => {
  if (maxValue <= minValue) {
    return 0.72;
  }
  return 0.38 + ((value - minValue) / (maxValue - minValue)) * 0.5;
};

const truncateLabel = (id: string) => (id.length > 18 ? `${id.slice(0, 17)}…` : id);

const NodeGraph: React.FC<NodeGraphProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
  componentSwitchControl,
  errorMessage,
}) => {
  const { t } = useTranslation();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const onReadyRef = useRef(onReady);
  const [hover, setHover] = useState<{ info: HoverInfo; x: number; y: number } | null>(null);
  onReadyRef.current = onReady;

  const mapping = useMemo(() => toNodeGraphMapping(config), [config]);
  const mappingComplete = isNodeGraphMappingComplete(mapping);
  const graphModel = useMemo(
    () => buildNodeGraph(rawData, mapping),
    [rawData, mapping],
  );
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const themeName = resolveOpsChartThemeName();
  const palette = getOpsChartColorsByMode(config?.chartThemeMode, themeName);
  const sourceColor = palette[0] || chartTheme.singleValueColor;
  const targetColor = palette[1] || palette[4] || sourceColor;
  const trafficColor = palette[3] || palette[2] || sourceColor;

  useEffect(() => {
    if (loading) {
      onReadyRef.current?.(false);
      return;
    }
    if (errorMessage) {
      onReadyRef.current?.(true);
      return;
    }
    if (!mappingComplete) {
      onReadyRef.current?.(true);
      return;
    }
    if (graphModel.edges.length === 0) {
      onReadyRef.current?.(false);
    }
  }, [errorMessage, graphModel.edges.length, loading, mappingComplete]);

  useEffect(() => {
    if (loading || errorMessage || !mappingComplete || graphModel.edges.length === 0) {
      graphRef.current?.dispose();
      graphRef.current = null;
      setHover(null);
      return;
    }

    const host = hostRef.current;
    const viewport = rootRef.current;
    if (!host || !viewport) {
      return;
    }

    let cancelled = false;
    let readyFrame = 0;

    const width = Math.max(viewport.clientWidth, 1);
    const height = Math.max(viewport.clientHeight, 1);
    const graph = new Graph({
      container: host,
      width,
      height,
      background: { color: 'transparent' },
      panning: { enabled: true },
      mousewheel: {
        enabled: true,
        minScale: 0.2,
        maxScale: 2.5,
      },
      interacting: {
        nodeMovable: false,
        edgeMovable: false,
        edgeLabelMovable: false,
        arrowheadMovable: false,
        vertexMovable: false,
      },
    });
    graphRef.current = graph;

    const updateHover = (info: HoverInfo, event: { clientX: number; clientY: number }) => {
      const root = rootRef.current;
      if (!root) return;
      const rect = root.getBoundingClientRect();
      setHover({
        info,
        x: Math.min(event.clientX - rect.left + 12, Math.max(rect.width - 180, 8)),
        y: Math.min(event.clientY - rect.top + 12, Math.max(rect.height - 72, 8)),
      });
    };

    graph.on('node:mouseenter', ({ node, e }) => {
      const data = node.getData() as {
        label: string;
        role: 'source' | 'target';
        inbound: number;
        outbound: number;
      };
      updateHover(
        {
          kind: 'node',
          id: data.label,
          role: data.role,
          inbound: data.inbound,
          outbound: data.outbound,
        },
        e,
      );
    });
    graph.on('node:mousemove', ({ node, e }) => {
      const data = node.getData() as {
        label: string;
        role: 'source' | 'target';
        inbound: number;
        outbound: number;
      };
      updateHover(
        {
          kind: 'node',
          id: data.label,
          role: data.role,
          inbound: data.inbound,
          outbound: data.outbound,
        },
        e,
      );
    });
    graph.on('edge:mouseenter', ({ edge, e }) => {
      const data = edge.getData() as { source: string; target: string; value: number };
      updateHover(
        { kind: 'edge', source: data.source, target: data.target, value: data.value },
        e,
      );
    });
    graph.on('edge:mousemove', ({ edge, e }) => {
      const data = edge.getData() as { source: string; target: string; value: number };
      updateHover(
        { kind: 'edge', source: data.source, target: data.target, value: data.value },
        e,
      );
    });
    graph.on('node:mouseleave', () => setHover(null));
    graph.on('edge:mouseleave', () => setHover(null));
    graph.on('blank:mouseenter', () => setHover(null));

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
          if (!viewport.clientWidth || !viewport.clientHeight) return;
          graph.resize(viewport.clientWidth, viewport.clientHeight);
          graph.zoomToFit({ padding: 28, maxScale: 1 });
        });
    observer?.observe(viewport);

    const edgeValues = graphModel.edges.map((edge) => edge.value);
    const minValue = Math.min(...edgeValues);
    const maxValue = Math.max(...edgeValues);
    const placed = layoutNodeGraphBipartite(graphModel, width, height);

    graph.addNodes(
      placed.nodes.map((node) => {
        const color = node.role === 'source' ? sourceColor : targetColor;
        return {
          id: node.graphId,
          shape: 'rect',
          x: node.x,
          y: node.y,
          width: NODE_GRAPH_NODE_WIDTH,
          height: NODE_GRAPH_NODE_HEIGHT,
          label: truncateLabel(node.label),
          data: {
            label: node.label,
            role: node.role,
            inbound: node.inbound,
            outbound: node.outbound,
          },
          attrs: {
            body: {
              fill: color,
              fillOpacity: 0.16,
              stroke: color,
              strokeWidth: 1.5,
              rx: 6,
              ry: 6,
            },
            label: {
              text: truncateLabel(node.label),
              fill: chartTheme.panelTitleColor,
              fontSize: 11,
              fontWeight: 500,
            },
          },
        };
      }),
    );
    graph.addEdges(
      placed.edges.map((edge, index) => ({
        id: `node-graph-edge-${index}`,
        source: { cell: edge.source, anchor: { name: 'right' } },
        target: { cell: edge.target, anchor: { name: 'left' } },
        data: {
          source: graphModel.edges[index].source,
          target: graphModel.edges[index].target,
          value: edge.value,
        },
        connector: { name: 'smooth' },
        attrs: {
          line: {
            stroke: trafficColor,
            strokeWidth: scaleEdgeWidth(edge.value, minValue, maxValue),
            strokeOpacity: scaleEdgeOpacity(edge.value, minValue, maxValue),
            strokeLinecap: 'round',
            targetMarker: {
              name: 'classic',
              size: 6,
              fill: trafficColor,
            },
          },
        },
      })),
    );
    graph.zoomToFit({ padding: 28, maxScale: 1 });
    readyFrame = window.requestAnimationFrame(() => {
      if (cancelled) return;
      onReadyRef.current?.(true);
    });

    return () => {
      cancelled = true;
      if (readyFrame) window.cancelAnimationFrame(readyFrame);
      observer?.disconnect();
      setHover(null);
      graph.dispose();
      if (graphRef.current === graph) {
        graphRef.current = null;
      }
    };
  }, [
    chartTheme.panelTitleColor,
    errorMessage,
    graphModel,
    loading,
    mappingComplete,
    sourceColor,
    targetColor,
    trafficColor,
  ]);

  let content: React.ReactNode;
  if (loading) {
    content = (
      <div className="flex h-full items-center justify-center">
        <Spin size="small" />
      </div>
    );
  } else if (errorMessage) {
    content = <WidgetState kind="error" description={errorMessage} />;
  } else if (!mappingComplete) {
    content = (
      <WidgetState description={t('dashboard.nodeGraphMappingRequired', '请完整配置源、目的和流量字段')} />
    );
  } else if (graphModel.edges.length === 0) {
    content = <WidgetState />;
  } else {
    content = (
      <div ref={rootRef} className="relative h-full min-h-0 w-full">
        <div className="pointer-events-none absolute inset-x-0 top-1 z-10 flex items-center justify-between px-3 text-xs text-[var(--color-text-3)]">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: sourceColor }}
            />
            {t('dashboard.nodeGraphSourceColumn', '源')}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: trafficColor }}
            />
            {t('dashboard.nodeGraphTrafficLegend', '流量')}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: targetColor }}
            />
            {t('dashboard.nodeGraphTargetColumn', '目标')}
          </span>
        </div>
        <div ref={hostRef} className="h-full w-full" />
        {hover ? (
          <div
            className="pointer-events-none absolute z-10 max-w-[220px] rounded-md px-2 py-1.5 text-xs"
            style={{
              left: hover.x,
              top: hover.y,
              backgroundColor: chartTheme.tooltipBackgroundColor,
              border: `1px solid ${chartTheme.tooltipBorderColor}`,
              color: chartTheme.tooltipTextColor,
              boxShadow: chartTheme.tooltipShadow,
            }}
          >
            {hover.info.kind === 'node' ? (
              <div className="flex flex-col gap-0.5">
                <span className="font-medium">{hover.info.id}</span>
                <span>
                  {hover.info.role === 'source'
                    ? t('dashboard.nodeGraphOutbound', '出向')
                    : t('dashboard.nodeGraphInbound', '入向')}{' '}
                  {formatVisibleChartValue(
                    hover.info.role === 'source' ? hover.info.outbound : hover.info.inbound,
                    config,
                  )}
                </span>
              </div>
            ) : (
              <div className="flex flex-col gap-0.5">
                <span className="font-medium">
                  {hover.info.source} → {hover.info.target}
                </span>
                <span>{formatVisibleChartValue(hover.info.value, config)}</span>
              </div>
            )}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {componentSwitchControl ? (
        <div className="shrink-0 overflow-x-auto px-3 pt-2">
          {componentSwitchControl}
        </div>
      ) : null}
      <div className="min-h-0 flex-1">{content}</div>
    </div>
  );
};

export default NodeGraph;
