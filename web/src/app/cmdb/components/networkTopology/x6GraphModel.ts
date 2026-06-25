import { getIconUrl } from '@/app/cmdb/utils/common';
import type {
  NetworkTopologyLink,
  NetworkTopologyPositionedLink,
  NetworkTopologyPositionedNode,
} from './types';
import { NETWORK_TOPO_VISUAL, buildNetworkTopoPortLabel } from './x6Visual';

export interface BuildX6GraphDataOptions {
  nodes: NetworkTopologyPositionedNode[];
  links: NetworkTopologyPositionedLink[];
  centerId?: string;
  selectedNodeId?: string;
  activeNodeIds?: Set<string>;
  activeLinkIds?: Set<string>;
  dimInactive?: boolean;
  showStatusDot?: boolean;
}

const NODE_WIDTH = NETWORK_TOPO_VISUAL.node.width;
const NODE_HEIGHT = NETWORK_TOPO_VISUAL.node.height;
const DEVICE_NODE_SHAPE = 'topo-network-device';
const STATUS_COLOR_MAP: Record<string, string> = {
  normal: '#39c78f',
  warning: '#f5b544',
  error: '#ff4d4f',
  critical: '#ff4d4f',
};

const toOpacityAttrs = (dimmed: boolean) => ({
  opacity: dimmed ? 0.22 : 1,
});

const stripDevicePrefix = (value?: string, deviceName?: string) => {
  if (!value) return '';
  if (deviceName && value.startsWith(`${deviceName}-`)) {
    return value.slice(deviceName.length + 1);
  }
  return value;
};

const portLabel = (position: number, text: string) => ({
  ...buildNetworkTopoPortLabel(position, text),
});

export const buildNetworkTopologyX6GraphData = ({
  nodes,
  links,
  centerId,
  selectedNodeId,
  activeNodeIds = new Set(),
  activeLinkIds = new Set(),
  dimInactive = false,
  showStatusDot = false,
}: BuildX6GraphDataOptions) => {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const graphNodes = nodes.map((node) => {
    const selected = selectedNodeId === node.id || centerId === node.id;
    const active = activeNodeIds.has(node.id);
    const dimmed = dimInactive && !active;
    const alertCount = Number(node.alertCount || 0);
    const statusColor = STATUS_COLOR_MAP[node.status || 'normal'] || STATUS_COLOR_MAP.normal;
    const badgeOpacity = alertCount ? (dimmed ? 0.22 : 1) : 0;

    return {
      id: node.id,
      x: node.x - NODE_WIDTH / 2,
      y: node.y - NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      shape: DEVICE_NODE_SHAPE,
      data: {
        node,
      },
      attrs: {
        body: {
          ...(selected ? NETWORK_TOPO_VISUAL.node.activeBody : {}),
          ...(active ? { stroke: '#ff4d4f', strokeWidth: 2.4 } : {}),
          ...toOpacityAttrs(dimmed),
        },
        pulseHalo: {
          stroke: statusColor,
          opacity: node.pulse && node.status === 'critical' ? 0.36 : 0,
          style: {
            animation: node.pulse && node.status === 'critical'
              ? 'networkTopologyCriticalPulse 1.4s infinite ease-out'
              : undefined,
            transformBox: 'fill-box',
            transformOrigin: 'center',
            pointerEvents: 'none',
          },
        },
        iconColumn: {
          fill: selected ? '#eef7ff' : '#f7fbff',
          ...toOpacityAttrs(dimmed),
        },
        divider: {
          stroke: selected ? '#c7def8' : '#e1ebf6',
          ...toOpacityAttrs(dimmed),
        },
        iconPlate: toOpacityAttrs(dimmed),
        img: {
          'xlink:href': node.icon && (/^https?:\/\//.test(node.icon) || node.icon.startsWith('/'))
            ? node.icon
            : getIconUrl({ icn: node.icon || '', model_id: node.modelId }),
          ...toOpacityAttrs(dimmed),
        },
        statusDot: {
          fill: statusColor,
          display: showStatusDot ? 'block' : 'none',
          ...toOpacityAttrs(dimmed),
        },
        alertBadge: {
          fill: statusColor,
          opacity: badgeOpacity,
        },
        alertBadgeText: {
          text: alertCount > 99 ? '99+' : String(alertCount),
          fill: '#fff',
          opacity: badgeOpacity,
        },
        tt: { text: node.name },
        lbl: {
          text: node.name,
          title: node.name,
          ...toOpacityAttrs(dimmed),
        },
        subLbl: {
          text: node.subtitle || node.modelId,
          title: node.subtitle || node.modelId,
          ...toOpacityAttrs(dimmed),
        },
      },
    };
  });

  const pairCount: Record<string, number> = {};
  const pairIndex: Record<string, number> = {};
  links.forEach((link) => {
    const key = [link.source, link.target].sort().join('__');
    pairCount[key] = (pairCount[key] || 0) + 1;
  });

  const graphEdges = links.map((link: NetworkTopologyPositionedLink & NetworkTopologyLink) => {
    const key = [link.source, link.target].sort().join('__');
    const total = pairCount[key] || 1;
    const idx = pairIndex[key] || 0;
    pairIndex[key] = idx + 1;
    const active = activeLinkIds.has(link.id);
    const dimmed = dimInactive && !active;

    let vertices: Array<{ x: number; y: number }> | undefined;
    if (total > 1) {
      const source = nodeMap.get(link.source);
      const target = nodeMap.get(link.target);
      if (source && target) {
        const midX = (source.x + target.x) / 2;
        const midY = (source.y + target.y) / 2;
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const len = Math.hypot(dx, dy) || 1;
        const offset = (idx - (total - 1) / 2) * 48;
        if (offset !== 0) {
          vertices = [{ x: midX + (-dy / len) * offset, y: midY + (dx / len) * offset }];
        }
      }
    }

    const sourceName = nodeMap.get(link.source)?.name;
    const targetName = nodeMap.get(link.target)?.name;

    return {
      id: link.id,
      source: link.source,
      target: link.target,
      vertices,
      connector: { name: 'smooth' },
      attrs: {
        line: {
          stroke: active ? '#ff4d4f' : NETWORK_TOPO_VISUAL.edge.stroke,
          strokeWidth: active ? 3 : NETWORK_TOPO_VISUAL.edge.strokeWidth,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          targetMarker: null,
          opacity: dimmed ? 0.22 : 1,
          filter: 'drop-shadow(0 1px 2px rgba(28, 55, 92, 0.16))',
        },
      },
      labels: [
        portLabel(
          NETWORK_TOPO_VISUAL.portLabelPosition.source,
          stripDevicePrefix(link.sourcePort, sourceName)
        ),
        portLabel(
          NETWORK_TOPO_VISUAL.portLabelPosition.target,
          stripDevicePrefix(link.targetPort, targetName)
        ),
      ],
    };
  });

  return {
    nodes: graphNodes,
    edges: graphEdges,
  };
};
