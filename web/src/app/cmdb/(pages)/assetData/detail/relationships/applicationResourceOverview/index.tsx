'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Flex,
  Radio,
  Space,
  Spin,
  Table,
} from 'antd';
import {
  DownloadOutlined,
  DoubleRightOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import type { Edge, Graph, Node } from '@antv/x6';

import { useInstanceApi } from '@/app/cmdb/api/instance';
import {
  buildNetworkTopologyX6GraphData,
  NetworkTopologyX6Canvas,
  type NetworkTopologyLink as VisualLink,
  type NetworkTopologyNode as VisualNode,
  type NetworkTopologyNodeStatus,
} from '@/app/cmdb/components/networkTopology';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import type {
  ApplicationResourceLink,
  ApplicationResourceInstanceListData,
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '@/app/cmdb/types/applicationResourceOverview';
import styles from './index.module.scss';

interface Props {
  modelId: string;
  instId: string;
}

type ViewMode = 'topology' | 'resources';
interface OverviewTarget {
  id: string;
  name: string;
  model_id: string;
}

interface NodeContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  nodeId: string;
}

const GROUP_LABELS: Record<string, string> = {
  application: 'ApplicationResourceOverview.groupApplication',
  host: 'ApplicationResourceOverview.groupHost',
  database: 'ApplicationResourceOverview.groupDatabase',
  middleware: 'ApplicationResourceOverview.groupMiddleware',
  cache: 'ApplicationResourceOverview.groupCache',
  message_queue: 'ApplicationResourceOverview.groupMessageQueue',
  hardware: 'ApplicationResourceOverview.groupHardware',
  rack_room: 'ApplicationResourceOverview.groupRackRoom',
  other: 'ApplicationResourceOverview.groupOther',
};

const LAYER_START_Y = 88;
const LAYER_GAP = 168;

const LAYER_META = {
  root: {
    titleKey: 'ApplicationResourceOverview.layerSystem',
    y: LAYER_START_Y,
  },
  service: {
    titleKey: 'ApplicationResourceOverview.layerServiceTier',
    y: LAYER_START_Y + LAYER_GAP,
  },
  host: {
    titleKey: 'ApplicationResourceOverview.layerHost',
    y: LAYER_START_Y + LAYER_GAP * 2,
  },
  appService: {
    titleKey: 'ApplicationResourceOverview.layerAppService',
    y: LAYER_START_Y + LAYER_GAP * 3,
  },
  infrastructure: {
    titleKey: 'ApplicationResourceOverview.layerInfrastructure',
    y: LAYER_START_Y + LAYER_GAP * 4,
  },
} as const;

type LayerKey = keyof typeof LAYER_META;

const COMPACT_NODE = {
  width: 248,
  height: 68,
  iconColumnWidth: 50,
  iconSize: 34,
  labelX: 62,
  labelWidth: 170,
} as const;

const buildRelationshipLabel = (text: string, position = 0.5) => ({
  position,
  markup: [
    { tagName: 'rect', selector: 'bg' },
    { tagName: 'text', selector: 'txt' },
  ],
  attrs: {
    txt: {
      text,
      fill: 'var(--color-text-3)',
      fontSize: 10,
      fontWeight: 500,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
    bg: {
      ref: 'txt',
      refWidth: '140%',
      refHeight: '155%',
      refX: '-20%',
      refY: '-27%',
      fill: 'var(--color-bg)',
      fillOpacity: 0.94,
      stroke: 'var(--color-border-2)',
      strokeWidth: 1,
      rx: 4,
      ry: 4,
    },
  },
});

const resolveEdgeCellId = (terminal: unknown) => {
  if (typeof terminal === 'string' || typeof terminal === 'number') {
    return String(terminal);
  }
  if (!terminal || typeof terminal !== 'object' || !('cell' in terminal)) return '';
  const cell = (terminal as { cell?: unknown }).cell;
  return cell == null ? '' : String(cell);
};

const resolveRelationshipText = (labels: unknown) => {
  if (!Array.isArray(labels)) return '';
  const firstLabel = labels[0];
  if (!firstLabel || typeof firstLabel !== 'object' || !('attrs' in firstLabel)) return '';
  const attrs = (firstLabel as { attrs?: unknown }).attrs;
  if (!attrs || typeof attrs !== 'object' || !('txt' in attrs)) return '';
  const txt = (attrs as { txt?: unknown }).txt;
  if (!txt || typeof txt !== 'object' || !('text' in txt)) return '';
  return String((txt as { text?: unknown }).text || '').trim();
};

const resolveGraphNodeCenter = (node: ReturnType<typeof buildNetworkTopologyX6GraphData>['nodes'][number]) => ({
  x: Number(node.x) + Number(node.width) / 2,
  y: Number(node.y) + Number(node.height) / 2,
});

const resolveGraphLayerIndex = (node: ReturnType<typeof buildNetworkTopologyX6GraphData>['nodes'][number]) => {
  const centerY = resolveGraphNodeCenter(node).y;
  return (Object.keys(LAYER_META) as LayerKey[]).reduce((nearestIndex, key, index, keys) => {
    const nearestDistance = Math.abs(centerY - LAYER_META[keys[nearestIndex]].y);
    return Math.abs(centerY - LAYER_META[key].y) < nearestDistance ? index : nearestIndex;
  }, 0);
};

const buildCrossLayerVertices = (
  sourceCenter: { x: number; y: number },
  targetCenter: { x: number; y: number },
  nodes: ReturnType<typeof buildNetworkTopologyX6GraphData>['nodes']
) => {
  const nodeHalfWidth = COMPACT_NODE.width / 2;
  const clearance = 12;
  const intervals = nodes
    .map(resolveGraphNodeCenter)
    .filter((center) => center.y > sourceCenter.y && center.y < targetCenter.y)
    .map((center) => ({
      start: center.x - nodeHalfWidth - clearance,
      end: center.x + nodeHalfWidth + clearance,
    }))
    .sort((a, b) => a.start - b.start);

  const mergedIntervals = intervals.reduce<Array<{ start: number; end: number }>>((merged, interval) => {
    const previous = merged[merged.length - 1];
    if (!previous || interval.start > previous.end) {
      merged.push({ ...interval });
    } else {
      previous.end = Math.max(previous.end, interval.end);
    }
    return merged;
  }, []);

  const corridorCandidates: number[] = [];
  mergedIntervals.forEach((interval, index) => {
    const next = mergedIntervals[index + 1];
    if (next && next.start - interval.end >= 24) {
      corridorCandidates.push((interval.end + next.start) / 2);
    }
  });
  if (mergedIntervals.length) {
    corridorCandidates.push(mergedIntervals[0].start - 32);
    corridorCandidates.push(mergedIntervals[mergedIntervals.length - 1].end + 32);
  } else {
    corridorCandidates.push((sourceCenter.x + targetCenter.x) / 2);
  }

  const corridorX = corridorCandidates.reduce((best, candidate) => {
    const score = Math.abs(candidate - sourceCenter.x) + Math.abs(candidate - targetCenter.x);
    const bestScore = Math.abs(best - sourceCenter.x) + Math.abs(best - targetCenter.x);
    return score < bestScore ? candidate : best;
  }, corridorCandidates[0]);
  const sourceY = sourceCenter.y + COMPACT_NODE.height / 2;
  const targetY = targetCenter.y - COMPACT_NODE.height / 2;
  const turnOffset = Math.min(24, Math.max(12, (targetY - sourceY) / 5));

  return [
    { x: sourceCenter.x, y: sourceY + turnOffset },
    { x: corridorX, y: sourceY + turnOffset },
    { x: corridorX, y: targetY - turnOffset },
    { x: targetCenter.x, y: targetY - turnOffset },
  ];
};

function getLayerTitle(key: LayerKey, t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string) {
  return t(LAYER_META[key].titleKey);
}

function buildCompactGraphData(graphData: ReturnType<typeof buildNetworkTopologyX6GraphData>) {
  const nodeMap = new Map(graphData.nodes.map((node) => [String(node.id), node]));
  const edgeGroups = new Map<string, {
    edge: (typeof graphData.edges)[number];
    visualSourceCell: string;
    visualTargetCell: string;
    visualSourceNode: (typeof graphData.nodes)[number];
    visualTargetNode: (typeof graphData.nodes)[number];
    hasForwardEdge: boolean;
    hasReverseEdge: boolean;
    forwardRelationships: Set<string>;
    reverseRelationships: Set<string>;
  }>();

  graphData.edges.forEach((edge) => {
    const sourceCell = resolveEdgeCellId(edge.source);
    const targetCell = resolveEdgeCellId(edge.target);
    const sourceNode = nodeMap.get(sourceCell);
    const targetNode = nodeMap.get(targetCell);
    if (!sourceNode || !targetNode || sourceCell === targetCell) return;

    const sourceCenter = resolveGraphNodeCenter(sourceNode);
    const targetCenter = resolveGraphNodeCenter(targetNode);
    const sourceComesFirst = sourceCenter.y < targetCenter.y
      || (sourceCenter.y === targetCenter.y && sourceCenter.x <= targetCenter.x);
    const visualSourceCell = sourceComesFirst ? sourceCell : targetCell;
    const visualTargetCell = sourceComesFirst ? targetCell : sourceCell;
    const pairKey = `${visualSourceCell}__${visualTargetCell}`;
    const relationship = resolveRelationshipText(edge.labels);
    const group = edgeGroups.get(pairKey) || {
      edge,
      visualSourceCell,
      visualTargetCell,
      visualSourceNode: sourceComesFirst ? sourceNode : targetNode,
      visualTargetNode: sourceComesFirst ? targetNode : sourceNode,
      hasForwardEdge: false,
      hasReverseEdge: false,
      forwardRelationships: new Set<string>(),
      reverseRelationships: new Set<string>(),
    };

    if (sourceCell === visualSourceCell) {
      group.hasForwardEdge = true;
      if (relationship) {
        group.forwardRelationships.add(relationship);
      }
    } else {
      group.hasReverseEdge = true;
      if (relationship) {
        group.reverseRelationships.add(relationship);
      }
    }
    edgeGroups.set(pairKey, group);
  });

  return {
    nodes: graphData.nodes.map((node) => {
      const centerX = node.x + node.width / 2;
      const centerY = node.y + node.height / 2;
      const selected = Number(node.attrs?.body?.strokeWidth || 1) > 1;
      const iconX = (COMPACT_NODE.iconColumnWidth - COMPACT_NODE.iconSize) / 2;
      const iconY = (COMPACT_NODE.height - COMPACT_NODE.iconSize) / 2;

      return {
        ...node,
        x: centerX - COMPACT_NODE.width / 2,
        y: centerY - COMPACT_NODE.height / 2,
        width: COMPACT_NODE.width,
        height: COMPACT_NODE.height,
        attrs: {
          ...node.attrs,
          pulseHalo: {
            ...(node.attrs?.pulseHalo || {}),
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            opacity: 0,
          },
          body: {
            ...(node.attrs?.body || {}),
            rx: 6,
            ry: 6,
            fill: 'var(--color-bg)',
            fillOpacity: 1,
            opacity: 1,
            stroke: selected ? 'var(--color-primary)' : 'var(--color-border-3)',
            strokeWidth: selected ? 1.5 : 1,
            filter: 'drop-shadow(0 2px 4px var(--color-portal-card-shadow))',
            cursor: 'pointer',
            pointerEvents: 'all',
          },
          iconColumn: {
            ...(node.attrs?.iconColumn || {}),
            x: 1,
            y: 1,
            width: COMPACT_NODE.iconColumnWidth - 1,
            height: COMPACT_NODE.height - 2,
            rx: 5,
            ry: 5,
            fill: selected
              ? 'color-mix(in srgb, var(--color-primary) 8%, var(--color-bg))'
              : 'color-mix(in srgb, var(--color-fill-1) 55%, var(--color-bg))',
            fillOpacity: 1,
            stroke: 'transparent',
          },
          divider: {
            ...(node.attrs?.divider || {}),
            x1: COMPACT_NODE.iconColumnWidth,
            y1: 10,
            x2: COMPACT_NODE.iconColumnWidth,
            y2: COMPACT_NODE.height - 10,
            stroke: 'var(--color-border-2)',
            strokeWidth: 1,
            opacity: 1,
          },
          iconPlate: {
            ...(node.attrs?.iconPlate || {}),
            width: 0,
            height: 0,
            fill: 'transparent',
            stroke: 'transparent',
            strokeWidth: 0,
          },
          img: {
            ...(node.attrs?.img || {}),
            width: COMPACT_NODE.iconSize,
            height: COMPACT_NODE.iconSize,
            x: iconX,
            y: iconY,
          },
          statusDot: {
            ...(node.attrs?.statusDot || {}),
            cx: COMPACT_NODE.width - 14,
            cy: 13,
            r: 3,
          },
          alertBadge: {
            ...(node.attrs?.alertBadge || {}),
            cx: COMPACT_NODE.width - 1,
            cy: 1,
            r: 8,
          },
          alertBadgeText: {
            ...(node.attrs?.alertBadgeText || {}),
            refX: COMPACT_NODE.width - 1,
            refY: 1,
            fontSize: 9,
          },
          lbl: {
            ...(node.attrs?.lbl || {}),
            refX: null,
            refY: null,
            x: COMPACT_NODE.labelX,
            y: 27,
            textAnchor: 'start',
            textVerticalAnchor: 'middle',
            fill: 'var(--color-text-1)',
            fontSize: 14,
            fontWeight: 600,
            textWrap: {
              width: COMPACT_NODE.labelWidth,
              height: 22,
              ellipsis: true,
            },
          },
          subLbl: {
            ...(node.attrs?.subLbl || {}),
            refX: null,
            refY: null,
            x: COMPACT_NODE.labelX,
            y: 47,
            textAnchor: 'start',
            textVerticalAnchor: 'middle',
            fill: 'var(--color-text-3)',
            fontSize: 12,
            fontWeight: 400,
            opacity: 1,
            textWrap: {
              width: COMPACT_NODE.labelWidth,
              height: 18,
              ellipsis: true,
            },
          },
        },
      };
    }),
    edges: Array.from(edgeGroups.values()).map((group) => {
      const sourceCenter = resolveGraphNodeCenter(group.visualSourceNode);
      const targetCenter = resolveGraphNodeCenter(group.visualTargetNode);
      const vertical = sourceCenter.y !== targetCenter.y;
      const sourceLayerIndex = resolveGraphLayerIndex(group.visualSourceNode);
      const targetLayerIndex = resolveGraphLayerIndex(group.visualTargetNode);
      const crossesLayer = Math.abs(targetLayerIndex - sourceLayerIndex) > 1;
      const forwardRelationships = Array.from(group.forwardRelationships);
      const reverseRelationships = Array.from(group.reverseRelationships);
      const hasForward = group.hasForwardEdge;
      const hasReverse = group.hasReverseEdge;
      const marker = {
        name: 'block',
        width: 6,
        height: 6,
      };
      const relationshipLines = [
        ...(forwardRelationships.length
          ? [`${forwardRelationships.join(' / ')} ${vertical ? '↓' : '→'}`]
          : []),
        ...(reverseRelationships.length
          ? [`${reverseRelationships.join(' / ')} ${vertical ? '↑' : '←'}`]
          : []),
      ];
      const sourcePoint = vertical
        ? { x: sourceCenter.x, y: sourceCenter.y + COMPACT_NODE.height / 2 }
        : { x: sourceCenter.x + COMPACT_NODE.width / 2, y: sourceCenter.y };
      const targetPoint = vertical
        ? { x: targetCenter.x, y: targetCenter.y - COMPACT_NODE.height / 2 }
        : { x: targetCenter.x - COMPACT_NODE.width / 2, y: targetCenter.y };
      return {
        ...group.edge,
        source: sourcePoint,
        target: targetPoint,
        ...(crossesLayer
          ? {
            vertices: buildCrossLayerVertices(sourceCenter, targetCenter, graphData.nodes),
            connector: { name: 'rounded', args: { radius: 10 } },
          }
          : { vertices: undefined, connector: { name: 'normal' } }),
        attrs: {
          ...group.edge.attrs,
          line: {
            ...(group.edge.attrs?.line || {}),
            stroke: 'color-mix(in srgb, var(--color-text-3) 65%, var(--color-border-3))',
            strokeOpacity: 0.78,
            strokeWidth: 1.35,
            sourceMarker: hasReverse ? marker : null,
            targetMarker: hasForward ? marker : null,
            filter: 'none',
            cursor: 'pointer',
          },
        },
        data: {
          sourceNodeId: group.visualSourceCell,
          targetNodeId: group.visualTargetCell,
        },
        labels: relationshipLines.length
          ? [buildRelationshipLabel(relationshipLines.join('\n'))]
          : [],
      };
    }),
  };
}

function resolveRootNode(topology: ApplicationResourceTopologyData): ApplicationResourceNode {
  const systemNode = [...(topology.nodes || [])]
    .filter((node) => node.model_id === 'system')
    .sort((a, b) => a.hop - b.hop || a.name.localeCompare(b.name))[0];
  return systemNode || topology.center;
}

function resolveLayer(
  topology: ApplicationResourceTopologyData,
  node: ApplicationResourceNode,
  rootNode: ApplicationResourceNode
): LayerKey {
  if (node.id === rootNode.id) return 'root';
  if (node.category === 'application') return 'service';
  if (node.model_id === 'host') return 'host';
  if (
    node.category === 'middleware' ||
    node.category === 'database' ||
    node.category === 'cache' ||
    node.category === 'message_queue'
  ) {
    return 'appService';
  }
  if (node.category === 'host') {
    const linkedToHost = topology.links.some((link) => {
      if (link.source === node.id) {
        return topology.nodes.find((item) => item.id === link.target)?.model_id === 'host';
      }
      if (link.target === node.id) {
        return topology.nodes.find((item) => item.id === link.source)?.model_id === 'host';
      }
      return false;
    });
    if (linkedToHost) return 'infrastructure';
  }
  return 'infrastructure';
}

function buildLayeredGraphData(params: {
  topology: ApplicationResourceTopologyData;
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
}) {
  const { topology, t } = params;
  const rootNode = resolveRootNode(topology);
  const orderedNodes = [...topology.nodes].sort(
    (a, b) => a.hop - b.hop || a.name.localeCompare(b.name)
  );
  const byLayer = new Map<LayerKey, ApplicationResourceNode[]>();
  orderedNodes.forEach((node) => {
    const layer = resolveLayer(topology, node, rootNode);
    const list = byLayer.get(layer) || [];
    list.push(node);
    byLayer.set(layer, list);
  });

  const layerSpacing: Record<LayerKey, number> = {
    root: 0,
    service: 320,
    host: 300,
    appService: 300,
    infrastructure: 300,
  };

  const resolveLaneX = (layer: LayerKey, index: number) => {
    if (layer === 'root') return 0;
    return 220 + index * layerSpacing[layer];
  };

  const serviceNodes = byLayer.get('service') || [];
  const serviceCenterX = serviceNodes.length
    ? serviceNodes
      .map((item, index) => resolveLaneX('service', index))
      .reduce((sum, value) => sum + value, 0) / serviceNodes.length
    : 620;

  const positionedNodes = orderedNodes.map((node) => {
    const layer = resolveLayer(topology, node, rootNode);
    const laneNodes = byLayer.get(layer) || [];
    const index = laneNodes.findIndex((item) => item.id === node.id);
    const x = layer === 'root' ? serviceCenterX : resolveLaneX(layer, index);
    return {
      id: node.id,
      modelId: node.model_id,
      name: node.name,
      subtitle: `${node.model_id} · ${t(GROUP_LABELS[node.category] || GROUP_LABELS.other)}`,
      hop: node.hop,
      status: 'normal' as NetworkTopologyNodeStatus,
      x,
      y: LAYER_META[layer].y,
    };
  });

  const links: Array<VisualLink & { curveOffset: number }> = topology.links.map((link) => ({
    id: link.id,
    source: link.source,
    target: link.target,
    sourcePort: link.asst_id || '',
    targetPort: link.model_asst_id || '',
    curveOffset: 0,
  }));

  return buildNetworkTopologyX6GraphData({
    nodes: positionedNodes,
    links,
    centerId: undefined,
    selectedNodeId: undefined,
    activeNodeIds: new Set(),
    activeLinkIds: new Set(),
    dimInactive: false,
    showStatusDot: false,
  });
}

function mergeTopology(
  current: ApplicationResourceTopologyData | null,
  incoming: ApplicationResourceTopologyData
): ApplicationResourceTopologyData {
  if (!current) return incoming;

  const nodes = new Map<string, ApplicationResourceNode>();
  for (const node of current.nodes) nodes.set(node.id, node);
  for (const node of incoming.nodes) {
    const existing = nodes.get(node.id);
    if (!existing || node.hop < existing.hop) {
      nodes.set(node.id, node);
    }
  }

  const links = new Map<string, ApplicationResourceLink>();
  for (const link of current.links) links.set(link.id, link);
  for (const link of incoming.links) links.set(link.id, link);

  return {
    center: current.center,
    nodes: Array.from(nodes.values()).sort((a, b) => a.hop - b.hop || a.name.localeCompare(b.name)),
    links: Array.from(links.values()),
    truncated: current.truncated || incoming.truncated,
  };
}

const LOCAL_REVIEW_INSTANCE_ID = '303';

function withLocalRelationshipScenarios(
  data: ApplicationResourceTopologyData,
  instanceId: string
): ApplicationResourceTopologyData {
  if (process.env.NODE_ENV !== 'development' || instanceId !== LOCAL_REVIEW_INSTANCE_ID) {
    return data;
  }

  const rootNode = resolveRootNode(data);
  if (rootNode.model_id !== 'system') return data;
  const serviceNode = data.nodes.find(
    (node) => node.id !== rootNode.id && node.category === 'application'
  );
  const hostNode = data.nodes.find((node) => node.model_id === 'host');
  if (!serviceNode) return data;

  const scenarioLinks: ApplicationResourceLink[] = [
    {
      id: `local-multi-${rootNode.id}-${serviceNode.id}`,
      source: rootNode.id,
      target: serviceNode.id,
      asst_id: 'depends_on',
      model_asst_id: 'is_depended_on_by',
    },
    {
      id: `local-reverse-${serviceNode.id}-${rootNode.id}`,
      source: serviceNode.id,
      target: rootNode.id,
      asst_id: 'reports_to',
      model_asst_id: 'receives_report_from',
    },
    ...(hostNode
      ? [{
        id: `local-cross-layer-${rootNode.id}-${hostNode.id}`,
        source: rootNode.id,
        target: hostNode.id,
        asst_id: 'observes',
        model_asst_id: 'is_observed_by',
      }]
      : []),
  ];
  const existingIds = new Set(data.links.map((link) => link.id));

  return {
    ...data,
    links: [
      ...data.links,
      ...scenarioLinks.filter((link) => !existingIds.has(link.id)),
    ],
  };
}

export default function ApplicationResourceOverview({ modelId, instId }: Props) {
  const { t } = useTranslation();
  const {
    getApplicationResourceTopology,
    getApplicationResourceInstances,
    exportApplicationResourceInstances,
  } = useInstanceApi();
  const [loading, setLoading] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<OverviewTarget | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('topology');
  const [topology, setTopology] = useState<ApplicationResourceTopologyData | null>(null);
  const [resources, setResources] = useState<ApplicationResourceInstanceListData | null>(null);
  const [nodeContextMenu, setNodeContextMenu] = useState<NodeContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    nodeId: '',
  });
  const [relationsOpen, setRelationsOpen] = useState(false);
  const topologyCardRef = useRef<HTMLDivElement | null>(null);
  const relationsButtonRef = useRef<HTMLAnchorElement | HTMLButtonElement | null>(null);
  const graphViewportFrameRef = useRef<number | null>(null);
  const [graphInstance, setGraphInstance] = useState<Graph | null>(null);
  const [graphViewport, setGraphViewport] = useState({ scaleY: 1, translateY: 0 });
  const initialDepth = modelId === 'system' ? 2 : 1;

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      setLoading(true);
      try {
        if (!cancelled) {
          setSelectedTarget({ id: instId, name: instId, model_id: modelId });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instId, modelId]);

  useEffect(() => {
    let cancelled = false;
    async function loadApplicationData() {
      if (!selectedTarget) return;
      setLoading(true);
      try {
        const topologyRes = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, initialDepth);
        const topologyData = withLocalRelationshipScenarios(topologyRes, selectedTarget.id);
        const resourceRes = await getApplicationResourceInstances(
          selectedTarget.model_id,
          selectedTarget.id,
          (topologyData?.nodes || []).map((node: ApplicationResourceNode) => node.id)
        );
        if (cancelled) return;
        setSelectedTarget((current) =>
          current ? { ...current, name: topologyData?.center?.name || current.name } : current
        );
        setTopology(topologyData);
        setResources(resourceRes);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (selectedTarget) loadApplicationData();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialDepth, selectedTarget?.id, selectedTarget?.model_id]);

  const topologyNodeMap = useMemo(() => {
    return new Map((topology?.nodes || []).map((node) => [node.id, node]));
  }, [topology]);

  const topologyNodesForCanvas = useMemo<VisualNode[]>(() => {
    return (topology?.nodes || []).map((node) => ({
      id: node.id,
      modelId: node.model_id,
      name: node.name,
      subtitle: `${node.model_id} · ${t(GROUP_LABELS[node.category] || GROUP_LABELS.other)}`,
      hop: node.hop,
      status: 'normal',
    }));
  }, [t, topology]);

  const graphData = useMemo(() => {
    if (!topologyNodesForCanvas.length) return { nodes: [], edges: [] };
    return buildCompactGraphData(
      buildLayeredGraphData({
        topology: topology as ApplicationResourceTopologyData,
        t,
      })
    );
  }, [
    topology,
    topologyNodesForCanvas,
  ]);

  useEffect(() => {
    const graph = graphInstance;
    if (!graph) return undefined;

    const syncViewport = () => {
      if (graphViewportFrameRef.current !== null) return;
      graphViewportFrameRef.current = window.requestAnimationFrame(() => {
        graphViewportFrameRef.current = null;
        const matrix = graph.matrix();
        setGraphViewport((current) => {
          if (
            Math.abs(current.scaleY - matrix.d) < 0.001
            && Math.abs(current.translateY - matrix.f) < 0.1
          ) {
            return current;
          }
          return { scaleY: matrix.d, translateY: matrix.f };
        });
      });
    };

    syncViewport();
    graph.on('scale', syncViewport);
    graph.on('translate', syncViewport);

    return () => {
      if (graphViewportFrameRef.current !== null) {
        window.cancelAnimationFrame(graphViewportFrameRef.current);
        graphViewportFrameRef.current = null;
      }
      graph.off('scale', syncViewport);
      graph.off('translate', syncViewport);
    };
  }, [graphInstance]);

  useEffect(() => {
    const graph = graphInstance;
    if (!graph) return undefined;

    const hoveredNodeIds = new Set<string>();
    const hoveredEdgeIds = new Set<string>();
    const nodeAttrs = new Map(graphData.nodes.map((node) => [String(node.id), node.attrs]));
    const edgeAttrs = new Map(graphData.edges.map((edge) => [String(edge.id), edge.attrs]));

    const applyHoverState = () => {
      graph.getNodes().forEach((node) => {
        const active = hoveredNodeIds.has(String(node.id));
        const original = nodeAttrs.get(String(node.id));
        node.attr({
          body: {
            stroke: active ? 'var(--color-primary)' : original?.body?.stroke,
            strokeWidth: active ? 1.8 : original?.body?.strokeWidth,
            filter: active
              ? 'drop-shadow(0 4px 8px var(--color-portal-card-shadow))'
              : original?.body?.filter,
          },
          iconColumn: {
            fill: active
              ? 'color-mix(in srgb, var(--color-primary) 10%, var(--color-bg))'
              : original?.iconColumn?.fill,
          },
        });
      });

      graph.getEdges().forEach((edge) => {
        const data = edge.getData() as { sourceNodeId?: string; targetNodeId?: string } | undefined;
        const active = hoveredEdgeIds.has(String(edge.id))
          || hoveredNodeIds.has(String(data?.sourceNodeId || ''))
          || hoveredNodeIds.has(String(data?.targetNodeId || ''));
        const original = edgeAttrs.get(String(edge.id));
        edge.attr({
          line: {
            stroke: active ? 'var(--color-primary)' : original?.line?.stroke,
            strokeOpacity: active ? 0.95 : original?.line?.strokeOpacity,
            strokeWidth: active ? 2 : original?.line?.strokeWidth,
          },
        });
      });
    };

    const handleNodeEnter = ({ node }: { node: Node }) => {
      hoveredNodeIds.add(String(node.id));
      applyHoverState();
    };
    const handleNodeLeave = ({ node }: { node: Node }) => {
      hoveredNodeIds.delete(String(node.id));
      applyHoverState();
    };
    const handleEdgeEnter = ({ edge }: { edge: Edge }) => {
      hoveredEdgeIds.add(String(edge.id));
      applyHoverState();
    };
    const handleEdgeLeave = ({ edge }: { edge: Edge }) => {
      hoveredEdgeIds.delete(String(edge.id));
      applyHoverState();
    };

    graph.on('node:mouseenter', handleNodeEnter);
    graph.on('node:mouseleave', handleNodeLeave);
    graph.on('edge:mouseenter', handleEdgeEnter);
    graph.on('edge:mouseleave', handleEdgeLeave);

    return () => {
      graph.off('node:mouseenter', handleNodeEnter);
      graph.off('node:mouseleave', handleNodeLeave);
      graph.off('edge:mouseenter', handleEdgeEnter);
      graph.off('edge:mouseleave', handleEdgeLeave);
    };
  }, [graphData, graphInstance]);

  const handleReset = async () => {
    if (!selectedTarget) return;
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, initialDepth);
      const topologyData = withLocalRelationshipScenarios(res, selectedTarget.id);
      setTopology(topologyData);
      const resourceRes = await getApplicationResourceInstances(
        selectedTarget.model_id,
        selectedTarget.id,
        (topologyData?.nodes || []).map((node: ApplicationResourceNode) => node.id)
      );
      setResources(resourceRes);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandNode = async (node: ApplicationResourceNode, depth: number) => {
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(node.model_id, node.id, depth);
      const mergedTopology = mergeTopology(topology, res);
      setTopology(mergedTopology);
      const resourceRes = await getApplicationResourceInstances(
        selectedTarget?.model_id || modelId,
        selectedTarget?.id || instId,
        (mergedTopology?.nodes || []).map((item: ApplicationResourceNode) => item.id)
      );
      setResources(resourceRes);
    } finally {
      setLoading(false);
    }
  };

  const closeNodeContextMenu = () => {
    setNodeContextMenu((current) => ({ ...current, visible: false }));
  };

  const linkColumns = useMemo(() => [
    {
      title: t('ApplicationResourceOverview.linkSource'),
      dataIndex: 'source',
      width: '39%',
      render: (value: string) => {
        const text = topologyNodeMap.get(value)?.name || value;
        return <EllipsisWithTooltip text={text} className={styles.relationCell} />;
      },
    },
    {
      title: t('ApplicationResourceOverview.linkType'),
      dataIndex: 'asst_id',
      width: '22%',
      render: (value: string) => (
        <EllipsisWithTooltip text={value || '--'} className={styles.relationCell} />
      ),
    },
    {
      title: t('ApplicationResourceOverview.linkTarget'),
      dataIndex: 'target',
      width: '39%',
      render: (value: string) => {
        const text = topologyNodeMap.get(value)?.name || value;
        return <EllipsisWithTooltip text={text} className={styles.relationCell} />;
      },
    },
  ], [t, topologyNodeMap]);

  if (loading && !selectedTarget) {
    return <Spin spinning />;
  }

  if (!selectedTarget) {
    return <Empty description={t('ApplicationResourceOverview.emptyApps')} />;
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" className={styles.overview} size={16}>
        <Radio.Group
          className={styles.viewSwitch}
          value={viewMode}
          onChange={(event) => setViewMode(event.target.value)}
          size="small"
          optionType="button"
          buttonStyle="solid"
          options={[
            { label: t('ApplicationResourceOverview.topologyTab'), value: 'topology' },
            { label: t('ApplicationResourceOverview.resourcesTab'), value: 'resources' },
          ]}
        />

        {viewMode === 'topology' && (
          <Space direction="vertical" className={styles.topologyStack} size={16}>
            {topology?.truncated && (
              <Alert type="warning" showIcon message={t('ApplicationResourceOverview.truncated')} />
            )}

            <Card
              size="small"
              className={styles.canvasCard}
              styles={{ body: { padding: 0 } }}
            >
              <div className={styles.canvasShell}>
                <div
                  ref={topologyCardRef}
                  className={styles.graphPane}
                >
                  {!topology?.nodes?.length ? (
                    <div className={styles.graphEmpty}>
                      <Empty description={t('ApplicationResourceOverview.emptyLinks')} />
                    </div>
                  ) : (
                    <>
                      <div className={styles.layerBands}>
                        {(Object.keys(LAYER_META) as LayerKey[]).map((key, index, keys) => {
                          const center = graphViewport.translateY
                            + LAYER_META[key].y * graphViewport.scaleY;
                          const previousCenter = index > 0
                            ? graphViewport.translateY
                              + LAYER_META[keys[index - 1]].y * graphViewport.scaleY
                            : 0;
                          const nextCenter = index < keys.length - 1
                            ? graphViewport.translateY
                              + LAYER_META[keys[index + 1]].y * graphViewport.scaleY
                            : 0;
                          const top = index === 0 ? 0 : (previousCenter + center) / 2;
                          const isLast = index === keys.length - 1;
                          return (
                            <div
                              key={key}
                              className={styles.layerBand}
                              style={isLast
                                ? { top, bottom: 0 }
                                : { top, height: (center + nextCenter) / 2 - top }}
                            />
                          );
                        })}
                      </div>
                      <div className={styles.graphCanvas}>
                        <NetworkTopologyX6Canvas
                          data={graphData}
                          centerId={topology.center.id}
                          nodeMovable={false}
                          minimap={{ width: 160, height: 96 }}
                          fitViewKey={`app-topology-${graphData.nodes.length}-${graphData.edges.length}`}
                          fitViewOptions={{ padding: 48, maxScale: 1 }}
                          onGraphReady={setGraphInstance}
                          onNodeClick={closeNodeContextMenu}
                          onNodeContextMenu={(nodeId, event) => {
                            const node = topologyNodeMap.get(nodeId);
                            if (!node) return;
                            const containerRect = topologyCardRef.current?.getBoundingClientRect();
                            const relativeX = containerRect ? event.clientX - containerRect.left : event.clientX;
                            const relativeY = containerRect ? event.clientY - containerRect.top : event.clientY;
                            setNodeContextMenu({
                              visible: true,
                              x: Math.max(12, Math.min(relativeX, (containerRect?.width || 0) - 176)),
                              y: Math.max(12, Math.min(relativeY, (containerRect?.height || 0) - 164)),
                              nodeId,
                            });
                          }}
                          onBlankClick={closeNodeContextMenu}
                          onBlankContextMenu={closeNodeContextMenu}
                          toolbar={{
                            align: 'split',
                            labels: {
                              zoomOut: t('Model.networkTopoZoomOut'),
                              zoomIn: t('Model.networkTopoZoomIn'),
                              fitView: t('Model.networkTopoFitView'),
                              exportImage: t('Model.exportImage'),
                              refresh: t('ApplicationResourceOverview.refresh'),
                            },
                            prefix: (
                              <div className={styles.toolbarActions}>
                                {!relationsOpen && (
                                  <Button
                                    ref={relationsButtonRef}
                                    size="small"
                                    icon={<ShareAltOutlined />}
                                    aria-expanded={false}
                                    aria-controls="application-topology-relations"
                                    disabled={!topology.links.length}
                                    onClick={() => {
                                      closeNodeContextMenu();
                                      setRelationsOpen(true);
                                    }}
                                  >
                                    {t('ApplicationResourceOverview.linksTitle')}
                                    <span className={styles.relationCount}>{topology.links.length}</span>
                                  </Button>
                                )}
                              </div>
                            ),
                            onRefresh: handleReset,
                            refreshLoading: loading,
                          }}
                        />
                      </div>
                      <div className={styles.layerLabels}>
                        {(Object.keys(LAYER_META) as LayerKey[]).map((key) => (
                          <div
                            key={key}
                            className={styles.layerLabel}
                            style={{
                              top: graphViewport.translateY
                                + LAYER_META[key].y * graphViewport.scaleY,
                            }}
                          >
                            <span>{getLayerTitle(key, t)}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  {nodeContextMenu.visible && topologyNodeMap.get(nodeContextMenu.nodeId) && (
                    <div
                      className={styles.contextMenu}
                      style={{ left: nodeContextMenu.x, top: nodeContextMenu.y }}
                    >
                      <div className={styles.contextMenuTitle}>
                        {topologyNodeMap.get(nodeContextMenu.nodeId)?.name}
                      </div>
                      <Space
                        direction="vertical"
                        size={2}
                        className={styles.contextMenuActions}
                      >
                        {[1, 2, 3].map((depth) => (
                          <Button
                            key={depth}
                            block
                            size="small"
                            onClick={() => handleExpandNode(
                              topologyNodeMap.get(nodeContextMenu.nodeId) as ApplicationResourceNode,
                              depth
                            )}
                          >
                            {t(
                              depth === 1
                                ? 'ApplicationResourceOverview.expandOne'
                                : depth === 2
                                  ? 'ApplicationResourceOverview.expandTwo'
                                  : 'ApplicationResourceOverview.expandThree'
                            )}
                          </Button>
                        ))}
                      </Space>
                    </div>
                  )}
                </div>

                <aside
                  id="application-topology-relations"
                  aria-label={t('ApplicationResourceOverview.linksTitle')}
                  aria-hidden={!relationsOpen}
                  className={`${styles.relationsPanel} ${relationsOpen ? styles.relationsPanelOpen : ''}`}
                >
                  <div className={styles.relationsPanelInner}>
                    <div className={styles.relationsHeader}>
                      <div className={styles.relationsTitle}>
                        <ShareAltOutlined aria-hidden="true" />
                        <span>{t('ApplicationResourceOverview.linksTitle')}</span>
                        <span className={styles.relationCount}>{topology?.links?.length || 0}</span>
                      </div>
                      <Button
                        type="text"
                        className={styles.relationsClose}
                        aria-label={t('common.close')}
                        icon={<DoubleRightOutlined />}
                        tabIndex={relationsOpen ? 0 : -1}
                        onClick={() => {
                          setRelationsOpen(false);
                          window.requestAnimationFrame(() => relationsButtonRef.current?.focus());
                        }}
                      />
                    </div>
                    <div className={styles.relationsTable}>
                      {!topology?.links?.length ? (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={t('ApplicationResourceOverview.emptyLinks')}
                        />
                      ) : (
                        <Table
                          rowKey="id"
                          size="small"
                          pagination={false}
                          tableLayout="fixed"
                          scroll={{ y: 'calc(100vh - 308px)' }}
                          dataSource={topology.links}
                          columns={linkColumns}
                        />
                      )}
                    </div>
                  </div>
                </aside>
              </div>
            </Card>
          </Space>
        )}

        {viewMode === 'resources' && (
          <Space direction="vertical" className={styles.resourceStack} size={16}>
            <Flex justify="end">
              <Button
                icon={<DownloadOutlined />}
                onClick={async () => {
                  if (!topology?.nodes?.length || !selectedTarget) return;
                  const blob = await exportApplicationResourceInstances(
                    selectedTarget.model_id,
                    selectedTarget.id,
                    topology.nodes.map((node) => node.id)
                  );
                  const url = window.URL.createObjectURL(new Blob([blob]));
                  const link = document.createElement('a');
                  link.href = url;
                  link.download = 'application_topology_instances.xlsx';
                  link.click();
                  window.URL.revokeObjectURL(url);
                }}
                disabled={!topology?.nodes?.length}
              >
                {t('ApplicationResourceOverview.export')}
              </Button>
            </Flex>

            {!resources?.groups?.length ? (
              <Empty description={t('ApplicationResourceOverview.emptyResources')} />
            ) : (
              resources.groups.map((group) => (
                <Card
                  key={group.model_id}
                  size="small"
                  title={`${group.model_id} (${group.count})`}
                >
                  <Table<Record<string, string>>
                    rowKey={(record, index) => `${group.model_id}-${record.inst_name || index}`}
                    size="small"
                    pagination={false}
                    scroll={{ x: 'max-content' }}
                    dataSource={group.items}
                    columns={group.column_defs.map((column) => ({
                      title: column.title,
                      dataIndex: column.key,
                      key: column.key,
                      render: (value: string) => {
                        const text = value == null ? '' : String(value);
                        return (
                          <span title={text}>
                            {text}
                          </span>
                        );
                      },
                    }))}
                  />
                </Card>
              ))
            )}
          </Space>
        )}
      </Space>
    </Spin>
  );
}
