'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Flex,
  Input,
  Radio,
  Space,
  Spin,
  Table,
} from 'antd';
import {
  DownloadOutlined,
  DoubleRightOutlined,
  SearchOutlined,
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
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import type {
  ApplicationResourceLink,
  ApplicationResourceInstanceListData,
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '@/app/cmdb/types/applicationResourceOverview';
import { buildBaseInfoPath } from '@/app/cmdb/(pages)/views/viewUrls';
import {
  DEFAULT_LANE_WIDTH,
  LAYER_KEYS,
  LAYER_LABEL_RAIL_PX,
  LAYER_TITLE_KEYS,
  ROW_STRIDE,
  packLayeredNodes,
  resolveBandIndex,
  type LayerBand,
  type LayerKey,
} from './layerLayout';
import { resolveLayer } from './resolveLayer';
import {
  centerTopologyNode,
  filterRelationLinks,
  filterTopologyNodes,
  resolveNeighborhood,
} from './nodeFocus';
import { filterResourceGroups } from './resourceInventory';
import ExpandDepthControl from './ExpandDepthControl';
import {
  APP_TOPO_DEFAULT_EXPAND_DEPTH,
  readAppTopoExpandDepth,
  writeAppTopoExpandDepth,
  type AppTopoExpandDepth,
} from './expandDepth';
import styles from './index.module.scss';

interface Props {
  modelId: string;
  instUuid: string;
  fillContainer?: boolean;
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

interface RelationshipEdgeData {
  sourceNodeId?: string;
  targetNodeId?: string;
  relationshipIds?: string[];
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

const COMPACT_NODE = {
  width: 248,
  height: 68,
  iconColumnWidth: 50,
  iconSize: 34,
  labelX: 62,
  labelWidth: 170,
} as const;

const HOVER_COLOR = 'color-mix(in srgb, var(--color-primary) 72%, var(--color-bg))';

const RELATIONSHIP_LABEL_ATTRS = {
  textFill: 'var(--color-text-3)',
  activeTextFill: HOVER_COLOR,
  bgFill: 'var(--color-bg)',
  activeBgFill: 'var(--color-primary-bg-active)',
  bgStroke: 'var(--color-border-2)',
  activeBgStroke: HOVER_COLOR,
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
      fill: RELATIONSHIP_LABEL_ATTRS.textFill,
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
      fill: RELATIONSHIP_LABEL_ATTRS.bgFill,
      fillOpacity: 0.94,
      stroke: RELATIONSHIP_LABEL_ATTRS.bgStroke,
      strokeWidth: 1,
      rx: 4,
      ry: 4,
    },
  },
});

const buildHoverLabels = (labels: unknown, active: boolean) => {
  if (!Array.isArray(labels)) return labels;
  return labels.map((label) => {
    if (!label || typeof label !== 'object') return label;
    const typedLabel = label as { attrs?: { txt?: Record<string, unknown>; bg?: Record<string, unknown> } };
    const attrs = typedLabel.attrs || {};
    return {
      ...typedLabel,
      attrs: {
        ...attrs,
        txt: {
          ...(attrs.txt || {}),
          fill: active
            ? RELATIONSHIP_LABEL_ATTRS.activeTextFill
            : RELATIONSHIP_LABEL_ATTRS.textFill,
          fontWeight: active ? 700 : 500,
        },
        bg: {
          ...(attrs.bg || {}),
          fill: active
            ? RELATIONSHIP_LABEL_ATTRS.activeBgFill
            : RELATIONSHIP_LABEL_ATTRS.bgFill,
          stroke: active
            ? RELATIONSHIP_LABEL_ATTRS.activeBgStroke
            : RELATIONSHIP_LABEL_ATTRS.bgStroke,
          strokeWidth: active ? 1.35 : 1,
          fillOpacity: active ? 0.98 : 0.94,
          filter: active
            ? 'drop-shadow(0 3px 6px var(--color-portal-card-shadow))'
            : 'none',
        },
      },
    };
  });
};

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

const resolveGraphLayerIndex = (
  node: ReturnType<typeof buildNetworkTopologyX6GraphData>['nodes'][number],
  bands: LayerBand[],
) => resolveBandIndex(resolveGraphNodeCenter(node).y, bands);

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
  return t(LAYER_TITLE_KEYS[key]);
}

function buildCompactGraphData(
  graphData: ReturnType<typeof buildNetworkTopologyX6GraphData>,
  bands: LayerBand[],
) {
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
    relationshipIds: Set<string>;
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
      relationshipIds: new Set<string>(),
    };

    group.relationshipIds.add(String(edge.id));
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
      const sourceLayerIndex = resolveGraphLayerIndex(group.visualSourceNode, bands);
      const targetLayerIndex = resolveGraphLayerIndex(group.visualTargetNode, bands);
      const farApart = Math.abs(targetCenter.y - sourceCenter.y) > ROW_STRIDE * 2;
      const crossesLayer = Math.abs(targetLayerIndex - sourceLayerIndex) > 1 || farApart;
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
          relationshipIds: Array.from(group.relationshipIds),
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

function buildLayeredGraphData(params: {
  topology: ApplicationResourceTopologyData;
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
  laneWidth: number;
}) {
  const { topology, t, laneWidth } = params;
  const rootNode = resolveRootNode(topology);
  const orderedNodes = [...topology.nodes].sort(
    (a, b) => a.hop - b.hop || a.name.localeCompare(b.name)
  );
  const byLayer = new Map<LayerKey, ApplicationResourceNode[]>();
  LAYER_KEYS.forEach((key) => byLayer.set(key, []));
  orderedNodes.forEach((node) => {
    const layer = resolveLayer(topology, node, rootNode);
    if (!layer) return;
    const list = byLayer.get(layer) || [];
    list.push(node);
    byLayer.set(layer, list);
  });

  const packed = packLayeredNodes({
    layers: Object.fromEntries(
      LAYER_KEYS.map((key) => [key, (byLayer.get(key) || []).map((node) => ({ id: node.id }))])
    ) as Record<LayerKey, Array<{ id: string }>>,
    laneWidth,
  });
  const positionById = new Map(packed.positions.map((item) => [item.id, item]));

  const positionedNodes = orderedNodes.flatMap((node) => {
    const packedPosition = positionById.get(node.id);
    if (!packedPosition) return [];
    return [
      {
        id: node.id,
        modelId: node.model_id,
        name: node.name,
        subtitle: `${node.model_id} · ${t(GROUP_LABELS[node.category] || GROUP_LABELS.other)}`,
        hop: node.hop,
        status: 'normal' as NetworkTopologyNodeStatus,
        x: packedPosition.x,
        y: packedPosition.y,
      },
    ];
  });

  const positionedIds = new Set(positionedNodes.map((node) => node.id));
  const links: Array<VisualLink & { curveOffset: number }> = topology.links
    .filter((link) => positionedIds.has(link.source) && positionedIds.has(link.target))
    .map((link) => ({
      id: link.id,
      source: link.source,
      target: link.target,
      sourcePort: link.asst_id || '',
      targetPort: link.model_asst_id || '',
      curveOffset: 0,
    }));

  return {
    graphData: buildNetworkTopologyX6GraphData({
      nodes: positionedNodes,
      links,
      centerId: undefined,
      selectedNodeId: undefined,
      activeNodeIds: new Set(),
      activeLinkIds: new Set(),
      dimInactive: false,
      showStatusDot: false,
    }),
    bands: packed.bands,
  };
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

export default function ApplicationResourceOverview({
  modelId,
  instUuid,
  fillContainer = false,
}: Props) {
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
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [relationQuery, setRelationQuery] = useState('');
  const [relationFocusNodeId, setRelationFocusNodeId] = useState<string | null>(null);
  const [resourceQuery, setResourceQuery] = useState('');
  const [nodeSearch, setNodeSearch] = useState('');
  const [nodeSearchOpen, setNodeSearchOpen] = useState(false);
  const [hoveredGraphNodeId, setHoveredGraphNodeId] = useState<string | null>(null);
  const [hoveredGraphEdgeId, setHoveredGraphEdgeId] = useState<string | null>(null);
  const topologyCardRef = useRef<HTMLDivElement | null>(null);
  const relationsButtonRef = useRef<HTMLAnchorElement | HTMLButtonElement | null>(null);
  const graphViewportFrameRef = useRef<number | null>(null);
  const [graphInstance, setGraphInstance] = useState<Graph | null>(null);
  const [graphViewport, setGraphViewport] = useState({ scaleY: 1, translateY: 0 });
  const [laneWidth, setLaneWidth] = useState(DEFAULT_LANE_WIDTH);
  const [expandDepth, setExpandDepth] = useState<AppTopoExpandDepth>(() =>
    typeof window === 'undefined'
      ? APP_TOPO_DEFAULT_EXPAND_DEPTH
      : readAppTopoExpandDepth(window.localStorage)
  );

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      setLoading(true);
      try {
        if (!cancelled) {
          setSelectedTarget({ id: instUuid, name: instUuid, model_id: modelId });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
     
  }, [instUuid, modelId]);

  useEffect(() => {
    let cancelled = false;
    async function loadApplicationData() {
      if (!selectedTarget) return;
      setHoveredGraphNodeId(null);
      setHoveredGraphEdgeId(null);
      setLoading(true);
      try {
        const topologyRes = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, expandDepth);
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
        setSelectedNodeId(null);
        setRelationQuery('');
        setRelationFocusNodeId(null);
        setResourceQuery('');
        setNodeSearch('');
        setNodeSearchOpen(false);
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
     
  }, [expandDepth, selectedTarget?.id, selectedTarget?.model_id]);

  const topologyNodeMap = useMemo(() => {
    return new Map((topology?.nodes || []).map((node) => [node.id, node]));
  }, [topology]);

  const neighborhood = useMemo(
    () => resolveNeighborhood(topology?.links || [], selectedNodeId),
    [selectedNodeId, topology]
  );

  const filteredRelationLinks = useMemo(
    () => filterRelationLinks(
      topology?.links || [],
      topologyNodeMap,
      relationQuery,
      relationFocusNodeId
    ),
    [relationFocusNodeId, relationQuery, topology, topologyNodeMap]
  );

  const filteredResourceGroups = useMemo(
    () => filterResourceGroups(resources?.groups || [], resourceQuery),
    [resourceQuery, resources]
  );

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

  const graphLayout = useMemo(() => {
    if (!topologyNodesForCanvas.length) {
      return { graphData: { nodes: [], edges: [] }, bands: [] as LayerBand[] };
    }
    const layered = buildLayeredGraphData({
      topology: topology as ApplicationResourceTopologyData,
      t,
      laneWidth,
    });
    return {
      graphData: buildCompactGraphData(layered.graphData, layered.bands),
      bands: layered.bands,
    };
  }, [laneWidth, t, topology, topologyNodesForCanvas]);
  const graphData = graphLayout.graphData;
  const layerBands = graphLayout.bands;

  useEffect(() => {
    const pane = topologyCardRef.current;
    if (!pane || viewMode !== 'topology') return undefined;
    const updateLaneWidth = () => {
      const next = Math.max(480, pane.clientWidth - LAYER_LABEL_RAIL_PX);
      setLaneWidth((current) => (Math.abs(current - next) < 8 ? current : next));
    };
    updateLaneWidth();
    const observer = new ResizeObserver(updateLaneWidth);
    observer.observe(pane);
    return () => observer.disconnect();
  }, [viewMode, topology?.nodes?.length]);

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

    const handleNodeEnter = ({ node }: { node: Node }) => {
      setHoveredGraphNodeId(String(node.id));
    };
    const handleNodeLeave = ({ node }: { node: Node }) => {
      setHoveredGraphNodeId((current) => (
        current === String(node.id) ? null : current
      ));
    };
    const handleEdgeEnter = ({ edge }: { edge: Edge }) => {
      setHoveredGraphEdgeId(String(edge.id));
    };
    const handleEdgeLeave = ({ edge }: { edge: Edge }) => {
      setHoveredGraphEdgeId((current) => (
        current === String(edge.id) ? null : current
      ));
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
  }, [graphInstance]);

  useEffect(() => {
    const graph = graphInstance;
    if (!graph) return;

    const nodeAttrs = new Map(graphData.nodes.map((node) => [String(node.id), node.attrs]));
    const edgeAttrs = new Map(graphData.edges.map((edge) => [String(edge.id), edge.attrs]));
    const edgeLabels = new Map(graphData.edges.map((edge) => [String(edge.id), edge.labels]));
    const edgeData = new Map(graphData.edges.map((edge) => [
      String(edge.id),
      edge.data as RelationshipEdgeData | undefined,
    ]));

    const withActiveMarker = (marker: unknown) => {
      if (!marker || typeof marker !== 'object') return marker;
      return {
        ...(marker as Record<string, unknown>),
        fill: HOVER_COLOR,
        stroke: HOVER_COLOR,
      };
    };

    const persistOn = Boolean(selectedNodeId);

    graph.getNodes().forEach((node) => {
      const nodeId = String(node.id);
      const persistActive = persistOn && neighborhood.nodeIds.has(nodeId);
      const hoverActive = hoveredGraphNodeId === nodeId;
      const highlighted = persistActive || hoverActive;
      const focused = selectedNodeId === nodeId || hoverActive;
      const dimmed = persistOn && !highlighted;
      const original = nodeAttrs.get(nodeId);
      node.attr({
        body: {
          stroke: highlighted ? HOVER_COLOR : original?.body?.stroke,
          strokeWidth: focused ? 1.6 : original?.body?.strokeWidth,
          opacity: dimmed ? 0.22 : 1,
          filter: highlighted
            ? 'drop-shadow(0 4px 8px var(--color-portal-card-shadow))'
            : original?.body?.filter,
        },
        iconColumn: {
          fill: focused
            ? 'var(--color-primary-bg-active)'
            : original?.iconColumn?.fill,
          opacity: dimmed ? 0.22 : 1,
        },
        divider: { opacity: dimmed ? 0.22 : 1 },
        img: { opacity: dimmed ? 0.22 : 1 },
        lbl: { opacity: dimmed ? 0.22 : 1 },
        subLbl: { opacity: dimmed ? 0.22 : 1 },
      });
    });

    graph.getEdges().forEach((edge) => {
      const data = edgeData.get(String(edge.id));
      const persistActive = persistOn && Boolean(
        data?.relationshipIds?.some((relationshipId) => neighborhood.linkIds.has(relationshipId))
      );
      const hoverActive = hoveredGraphEdgeId === String(edge.id)
        || hoveredGraphNodeId === String(data?.sourceNodeId || '')
        || hoveredGraphNodeId === String(data?.targetNodeId || '');
      const active = persistActive || hoverActive;
      const dimmed = persistOn && !active;
      const original = edgeAttrs.get(String(edge.id));
      (edge as Edge & { attr: (attrs: unknown) => void }).attr({
        line: {
          stroke: active ? HOVER_COLOR : original?.line?.stroke,
          strokeOpacity: dimmed ? 0.16 : (active ? 0.88 : original?.line?.strokeOpacity),
          strokeWidth: active ? 2.1 : original?.line?.strokeWidth,
          sourceMarker: active
            ? withActiveMarker(original?.line?.sourceMarker)
            : original?.line?.sourceMarker,
          targetMarker: active
            ? withActiveMarker(original?.line?.targetMarker)
            : original?.line?.targetMarker,
          filter: active
            ? 'drop-shadow(0 2px 4px var(--color-portal-card-shadow))'
            : original?.line?.filter,
        },
      });
      (edge as Edge & { setLabels?: (labels: unknown) => void }).setLabels?.(
        buildHoverLabels(edgeLabels.get(String(edge.id)), active)
      );
    });
  }, [
    graphData,
    graphInstance,
    hoveredGraphEdgeId,
    hoveredGraphNodeId,
    neighborhood,
    selectedNodeId,
  ]);

  const handleReset = async () => {
    if (!selectedTarget) return;
    setHoveredGraphNodeId(null);
    setHoveredGraphEdgeId(null);
    setSelectedNodeId(null);
    setRelationQuery('');
    setRelationFocusNodeId(null);
    setResourceQuery('');
    setNodeSearch('');
    setNodeSearchOpen(false);
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, expandDepth);
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
    setHoveredGraphNodeId(null);
    setHoveredGraphEdgeId(null);
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(node.model_id, node.id, depth);
      const mergedTopology = mergeTopology(topology, res);
      setTopology(mergedTopology);
      const resourceRes = await getApplicationResourceInstances(
        selectedTarget?.model_id || modelId,
        selectedTarget?.id || instUuid,
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

  const handleSelectNode = (nodeId: string) => {
    closeNodeContextMenu();
    setSelectedNodeId(nodeId);
  };

  const handleLocateTopologyNode = (nodeId: string) => {
    const node = topologyNodeMap.get(nodeId);
    if (node) {
      setNodeSearch(node.name);
    }
    setNodeSearchOpen(false);
    handleSelectNode(nodeId);
    window.requestAnimationFrame(() => {
      centerTopologyNode(graphInstance, nodeId);
    });
  };

  const nodeSearchOptions = useMemo(
    () => filterTopologyNodes(topology?.nodes || [], nodeSearch).map((node) => ({
      value: node.id,
      label: (
        <div className={styles.nodeSearchOption}>
          <span className={styles.nodeSearchName}>{node.name}</span>
          <span className={styles.nodeSearchMeta}>{node.model_id}</span>
        </div>
      ),
    })),
    [nodeSearch, topology]
  );

  const handleClearNodeFocus = () => {
    closeNodeContextMenu();
    setSelectedNodeId(null);
  };

  const handleViewRelations = (node: ApplicationResourceNode) => {
    closeNodeContextMenu();
    setSelectedNodeId(node.id);
    setRelationFocusNodeId(node.id);
    setRelationQuery(node.name);
    setRelationsOpen(true);
  };

  const handleViewNodeDetail = (node: ApplicationResourceNode) => {
    closeNodeContextMenu();
    window.open(
      buildBaseInfoPath({
        model_id: node.model_id,
        inst_uuid: node.id,
        inst_name: node.name,
      }),
      '_blank',
      'noopener,noreferrer'
    );
  };

  const handleOpenRelationsPanel = () => {
    closeNodeContextMenu();
    setRelationQuery('');
    setRelationFocusNodeId(null);
    setRelationsOpen(true);
  };

  const contextMenuNode = nodeContextMenu.visible
    ? topologyNodeMap.get(nodeContextMenu.nodeId)
    : undefined;

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

  const hostClassName = `${styles.overview} ${fillContainer ? styles.overviewFill : styles.overviewStandalone}`;

  if (loading && !selectedTarget) {
    return (
      <div className={hostClassName}>
        <Spin spinning className={styles.fillState} />
      </div>
    );
  }

  if (!selectedTarget) {
    return (
      <div className={hostClassName}>
        <CompactEmptyState description={t('ApplicationResourceOverview.emptyApps')} />
      </div>
    );
  }

  return (
    <Spin
      spinning={loading}
      wrapperClassName={styles.spinHost}
    >
      <div className={hostClassName}>
        <div className={styles.viewToolbar}>
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
            <>
              <AutoComplete
                className={styles.nodeSearch}
                value={nodeSearch}
                options={nodeSearchOptions}
                open={nodeSearchOpen}
                size="small"
                filterOption={false}
                notFoundContent={nodeSearch.trim() ? t('ApplicationResourceOverview.nodeSearchEmpty') : null}
                popupMatchSelectWidth
                onOpenChange={(open) => {
                  setNodeSearchOpen(open && Boolean(nodeSearch.trim()));
                }}
                onChange={(value) => {
                  const next = typeof value === 'string' ? value : '';
                  const matched = topologyNodeMap.get(next);
                  if (matched && matched.name !== next) {
                    return;
                  }
                  setNodeSearch(next);
                  setNodeSearchOpen(Boolean(next.trim()));
                }}
                onSelect={(nodeId) => {
                  handleLocateTopologyNode(String(nodeId));
                }}
              >
                <Input
                  allowClear
                  size="small"
                  prefix={<SearchOutlined />}
                  placeholder={t('ApplicationResourceOverview.nodeSearchPlaceholder')}
                  aria-label={t('ApplicationResourceOverview.nodeSearchPlaceholder')}
                />
              </AutoComplete>
              <ExpandDepthControl
                value={expandDepth}
                onChange={(depth) => {
                  setExpandDepth(depth);
                  writeAppTopoExpandDepth(window.localStorage, depth);
                }}
              />
            </>
          )}
        </div>

        {viewMode === 'topology' && (
          <div className={styles.topologyStack}>
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
                  style={{ ['--cmdb-layer-label-rail' as string]: `${LAYER_LABEL_RAIL_PX}px` }}
                  onMouseLeave={() => {
                    setHoveredGraphNodeId(null);
                    setHoveredGraphEdgeId(null);
                  }}
                >
                  {!topology?.nodes?.length ? (
                    <div className={styles.graphEmpty}>
                      <CompactEmptyState description={t('ApplicationResourceOverview.emptyLinks')} />
                    </div>
                  ) : (
                    <>
                      <div className={styles.layerBands}>
                        {layerBands.map((band, index) => {
                          const splitTop = index === 0
                            ? 0
                            : graphViewport.translateY
                              + ((layerBands[index - 1].bottom + band.top) / 2) * graphViewport.scaleY;
                          const isLast = index === layerBands.length - 1;
                          const splitBottom = isLast
                            ? 0
                            : graphViewport.translateY
                              + ((band.bottom + layerBands[index + 1].top) / 2) * graphViewport.scaleY;
                          return (
                            <div
                              key={band.key}
                              className={styles.layerBand}
                              style={isLast
                                ? { top: splitTop, bottom: 0 }
                                : { top: splitTop, height: splitBottom - splitTop }}
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
                          fitViewKey={`app-topology-${graphData.nodes.length}-${graphData.edges.length}-${laneWidth}`}
                          fitViewOptions={{ padding: 48, maxScale: 1, minScale: 0.5, align: 'start' }}
                          onGraphReady={setGraphInstance}
                          onNodeClick={handleSelectNode}
                          onNodeContextMenu={(nodeId, event) => {
                            const node = topologyNodeMap.get(nodeId);
                            if (!node) return;
                            const containerRect = topologyCardRef.current?.getBoundingClientRect();
                            const relativeX = containerRect ? event.clientX - containerRect.left : event.clientX;
                            const relativeY = containerRect ? event.clientY - containerRect.top : event.clientY;
                            setNodeContextMenu({
                              visible: true,
                              x: Math.max(12, Math.min(relativeX, (containerRect?.width || 0) - 176)),
                              y: Math.max(12, Math.min(relativeY, (containerRect?.height || 0) - 280)),
                              nodeId,
                            });
                          }}
                          onBlankClick={handleClearNodeFocus}
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
                                    onClick={handleOpenRelationsPanel}
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
                        {layerBands.map((band) => (
                          <div
                            key={band.key}
                            className={styles.layerLabel}
                            style={{
                              top: graphViewport.translateY
                                + band.labelY * graphViewport.scaleY,
                            }}
                          >
                            <span>{getLayerTitle(band.key, t)}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  {nodeContextMenu.visible && contextMenuNode && (
                    <div
                      className={styles.contextMenu}
                      style={{ left: nodeContextMenu.x, top: nodeContextMenu.y }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <div className={styles.contextMenuTitle}>
                        {contextMenuNode.name}
                      </div>
                      <Space
                        direction="vertical"
                        size={2}
                        className={styles.contextMenuActions}
                      >
                        <Button
                          block
                          size="small"
                          onClick={() => handleViewRelations(contextMenuNode)}
                        >
                          {t('ApplicationResourceOverview.viewRelations')}
                        </Button>
                        <Button
                          block
                          size="small"
                          onClick={() => handleViewNodeDetail(contextMenuNode)}
                        >
                          {t('ViewsHub.viewDetail')}
                        </Button>
                        <div className={styles.contextMenuDivider} />
                        {[1, 2, 3].map((depth) => (
                          <Button
                            key={depth}
                            block
                            size="small"
                            onClick={() => handleExpandNode(contextMenuNode, depth)}
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
                        <span className={styles.relationCount}>
                          {relationQuery.trim() || relationFocusNodeId
                            ? `${filteredRelationLinks.length} / ${topology?.links?.length || 0}`
                            : topology?.links?.length || 0}
                        </span>
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
                    <div className={styles.relationsFilter}>
                      <Input
                        allowClear
                        size="small"
                        value={relationQuery}
                        aria-label={t('ApplicationResourceOverview.relationSearchPlaceholder')}
                        placeholder={t('ApplicationResourceOverview.relationSearchPlaceholder')}
                        onChange={(event) => setRelationQuery(event.target.value)}
                      />
                    </div>
                    <div className={styles.relationsTable}>
                      {!topology?.links?.length ? (
                        <CompactEmptyState
                          description={t('ApplicationResourceOverview.emptyLinks')}
                        />
                      ) : !filteredRelationLinks.length ? (
                        <CompactEmptyState
                          description={t('ApplicationResourceOverview.emptyFilteredLinks')}
                        />
                      ) : (
                        <Table
                          rowKey="id"
                          size="small"
                          pagination={false}
                          tableLayout="fixed"
                          dataSource={filteredRelationLinks}
                          columns={linkColumns}
                        />
                      )}
                    </div>
                  </div>
                </aside>
              </div>
            </Card>
          </div>
        )}

        {viewMode === 'resources' && (
          <div className={styles.resourceStack}>
            <Flex justify="space-between" align="center" gap={12} wrap="wrap">
              <Input.Search
                allowClear
                className={styles.resourceSearch}
                value={resourceQuery}
                placeholder={t('ApplicationResourceOverview.resourceSearchPlaceholder')}
                aria-label={t('ApplicationResourceOverview.resourceSearchPlaceholder')}
                onChange={(event) => setResourceQuery(event.target.value)}
              />
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
              <CompactEmptyState description={t('ApplicationResourceOverview.emptyResources')} />
            ) : !filteredResourceGroups.length ? (
              <CompactEmptyState description={t('ApplicationResourceOverview.emptyFilteredResources')} />
            ) : (
              filteredResourceGroups.map((group) => (
                <Card
                  key={group.model_id}
                  size="small"
                  title={`${group.model_name || group.model_id} (${group.count})`}
                >
                  <Table<Record<string, string>>
                    rowKey={(record, index) => `${group.model_id}-${record.inst_uuid || record.inst_name || index}`}
                    size="small"
                    pagination={{
                      pageSize: 10,
                      showSizeChanger: true,
                      pageSizeOptions: [10, 20, 50],
                      hideOnSinglePage: true,
                    }}
                    scroll={{ x: 'max-content' }}
                    dataSource={group.items}
                    columns={group.column_defs.map((column) => ({
                      title: column.title,
                      dataIndex: column.key,
                      key: column.key,
                      ellipsis: true,
                      fixed: column.key === 'inst_name' ? 'left' : undefined,
                      width: column.key === 'inst_name' ? 220 : 180,
                      render: (value: string, record: Record<string, string>) => {
                        const text = value == null ? '' : String(value);
                        if (column.key === 'inst_name' && record.inst_uuid) {
                          return (
                            <Button
                              type="link"
                              className={styles.instanceNameLink}
                              onClick={() => {
                                window.open(
                                  buildBaseInfoPath({
                                    model_id: record.model_id || group.model_id,
                                    inst_uuid: record.inst_uuid,
                                    inst_name: record.inst_name || text,
                                  }),
                                  '_blank',
                                  'noopener,noreferrer'
                                );
                              }}
                            >
                              {text || '--'}
                            </Button>
                          );
                        }
                        return (
                          <EllipsisWithTooltip text={text || '--'} className={styles.resourceCell} />
                        );
                      },
                    }))}
                  />
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </Spin>
  );
}
