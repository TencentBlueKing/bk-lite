import { Graph } from '@antv/x6';
import { getIconUrl } from '@/app/cmdb/utils/common';
import type { NetworkTopologyLink, NetworkTopologyNode } from '@/app/cmdb/components/networkTopology';
import {
  buildParallelConnectorPath,
  STATUS_TOPOLOGY_PARALLEL_CONNECTOR,
} from './parallelEdges';
import { resolveLinkEdgeGeometry, layoutPointToCellPosition } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';

export type StatusTopologyPositionedNode = NetworkTopologyNode & {
  x: number;
  y: number;
};

export type StatusTopologyPositionedLink = NetworkTopologyLink & {
  x?: number;
  y?: number;
  /** 垂直于连线的平行偏移（像素）；0 表示不偏移 */
  parallelOffset?: number;
  curveOffset?: number;
  /** 用户手工折点；存在时优先于 parallel connector */
  vertices?: Array<{ x: number; y: number }>;
};

/**
 * 版本化 shape 名：避免热更新后仍命中旧 registerNode 缓存。
 * 对齐 CMDB 可用的卡片节点写法：register 时声明 width/height，
 * body 不写宽高（由节点尺寸驱动），子元素用绝对坐标。
 */
export const STATUS_TOPOLOGY_NODE_SHAPE = 'topo-network-status-device-v6';

export interface StatusTopologyPalette {
  nameFill: string;
  typeFill: string;
  edgeStroke: string;
  selectedStroke: string;
  portLabelFill: string;
}

export const STATUS_TOPOLOGY_VISUAL = {
  nodeWidth: 160,
  nodeHeight: 120,
  iconSize: 72,
  iconTop: 4,
  // 名称紧贴 icon：icon 底=76，名称中线=76+4+8=88
  labelNameY: 88,
  labelTypeY: 106,
  nameFontSize: 15,
  typeFontSize: 13,
  badgeRadius: 10,
  badgeFontSize: 11,
  edgeStrokeWidth: 1.35,
  // 更靠近节点两端
  portLabelPosition: {
    source: 0.14,
    target: 0.86,
  },
  portLabelFontSize: 11,
  status: {
    normal: '#39c78f',
    warning: '#f5b544',
    error: '#ff4d4f',
    critical: '#ff4d4f',
  },
} as const;

export const STATUS_TOPOLOGY_PALETTE_LIGHT: StatusTopologyPalette = {
  nameFill: '#1f2a37',
  typeFill: '#6b7c90',
  edgeStroke: '#9fb8d5',
  selectedStroke: '#0070fa',
  portLabelFill: '#60758d',
};

export const STATUS_TOPOLOGY_PALETTE_DARK: StatusTopologyPalette = {
  nameFill: '#eef4fc',
  typeFill: 'rgba(211, 225, 241, 0.82)',
  edgeStroke: 'rgba(168, 196, 228, 0.78)',
  selectedStroke: '#73A7FF',
  portLabelFill: 'rgba(211, 225, 241, 0.92)',
};

const STATUS_COLOR_MAP: Record<string, string> = {
  normal: STATUS_TOPOLOGY_VISUAL.status.normal,
  warning: STATUS_TOPOLOGY_VISUAL.status.warning,
  error: STATUS_TOPOLOGY_VISUAL.status.error,
  critical: STATUS_TOPOLOGY_VISUAL.status.critical,
};

const OPACITY_ATTR_DIMMED = Object.freeze({ opacity: 0.22 });
const OPACITY_ATTR_NORMAL = Object.freeze({ opacity: 1 });
const toOpacityAttrs = (dimmed: boolean) => (dimmed ? OPACITY_ATTR_DIMMED : OPACITY_ATTR_NORMAL);

/** SVG 属性：比 style.pointerEvents 更稳，避免穿透到 inherit:rect 的全尺寸 body */
const PE_NONE = Object.freeze({ 'pointer-events': 'none' as const });
const PE_ALL = Object.freeze({ 'pointer-events': 'visiblePainted' as const });

/**
 * 节点浮层只应在 icon（SVG image）上触发；名称/类型文字目标一律忽略。
 * X6 对 `.x6-cell` 委托 mouseenter 时，event.target 可能是容器，需看 composedPath。
 */
export const isStatusTopologyIconHoverTarget = (event: MouseEvent) => {
  const isImageEl = (node: EventTarget | null) => {
    if (!node || typeof (node as Element).tagName !== 'string') return false;
    return (node as Element).tagName.toLowerCase() === 'image';
  };
  if (isImageEl(event.target)) return true;
  const path =
    typeof event.composedPath === 'function' ? event.composedPath() : [];
  return path.some((node) => isImageEl(node));
};

const NODE_WIDTH = STATUS_TOPOLOGY_VISUAL.nodeWidth;
const NODE_HEIGHT = STATUS_TOPOLOGY_VISUAL.nodeHeight;
const ICON_SIZE = STATUS_TOPOLOGY_VISUAL.iconSize;
const ICON_TOP = STATUS_TOPOLOGY_VISUAL.iconTop;
const ICON_CENTER_Y = ICON_TOP + ICON_SIZE / 2;
const ICON_X = (NODE_WIDTH - ICON_SIZE) / 2;
// 叠在 icon 右上角内侧（中心略进入图标）
const BADGE_CX = ICON_X + ICON_SIZE - 8;
const BADGE_CY = ICON_TOP + 8;

const truncateLabel = (value: string, maxChars: number) => {
  const text = String(value || '');
  if (text.length <= maxChars) return text;
  return `${text.slice(0, Math.max(1, maxChars - 1))}…`;
};

/** 纯文字端口标签，无底框；贴边跟随连线比例位置 */
const buildPortLabel = (
  position: number,
  text: string,
  palette: StatusTopologyPalette,
  dimmed: boolean,
) => ({
  position,
  markup: [{ tagName: 'text', selector: 'txt' }],
  attrs: {
    txt: {
      text,
      fill: palette.portLabelFill,
      fontSize: STATUS_TOPOLOGY_VISUAL.portLabelFontSize,
      fontWeight: 600,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
      pointerEvents: 'none',
      opacity: dimmed ? 0.22 : 1,
    },
  },
});

export const ensureStatusTopologyParallelConnectorRegistered = () => {
  // force=true：热更新后覆盖旧实现
  Graph.registerConnector(
    STATUS_TOPOLOGY_PARALLEL_CONNECTOR,
    (sourcePoint, targetPoint, _vertices, args) => {
      const offset = Number((args as { offset?: number } | undefined)?.offset || 0);
      return buildParallelConnectorPath(sourcePoint, targetPoint, offset);
    },
    true,
  );
};

export const ensureStatusTopologyNodeRegistered = () => {
  ensureStatusTopologyParallelConnectorRegistered();
  // 即使已注册也强制覆盖，保证视觉常量变更后立即生效
  Graph.registerNode(
    STATUS_TOPOLOGY_NODE_SHAPE,
    {
      inherit: 'rect',
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      markup: [
        { tagName: 'circle', selector: 'pulseHalo' },
        { tagName: 'rect', selector: 'body' },
        // 连线专用轮廓：高度覆盖 icon+两行字，宽度仅按 icon，避免横向出线过远
        { tagName: 'rect', selector: 'edgeHull' },
        { tagName: 'circle', selector: 'iconRing' },
        { tagName: 'image', selector: 'img' },
        { tagName: 'circle', selector: 'alertBadge' },
        { tagName: 'text', selector: 'alertBadgeText' },
        { tagName: 'text', selector: 'lbl' },
        { tagName: 'text', selector: 'subLbl' },
      ],
      attrs: {
        // inherit:'rect' 会给 body 强制 refWidth/Height=100%，铺满整节点（含文字区）。
        // 文字 pointer-events:none 会穿透到 body，因此 body 必须禁用命中；热区只留给 img。
        body: {
          fill: 'none',
          stroke: 'none',
          strokeWidth: 0,
          ...PE_NONE,
        },
        edgeHull: {
          x: ICON_X,
          y: 0,
          width: ICON_SIZE,
          height: NODE_HEIGHT,
          fill: 'none',
          stroke: 'none',
          strokeWidth: 0,
          ...PE_NONE,
        },
        pulseHalo: {
          cx: NODE_WIDTH / 2,
          cy: ICON_CENTER_Y,
          r: ICON_SIZE / 2 + 10,
          fill: 'none',
          stroke: '#ff4d4f',
          strokeWidth: 2,
          opacity: 0,
          ...PE_NONE,
        },
        iconRing: {
          cx: NODE_WIDTH / 2,
          cy: ICON_CENTER_Y,
          r: ICON_SIZE / 2 + 4,
          fill: 'none',
          stroke: 'transparent',
          strokeWidth: 2,
          ...PE_NONE,
        },
        img: {
          x: ICON_X,
          y: ICON_TOP,
          width: ICON_SIZE,
          height: ICON_SIZE,
          opacity: 0.98,
          cursor: 'pointer',
          ...PE_ALL,
        },
        alertBadge: {
          cx: BADGE_CX,
          cy: BADGE_CY,
          r: STATUS_TOPOLOGY_VISUAL.badgeRadius,
          fill: '#ff4d4f',
          stroke: '#fff',
          strokeWidth: 2,
          opacity: 0,
          ...PE_NONE,
        },
        // 与 CMDB 可用实现一致：用 refX/refY + text，不要用 textWrap
        alertBadgeText: {
          refX: BADGE_CX,
          refY: BADGE_CY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: STATUS_TOPOLOGY_VISUAL.badgeFontSize,
          fontWeight: 800,
          fill: '#fff',
          opacity: 0,
          ...PE_NONE,
        },
        lbl: {
          refX: 0.5,
          refY: STATUS_TOPOLOGY_VISUAL.labelNameY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: STATUS_TOPOLOGY_VISUAL.nameFontSize,
          fontWeight: 600,
          fill: STATUS_TOPOLOGY_PALETTE_LIGHT.nameFill,
          ...PE_NONE,
        },
        subLbl: {
          refX: 0.5,
          refY: STATUS_TOPOLOGY_VISUAL.labelTypeY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: STATUS_TOPOLOGY_VISUAL.typeFontSize,
          fontWeight: 400,
          fill: STATUS_TOPOLOGY_PALETTE_LIGHT.typeFill,
          ...PE_NONE,
        },
      },
      ports: {
        groups: {
          icon: {
            position: {
              name: 'absolute',
              // 默认锚点仍贴近 icon，避免连线离节点过远
              args: { x: NODE_WIDTH / 2, y: ICON_CENTER_Y },
            },
            attrs: {
              circle: {
                r: 0,
                magnet: true,
                stroke: 'transparent',
                fill: 'transparent',
                style: { visibility: 'hidden' },
              },
            },
          },
        },
        items: [{ id: 'anchor', group: 'icon' }],
      },
    },
    true,
  );
};

export interface BuildStatusTopologyX6GraphDataOptions {
  nodes: StatusTopologyPositionedNode[];
  links: StatusTopologyPositionedLink[];
  centerId?: string;
  selectedNodeId?: string;
  activeNodeIds?: Set<string>;
  activeLinkIds?: Set<string>;
  dimInactive?: boolean;
  showStatusDot?: boolean;
  palette?: StatusTopologyPalette;
}

export const buildStatusTopologyX6GraphData = ({
  nodes,
  links,
  centerId,
  selectedNodeId,
  activeNodeIds = new Set(),
  activeLinkIds = new Set(),
  dimInactive = false,
  palette = STATUS_TOPOLOGY_PALETTE_LIGHT,
}: BuildStatusTopologyX6GraphDataOptions) => {
  ensureStatusTopologyNodeRegistered();

  const graphNodes = nodes.map((node) => {
    const selected = selectedNodeId === node.id || centerId === node.id;
    const active = activeNodeIds.has(node.id);
    const dimmed = dimInactive && !active;
    const alertCount = Number(node.alertCount || 0);
    const statusColor = STATUS_COLOR_MAP[node.status || 'normal'] || STATUS_COLOR_MAP.normal;
    const badgeOpacity = alertCount ? (dimmed ? 0.22 : 1) : 0;
    const badgeText = alertCount > 99 ? '99+' : alertCount > 0 ? String(alertCount) : '';
    const nameText = truncateLabel(String(node.name || node.id || ''), 18);
    const typeText = truncateLabel(String(node.subtitle || node.modelId || ''), 18);

    return {
      id: node.id,
      x: layoutPointToCellPosition(node).x,
      y: layoutPointToCellPosition(node).y,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      shape: STATUS_TOPOLOGY_NODE_SHAPE,
      zIndex: 10,
      data: { node },
      attrs: {
        body: {
          fill: 'none',
          stroke: 'none',
          ...PE_NONE,
          ...toOpacityAttrs(dimmed),
        },
        iconRing: {
          stroke: active ? '#ff4d4f' : selected ? palette.selectedStroke : 'transparent',
          strokeWidth: active || selected ? 2.2 : 0,
          ...PE_NONE,
          ...toOpacityAttrs(dimmed),
        },
        pulseHalo: {
          stroke: statusColor,
          opacity: node.pulse && node.status === 'critical' ? 0.36 : 0,
          style: {
            animation:
              node.pulse && node.status === 'critical'
                ? 'networkTopologyCriticalPulse 1.4s infinite ease-out'
                : undefined,
            transformBox: 'fill-box',
            transformOrigin: 'center',
          },
          ...PE_NONE,
        },
        img: {
          width: ICON_SIZE,
          height: ICON_SIZE,
          x: ICON_X,
          y: ICON_TOP,
          cursor: 'pointer',
          ...PE_ALL,
          'xlink:href':
            node.icon && (/^https?:\/\//.test(node.icon) || node.icon.startsWith('/'))
              ? node.icon
              : getIconUrl({ icn: node.icon || '', model_id: node.modelId }),
          ...toOpacityAttrs(dimmed),
        },
        alertBadge: {
          cx: BADGE_CX,
          cy: BADGE_CY,
          r: STATUS_TOPOLOGY_VISUAL.badgeRadius,
          fill: statusColor,
          stroke: '#ffffff',
          strokeWidth: 2,
          opacity: badgeOpacity,
          ...PE_NONE,
        },
        alertBadgeText: {
          refX: BADGE_CX,
          refY: BADGE_CY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          text: badgeText,
          fill: '#ffffff',
          fontSize: badgeText === '99+' ? 9 : STATUS_TOPOLOGY_VISUAL.badgeFontSize,
          fontWeight: 800,
          opacity: badgeOpacity,
          ...PE_NONE,
        },
        lbl: {
          refX: 0.5,
          refY: STATUS_TOPOLOGY_VISUAL.labelNameY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: STATUS_TOPOLOGY_VISUAL.nameFontSize,
          fontWeight: 600,
          text: nameText,
          title: String(node.name || node.id || ''),
          fill: palette.nameFill,
          ...PE_NONE,
          ...toOpacityAttrs(dimmed),
        },
        subLbl: {
          refX: 0.5,
          refY: STATUS_TOPOLOGY_VISUAL.labelTypeY,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
          fontSize: STATUS_TOPOLOGY_VISUAL.typeFontSize,
          fontWeight: 400,
          text: typeText,
          title: String(node.subtitle || node.modelId || ''),
          fill: palette.typeFill,
          ...PE_NONE,
          ...toOpacityAttrs(dimmed),
        },
      },
    };
  });

  const graphEdges = links.map((link) => {
    const active = activeLinkIds.has(link.id);
    const dimmed = dimInactive && !active;
    const edgeGeometry = resolveLinkEdgeGeometry({
      parallelOffset: Number(link.parallelOffset ?? link.curveOffset ?? 0),
      manualVertices: link.vertices,
    });
    const sourcePort = truncateLabel(String(link.sourcePort || ''), 14);
    const targetPort = truncateLabel(String(link.targetPort || ''), 14);
    const labels = [
      sourcePort
        ? buildPortLabel(
          STATUS_TOPOLOGY_VISUAL.portLabelPosition.source,
          sourcePort,
          palette,
          dimmed,
        )
        : null,
      targetPort
        ? buildPortLabel(
          STATUS_TOPOLOGY_VISUAL.portLabelPosition.target,
          targetPort,
          palette,
          dimmed,
        )
        : null,
    ].filter(Boolean);

    return {
      id: link.id,
      source: {
        cell: link.source,
        selector: 'edgeHull',
        anchor: { name: 'nodeCenter' },
        connectionPoint: { name: 'boundary', args: { selector: 'edgeHull' } },
      },
      target: {
        cell: link.target,
        selector: 'edgeHull',
        anchor: { name: 'nodeCenter' },
        connectionPoint: { name: 'boundary', args: { selector: 'edgeHull' } },
      },
      ...(edgeGeometry.kind === 'manual'
        ? {
          connector: { name: 'normal' },
          vertices: edgeGeometry.vertices,
        }
        : {
          // 用 connector 按当前端点实时算平行路径，避免绝对 vertices 拖动时卡住
          connector: {
            name: STATUS_TOPOLOGY_PARALLEL_CONNECTOR,
            args: { offset: edgeGeometry.parallelOffset },
          },
          vertices: [],
        }),
      labels,
      zIndex: 1,
      data: { link },
      attrs: {
        line: {
          stroke: active ? '#ff4d4f' : palette.edgeStroke,
          strokeWidth: active ? 3 : STATUS_TOPOLOGY_VISUAL.edgeStrokeWidth,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          targetMarker: null,
          sourceMarker: null,
          opacity: dimmed ? 0.22 : 1,
        },
      },
    };
  });

  return {
    nodes: graphNodes,
    edges: graphEdges,
  };
};

// 模块加载时即注册，避免 XFlow initData 早于首次 build 时拿不到自定义 shape
if (typeof window !== 'undefined') {
  try {
    ensureStatusTopologyNodeRegistered();
  } catch {
    // Graph 在非浏览器环境可能不可用
  }
}
