'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, Tooltip } from 'antd';
import {
  FullscreenOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { Graph } from '@antv/x6';
import { getIconUrl } from '@/app/cmdb/utils/modelIcon';
import { useTranslation } from '@/utils/i18n';
import {
  alertBadgeFill,
  alertCardStroke,
  formatAlertBadgeText,
} from './graphModel';
import type { RelatedTopologyGraphModel } from './types';
import { canvasBoxChanged, readStableCanvasBox } from './canvasSize';
import {
  NAME_TOOLTIP_ESTIMATE_HEIGHT,
  NAME_TOOLTIP_MAX_WIDTH,
  placeTooltipAboveCard,
} from './tooltipPosition';
import {
  RELATED_TOPOLOGY_CANVAS_STYLE,
  RELATED_TOPOLOGY_VISUAL,
} from './visual';

const NODE_SHAPE = 'ops-analysis-related-topology-node-v12';
const NODE_WIDTH = RELATED_TOPOLOGY_VISUAL.nodeWidth;
const NODE_HEIGHT = RELATED_TOPOLOGY_VISUAL.nodeHeight;
const ICON_SIZE = RELATED_TOPOLOGY_VISUAL.iconSize;
const ICON_X = 8;
const ICON_Y = Math.round((NODE_HEIGHT - ICON_SIZE) / 2);
const MIN_SCALE = 0.45;
const MAX_SCALE = 1.6;
const ZOOM_STEP = 0.1;
const FIT_VIEW_OPTIONS = { padding: 28, maxScale: 1 } as const;

const cardRectInContainer = (
  graph: Graph,
  nodeId: string,
  container: HTMLElement,
) => {
  const cell = graph.getCellById(nodeId);
  if (!cell) {
    return null;
  }
  const view = graph.findViewByCell(cell);
  const el = (view?.container as Element | undefined) || null;
  if (!el || typeof el.getBoundingClientRect !== 'function') {
    return null;
  }
  const card = el.getBoundingClientRect();
  const host = container.getBoundingClientRect();
  return {
    x: card.left - host.left,
    y: card.top - host.top,
    width: card.width,
    height: card.height,
  };
};

const resolveCardTooltipPosition = (
  graph: Graph,
  nodeId: string,
  container: HTMLElement,
) => {
  const card = cardRectInContainer(graph, nodeId, container);
  if (!card) {
    return null;
  }
  return placeTooltipAboveCard(
    card,
    { width: NAME_TOOLTIP_MAX_WIDTH, height: NAME_TOOLTIP_ESTIMATE_HEIGHT },
    { width: container.clientWidth, height: container.clientHeight },
  );
};

const ensureNodeRegistered = () => {
  Graph.registerNode(
    NODE_SHAPE,
    {
      inherit: 'rect',
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'image', selector: 'image' },
        { tagName: 'title', selector: 'tooltip1' },
        { tagName: 'text', selector: 'label1' },
        { tagName: 'title', selector: 'tooltip2' },
        { tagName: 'text', selector: 'label2' },
        { tagName: 'circle', selector: 'badge' },
        { tagName: 'text', selector: 'badgeText' },
      ],
      attrs: {
        body: {
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          rx: 6,
          ry: 6,
          ...RELATED_TOPOLOGY_VISUAL.card.defaultBody,
        },
        image: {
          width: ICON_SIZE,
          height: ICON_SIZE,
          x: ICON_X,
          y: ICON_Y,
        },
        label1: {
          refX: 0.28,
          refY: 0.38,
          textWrap: {
            width: 136,
            height: 24,
            ellipsis: true,
          },
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 16,
          fontWeight: 600,
          fill: RELATED_TOPOLOGY_VISUAL.card.label.fill,
        },
        label2: {
          refX: 0.28,
          refY: 0.68,
          textWrap: {
            width: 136,
            height: 18,
            ellipsis: true,
          },
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 12,
          fill: RELATED_TOPOLOGY_VISUAL.card.label.subFill,
        },
        badge: {
          cx: NODE_WIDTH - 2,
          cy: 4,
          r: 11,
          fill: 'var(--color-fail)',
          stroke: RELATED_TOPOLOGY_VISUAL.card.defaultBody.fill,
          strokeWidth: 2,
          opacity: 0,
        },
        badgeText: {
          refX: NODE_WIDTH - 2,
          refY: 4,
          fontSize: 11,
          fontWeight: 700,
          fill: '#fff',
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          opacity: 0,
        },
      },
    },
    true,
  );
};

interface RelatedTopologyGraphViewProps {
  model: RelatedTopologyGraphModel;
}

const RelatedTopologyGraphView = ({ model }: RelatedTopologyGraphViewProps) => {
  const { t } = useTranslation();
  const shellRef = useRef<HTMLDivElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const [nameTooltip, setNameTooltip] = useState<{
    nodeId: string;
    name: string;
    typeLabel: string;
    x: number;
    y: number;
  } | null>(null);

  const zoomBy = (delta: number) => {
    const graph = graphRef.current;
    if (!graph) {
      return;
    }
    const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, graph.zoom() + delta));
    graph.zoomTo(next);
  };

  useEffect(() => {
    const shell = shellRef.current;
    const host = hostRef.current;
    if (!shell || !host) {
      return;
    }

    let disposed = false;
    let lastBox = readStableCanvasBox(shell);
    const mount = () => {
      if (disposed || graphRef.current) {
        return;
      }
      const box = readStableCanvasBox(shell);
      if (!box) {
        return;
      }
      lastBox = box;
      ensureNodeRegistered();
      const graph = new Graph({
        container: host,
        width: box.width,
        height: box.height,
        autoResize: false,
        background: { color: 'transparent' },
        grid: {
          visible: true,
          type: 'dot',
          args: {
            color: RELATED_TOPOLOGY_VISUAL.grid.color,
            thickness: RELATED_TOPOLOGY_VISUAL.grid.thickness,
          },
        },
        panning: { enabled: true },
        mousewheel: { enabled: true, minScale: MIN_SCALE, maxScale: MAX_SCALE },
        interacting: {
          nodeMovable: false,
          edgeMovable: false,
          edgeLabelMovable: false,
        },
      });
      const showNameTooltip = ({
        node,
      }: {
        node: { id: string; getData: () => { name?: string; typeLabel?: string } };
      }) => {
        const data = node.getData() || {};
        const name = String(data.name || '').trim();
        const pos = name ? resolveCardTooltipPosition(graph, node.id, shell) : null;
        if (!name || !pos) {
          setNameTooltip(null);
          return;
        }
        setNameTooltip({
          nodeId: node.id,
          name,
          typeLabel: String(data.typeLabel || '').trim(),
          ...pos,
        });
      };
      const refreshNameTooltip = () => {
        setNameTooltip((current) => {
          if (!current) {
            return null;
          }
          const pos = resolveCardTooltipPosition(graph, current.nodeId, shell);
          return pos ? { ...current, ...pos } : null;
        });
      };
      graph.on('node:mouseenter', showNameTooltip);
      graph.on('node:mouseleave', () => setNameTooltip(null));
      graph.on('blank:mouseenter', () => setNameTooltip(null));
      graph.on('scale', refreshNameTooltip);
      graph.on('translate', refreshNameTooltip);
      graph.addNodes(
        model.nodes.map((node) => {
          const badge = formatAlertBadgeText(node.alertCount);
          const icon = getIconUrl({ model_id: node.modelId, icn: '' });
          const typeLabel = node.modelName || node.modelId || '';
          const card = node.isCenter
            ? RELATED_TOPOLOGY_VISUAL.card.activeBody
            : RELATED_TOPOLOGY_VISUAL.card.defaultBody;
          const alertStroke = alertCardStroke(node.alertCount, node.maxLevel);
          return {
            id: node.id,
            shape: NODE_SHAPE,
            zIndex: 10,
            width: NODE_WIDTH,
            height: NODE_HEIGHT,
            x: node.x,
            y: node.y,
            data: {
              name: node.name,
              typeLabel,
            },
            attrs: {
              body: {
                width: NODE_WIDTH,
                height: NODE_HEIGHT,
                ...card,
                ...alertStroke,
              },
              image: {
                'xlink:href': icon,
                href: icon,
              },
              tooltip1: { text: node.name },
              label1: { text: node.name, title: node.name },
              tooltip2: { text: typeLabel },
              label2: { text: typeLabel, title: typeLabel },
              badge: {
                opacity: badge ? 1 : 0,
                fill: alertBadgeFill(node.maxLevel),
              },
              badgeText: {
                opacity: badge ? 1 : 0,
                text: badge || '',
              },
            },
          };
        }),
      );
      graph.addEdges(
        model.edges.map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          connector: { name: 'rounded', args: { radius: 12 } },
          router: { name: 'er', args: { direction: 'H', offset: 24 } },
          attrs: {
            line: {
              stroke: RELATED_TOPOLOGY_VISUAL.edge.stroke,
              strokeWidth: RELATED_TOPOLOGY_VISUAL.edge.strokeWidth,
              targetMarker: {
                name: 'classic',
                size: 6,
                fill: RELATED_TOPOLOGY_VISUAL.edge.stroke,
                stroke: 'none',
              },
            },
          },
          labels: edge.label
            ? [
              {
                attrs: {
                  text: {
                    text: edge.label,
                    fill: RELATED_TOPOLOGY_VISUAL.labelFill,
                    fontSize: 12,
                    fontWeight: 500,
                  },
                  rect: {
                    fill: '#fcfeff',
                    stroke: 'none',
                    rx: 3,
                    ry: 3,
                  },
                },
              },
            ]
            : [],
        })),
      );
      graph.zoomToFit(FIT_VIEW_OPTIONS);
      graphRef.current = graph;
    };

    mount();
    const observer = new ResizeObserver(() => {
      if (!graphRef.current) {
        mount();
        return;
      }
      const next = readStableCanvasBox(shell);
      if (!next || !canvasBoxChanged(lastBox, next)) {
        return;
      }
      lastBox = next;
      graphRef.current.resize(next.width, next.height);
    });
    observer.observe(shell);

    return () => {
      disposed = true;
      observer.disconnect();
      setNameTooltip(null);
      graphRef.current?.dispose();
      graphRef.current = null;
    };
  }, [model]);

  return (
    <div
      ref={shellRef}
      className="relative h-full min-h-[280px] min-w-0 w-full overflow-hidden"
      style={RELATED_TOPOLOGY_CANVAS_STYLE}
    >
      <div ref={hostRef} className="absolute inset-0 overflow-hidden" />
      {nameTooltip ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-30 w-max max-w-[240px] rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-2 py-1 text-xs text-[var(--color-text-1)] shadow-sm"
          style={{ left: nameTooltip.x, top: nameTooltip.y }}
        >
          <div className="break-all font-medium">{nameTooltip.name}</div>
          {nameTooltip.typeLabel ? (
            <div className="break-all text-[var(--color-text-3)]">{nameTooltip.typeLabel}</div>
          ) : null}
        </div>
      ) : null}
      <div className="pointer-events-none absolute right-2.5 top-2.5 z-20">
        <div className="pointer-events-auto flex items-center gap-1 rounded-lg border border-[var(--color-border-2)] bg-[color-mix(in_srgb,var(--color-bg-1)_92%,transparent)] p-1 shadow-sm">
          <Tooltip title={t('dashboard.networkTopoZoomOut')}>
            <Button
              size="small"
              type="text"
              aria-label={t('dashboard.networkTopoZoomOut')}
              icon={<ZoomOutOutlined />}
              onClick={() => zoomBy(-ZOOM_STEP)}
            />
          </Tooltip>
          <Tooltip title={t('dashboard.networkTopoZoomIn')}>
            <Button
              size="small"
              type="text"
              aria-label={t('dashboard.networkTopoZoomIn')}
              icon={<ZoomInOutlined />}
              onClick={() => zoomBy(ZOOM_STEP)}
            />
          </Tooltip>
          <Tooltip title={t('topology.fitView')}>
            <Button
              size="small"
              type="text"
              aria-label={t('topology.fitView')}
              icon={<FullscreenOutlined />}
              onClick={() => graphRef.current?.zoomToFit(FIT_VIEW_OPTIONS)}
            />
          </Tooltip>
        </div>
      </div>
    </div>
  );
};

export default RelatedTopologyGraphView;
