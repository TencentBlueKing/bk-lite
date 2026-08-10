import React, { useCallback, useEffect, useRef } from "react";
import { Alert, Spin } from "antd";
import { ExclamationCircleFilled } from "@ant-design/icons";
import type {
  Graph as X6Graph,
  Cell as X6Cell,
  Node as X6Node,
  Edge as X6Edge,
} from "@antv/x6";
import { Graph } from "@antv/x6";
import { Selection } from "@antv/x6-plugin-selection";
import type {
  NetworkNodeLibraryItem,
  NetworkTopologyLink,
  NetworkTopologyNode,
  NetworkNodeRuntime,
  NetworkLinkRuntime,
  NetworkMetricRuntime,
} from "@/app/ops-analysis/types/networkTopology";
import { useTranslation } from "@/utils/i18n";
import {
  buildNetworkTopologyLinkTerminals,
  buildNetworkTopologyLinkRenderOptions,
  findNetworkTopologyMetricRuntime,
  isNetworkTopologyLinkPendingInterfaceSelection,
  isMetricRuntimeLoading,
  nextSequentialId,
} from "../utils/networkTopologyUtils";
import {
  NODE_UNFALLBACK_COLOR,
  resolveNodeOuterColor,
} from "../utils/nodeStatus";
import { formatNetworkMetricValue } from "../utils/metricValueFormat";

/** 画布侧使用的连线运行态 —— 复用后端 ``NetworkLinkRuntime``，便于跟 index.tsx 对齐。 */
export type NetworkLinkRuntimeSummary = NetworkLinkRuntime;

export interface NetworkCanvasProps {
  nodes: ReadonlyArray<NetworkTopologyNode>;
  links: ReadonlyArray<NetworkTopologyLink>;
  /** 首次加载/刷新运行态时显示 Spin 蒙层,沿用 topology/components/canvasShell 的写法。 */
  loading?: boolean;
  /**
   * WeOps Token 失效等致命错误,会在画布顶部展示一条醒目的横幅。
   * 不阻塞画布渲染 —— 用户仍可编辑节点、连线,只是运行态颜色不会刷新。
   */
  fatalMessage?: string | null;
  /** 是否处于 stale(整画布运行态拉取失败但有上次缓存)。 */
  stale?: boolean;
  /** 节点运行态(逐节点查询后合并)。 */
  runtimeNodes?: ReadonlyArray<NetworkNodeRuntime>;
  /** 连线运行态(简化结构即可)。 */
  runtimeLinks?: ReadonlyArray<NetworkLinkRuntimeSummary>;
  /** 是否处于编辑模式(用于 enable/disable magnet / node move)。 */
  editMode?: boolean;
  /** 接收 graph 实例回调(父级可用于 fit / 序列化等)。 */
  onGraphReady?: (graph: X6Graph) => void;
  onSelectNode: (
    id: string | null,
    options?: { point?: { x: number; y: number } },
  ) => void;
  onSelectLink: (
    id: string | null,
    options?: { point?: { x: number; y: number } },
  ) => void;
  onNodeMoved: (id: string, position: { x: number; y: number }) => void;
  onLinkVerticesChanged?: (
    id: string,
    vertices: Array<{ x: number; y: number }>,
  ) => void;
  onLinkTerminalsChanged?: (
    id: string,
    terminals: {
      source_node_id: string;
      target_node_id: string;
      source_port_id?: string;
      target_port_id?: string;
    },
  ) => void;
  onNodeContextMenu?: (id: string, point: { x: number; y: number }) => void;
  onLinkContextMenu?: (id: string, point: { x: number; y: number }) => void;
  /** 拖拽设备到画布:父级决定创建/重复提示。 */
  onDropDevice: (
    item: NetworkNodeLibraryItem,
    position: { x: number; y: number },
  ) => void;
  /** X6 magnet 连接成功后,父级根据 source/target node 决定行为(创建连线 + 打开 Drawer)。 */
  onConnectPorts?: (
    sourceNodeId: string,
    targetNodeId: string,
    sourcePortId?: string,
    targetPortId?: string,
  ) => { linkId: string } | { cancel: true } | undefined;
  testId?: string;
}

/** 与 useTranslation().t 兼容的最小签名。 */
type CanvasT = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

/** 模块级 buildNodeAttrs 调用(只用于 X6 原型注册,值会被运行时 setAttrs 覆盖),使用 no-op t。 */
const noopT: CanvasT = (id) => id;

const compactText = (value: unknown, max = 18): string => {
  const text = String(value ?? "");
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1))}…`;
};

const formatMetricValue = (
  node: NetworkTopologyNode,
  metric: NetworkTopologyNode["metrics"][number],
  runtime: NetworkNodeRuntime | undefined,
): string => {
  const runtimeMetric = findNetworkTopologyMetricRuntime(node, metric, runtime);
  if (runtimeMetric?.status === "loading") return "";
  if (!runtimeMetric || runtimeMetric.status === "error") return "--";
  if (runtimeMetric.value === null || runtimeMetric.value === undefined) return "--";
  return formatNetworkMetricValue(runtimeMetric.value, runtimeMetric.unit, {
    fallbackUnit: metric.unit,
  });
};

const NETWORK_NODE_WIDTH = 220;
const NETWORK_NODE_BASE_HEIGHT = 96;
const NETWORK_NODE_METRIC_ROW_HEIGHT = 18;
const NETWORK_NODE_METRIC_TOP = 98;
const NETWORK_NODE_METRIC_BOTTOM_PADDING = 12;
const NETWORK_NODE_MAX_METRIC_ROWS = 6;
const NETWORK_NODE_SHAPE_VERSION = 9;
const NETWORK_NODE_SHAPE_NAME = "network-node-card-v8";

const edgeVertexTool = {
  name: "vertices",
  args: {
    attrs: {
      fill: "#2d7df0",
      stroke: "#ffffff",
      strokeWidth: 1,
      r: 5,
      cursor: "move",
    },
    snapRadius: 20,
    addable: true,
    removable: true,
    removeRedundancies: true,
  },
};

const invisibleEndpointToolAttrs = {
  d: "M -6 -6 H 6 V 6 H -6 Z",
  fill: "#2d7df0",
  opacity: 0,
  stroke: "none",
  cursor: "move",
  "pointer-events": "all",
};

const edgeSourceEndpointTool = {
  name: "source-arrowhead",
  args: {
    attrs: invisibleEndpointToolAttrs,
  },
};

const edgeTargetEndpointTool = {
  name: "target-arrowhead",
  args: {
    attrs: invisibleEndpointToolAttrs,
  },
};

const NETWORK_NODE_PORT_IDS = [
  "port-top",
  "port-right",
  "port-bottom",
  "port-left",
] as const;

const syncNodePorts = (node: X6Node, editMode: boolean) => {
  NETWORK_NODE_PORT_IDS.forEach((portId) => {
    node.portProp(portId, "attrs/circle/opacity", editMode ? 1 : 0);
    node.portProp(portId, "attrs/circle/magnet", editMode);
  });
};

const normalizeVertices = (
  vertices: ReadonlyArray<{ x: number; y: number }> | undefined,
) =>
  (vertices ?? [])
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
    .map((point) => ({ x: point.x, y: point.y }));

const isSameVertices = (
  a: ReadonlyArray<{ x: number; y: number }> | undefined,
  b: ReadonlyArray<{ x: number; y: number }> | undefined,
) => {
  const left = normalizeVertices(a);
  const right = normalizeVertices(b);
  if (left.length !== right.length) return false;
  return left.every(
    (point, index) =>
      Math.abs(point.x - right[index].x) < 0.5 &&
      Math.abs(point.y - right[index].y) < 0.5,
  );
};

const syncEdgeTools = (edge: X6Edge, editMode: boolean) => {
  edge.removeTools();
  if (editMode) {
    edge.addTools([edgeSourceEndpointTool, edgeTargetEndpointTool, edgeVertexTool]);
  }
};

const getVisibleMetricRows = (node: NetworkTopologyNode) =>
  Math.min(node.metrics.length, NETWORK_NODE_MAX_METRIC_ROWS);

const getNetworkNodeHeight = (node: NetworkTopologyNode) => {
  const metricRows = getVisibleMetricRows(node);
  if (metricRows === 0) return NETWORK_NODE_BASE_HEIGHT;
  return (
    NETWORK_NODE_METRIC_TOP +
    metricRows * NETWORK_NODE_METRIC_ROW_HEIGHT +
    NETWORK_NODE_METRIC_BOTTOM_PADDING
  );
};

const buildNodeAttrs = (
  node: NetworkTopologyNode,
  runtime: NetworkNodeRuntime | undefined,
  t: CanvasT,
  editMode = false,
) => {
  const nodeHeight = getNetworkNodeHeight(node);
  const runtimeMetrics = runtime?.metrics ?? [];
  const metricRows = node.metrics
    .slice(0, NETWORK_NODE_MAX_METRIC_ROWS)
    .map((metric) => ({
      label: compactText(metric.display_name || metric.metric_field, 15),
      value: compactText(formatMetricValue(node, metric, runtime), 10),
      loading: isMetricRuntimeLoading(node, metric, runtime),
    }));
  const outerColor =
    resolveNodeOuterColor(node.metrics, runtimeMetrics) ??
    NODE_UNFALLBACK_COLOR;
  const metaText = [node.ip_addr, node.plugin_template_name || node.bk_obj_id]
    .filter(Boolean)
    .join(" · ");
  const metricAttrs = Array.from({
    length: NETWORK_NODE_MAX_METRIC_ROWS,
  }).reduce<Record<string, Record<string, unknown>>>((attrs, _, index) => {
    const row = metricRows[index];
    const y =
      (NETWORK_NODE_METRIC_TOP + index * NETWORK_NODE_METRIC_ROW_HEIGHT) /
      nodeHeight;
    attrs[`metric${index}Label`] = {
      display: row ? "block" : "none",
      text: row?.label ?? "",
      fill: "#64748b",
      fontSize: 11,
      textAnchor: "start",
      textVerticalAnchor: "middle",
      refX: 12,
      refY: y,
      textWrap: {
        width: 126,
        height: 16,
        ellipsis: true,
      },
    };
    attrs[`metric${index}Value`] = {
      display: row && !row.loading ? "block" : "none",
      text: row?.value ?? "",
      fill: "#192733",
      fontSize: 11,
      fontWeight: 650,
      textAnchor: "end",
      textVerticalAnchor: "middle",
      refX: NETWORK_NODE_WIDTH - 12,
      refY: y,
      textWrap: {
        width: 66,
        height: 16,
        ellipsis: true,
      },
    };
    attrs[`metric${index}Loading`] = {
      display: row?.loading ? "block" : "none",
      cx: NETWORK_NODE_WIDTH - 18,
      cy: y * nodeHeight,
      r: 3.5,
      fill: "none",
      stroke: "#2563eb",
      strokeWidth: 1.3,
      strokeDasharray: "7 5",
      opacity: 0.9,
    };
    return attrs;
  }, {});

  return {
    body: {
      x: 0,
      y: 0,
      width: NETWORK_NODE_WIDTH,
      height: nodeHeight,
      stroke: "#d6e1e8",
      strokeWidth: 1,
      fill: "#ffffff",
      rx: 8,
      ry: 8,
      filter: {
        name: "dropShadow",
        args: { dx: 0, dy: 2, blur: 4, color: "rgba(36,50,63,0.08)" },
      },
    },
    topLine: {
      stroke: outerColor,
      strokeWidth: 2,
      x1: 0,
      y1: 1,
      x2: NETWORK_NODE_WIDTH,
      y2: 1,
    },
    icon: {
      display: "none",
      fill: "#eef4f6",
      stroke: "#d6e1e8",
      strokeWidth: 1,
      rx: 6,
      ry: 6,
      x: 10,
      y: 10,
      width: 32,
      height: 32,
    },
    iconLabel: {
      display: "none",
      text: "",
      fill: "#335364",
      fontSize: 11,
      fontWeight: 700,
      textAnchor: "middle",
      textVerticalAnchor: "middle",
      refX: 26,
      refY: 26 / nodeHeight,
    },
    title: {
      text: compactText(node.bk_inst_name || node.bk_obj_id, 24),
      fill: "#1f2933",
      fontSize: 13,
      fontWeight: 650,
      textAnchor: "start",
      textVerticalAnchor: "middle",
      refX: 12,
      refY: 22 / nodeHeight,
      textWrap: {
        width: NETWORK_NODE_WIDTH - 44,
        height: 18,
        ellipsis: true,
      },
    },
    subtitle: {
      text: compactText(metaText || node.bk_obj_id, 24),
      fill: "#73808c",
      fontSize: 11,
      textAnchor: "start",
      textVerticalAnchor: "middle",
      refX: 12,
      refY: 40 / nodeHeight,
      textWrap: {
        width: NETWORK_NODE_WIDTH - 44,
        height: 16,
        ellipsis: true,
      },
    },
    statusDot: {
      fill: outerColor,
      stroke: "none",
      cx: 204,
      cy: 26,
      r: 5,
    },
    divider: {
      stroke: "#e4ebf0",
      strokeWidth: 1,
      strokeDasharray: "3 3",
      x1: 12,
      y1: 58,
      x2: NETWORK_NODE_WIDTH - 12,
      y2: 58,
    },
    summary: {
      text:
        metricRows.length > 0
          ? t("opsAnalysis.networkTopology.nodeShape.metricCount", undefined, {
            count: node.metrics.length,
          })
          : t(
            editMode
              ? "opsAnalysis.networkTopology.nodeShape.editHint"
              : "opsAnalysis.networkTopology.nodeShape.clickHint",
          ),
      fill: "#536270",
      fontSize: 11,
      textAnchor: "start",
      textVerticalAnchor: "middle",
      refX: 12,
      refY: 74 / nodeHeight,
      textWrap: {
        width: NETWORK_NODE_WIDTH - 24,
        height: 16,
        ellipsis: true,
      },
    },
    error: {
      display: "none",
      text: "",
      fill: "#536270",
      fontSize: 11,
      textAnchor: "end",
      refX: 190,
      refY: 68 / nodeHeight,
    },
    ...metricAttrs,
  };
};

/**
 * 给 network-node 注册 4 个端口(上/下/左/右)。端口是 X6 connecting 的
 * 「磁铁」:用户从源节点的某个端口磁铁拖到目标节点的端口磁铁即建连线。
 * 不加端口的话 connecting.magnet 会落到 cell body 上,行为不一致且视觉
 * 上看不出「这条线连到了哪个端口」。
 */
const networkNodePorts = [
  {
    id: NETWORK_NODE_PORT_IDS[0],
    group: "top",
    args: { x: NETWORK_NODE_WIDTH / 2, y: 0 },
  },
  {
    id: NETWORK_NODE_PORT_IDS[1],
    group: "right",
    args: { x: NETWORK_NODE_WIDTH, y: NETWORK_NODE_BASE_HEIGHT / 2 },
  },
  {
    id: NETWORK_NODE_PORT_IDS[2],
    group: "bottom",
    args: { x: NETWORK_NODE_WIDTH / 2, y: NETWORK_NODE_BASE_HEIGHT },
  },
  {
    id: NETWORK_NODE_PORT_IDS[3],
    group: "left",
    args: { x: 0, y: NETWORK_NODE_BASE_HEIGHT / 2 },
  },
] as const;

const registerNetworkNodeShapeOnce = () => {
  Graph.registerNode(
    NETWORK_NODE_SHAPE_NAME,
    {
      inherit: "rect",
      width: NETWORK_NODE_WIDTH,
      height: NETWORK_NODE_BASE_HEIGHT,
      markup: [
        { tagName: "rect", selector: "body" },
        { tagName: "line", selector: "topLine" },
        { tagName: "rect", selector: "icon" },
        { tagName: "text", selector: "iconLabel" },
        { tagName: "text", selector: "title" },
        { tagName: "text", selector: "subtitle" },
        { tagName: "circle", selector: "statusDot" },
        { tagName: "line", selector: "divider" },
        { tagName: "text", selector: "summary" },
        { tagName: "text", selector: "error" },
        ...Array.from({ length: NETWORK_NODE_MAX_METRIC_ROWS }).flatMap(
          (_, index) => [
            { tagName: "text", selector: `metric${index}Label` },
            { tagName: "circle", selector: `metric${index}Loading` },
            { tagName: "text", selector: `metric${index}Value` },
          ],
        ),
      ],
      ports: {
        groups: {
          top: {
            position: "top",
            attrs: {
              circle: {
                r: 4,
                magnet: true,
                stroke: "#2d7df0",
                strokeWidth: 1.5,
                fill: "#ffffff",
              },
            },
          },
          right: {
            position: "right",
            attrs: {
              circle: {
                r: 4,
                magnet: true,
                stroke: "#2d7df0",
                strokeWidth: 1.5,
                fill: "#ffffff",
              },
            },
          },
          bottom: {
            position: "bottom",
            attrs: {
              circle: {
                r: 4,
                magnet: true,
                stroke: "#2d7df0",
                strokeWidth: 1.5,
                fill: "#ffffff",
              },
            },
          },
          left: {
            position: "left",
            attrs: {
              circle: {
                r: 4,
                magnet: true,
                stroke: "#2d7df0",
                strokeWidth: 1.5,
                fill: "#ffffff",
              },
            },
          },
        },
        items: networkNodePorts.map((p) => ({ id: p.id, group: p.group })),
      },
      attrs: buildNodeAttrs(
        {
          id: "",
          bk_obj_id: "bk_network",
          bk_inst_id: 0,
          bk_inst_name: "",
          network_collect_task_id: 0,
          network_collect_instance_id: 0,
          plugin_template_id: "",
          position: { x: 0, y: 0 },
          metrics: [],
        },
        undefined,
        noopT,
        false,
      ),
    },
    true,
  );
};

const strokeFromStatus = (status?: "normal" | "critical" | "unknown") => {
  if (status === "critical") return "#dc2626";
  if (status === "normal") return "#16a34a";
  return "#64748b";
};

// 流动虚线:dasharray 5+3=8,与 index.module.scss 里 networkEdgeFlow 的
// stroke-dashoffset 8→0 周期对齐,动画才能无缝循环;class 经 X6 特殊 attr
// 挂到 line path 上(参考 topology 模块 edge-flow-animation 的做法)。
const lineAttrsFromStatus = (
  status?: "normal" | "critical" | "unknown",
) => ({
  stroke: strokeFromStatus(status),
  strokeWidth: status === "critical" ? 2 : 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  strokeDasharray: "5 3",
  class: "network-edge-flow",
  targetMarker: {
    name: "block",
    size: 8,
  },
});

const pendingInterfaceSelectionLineAttrs = () => lineAttrsFromStatus("unknown");

const lineAttrsForLinkRuntime = (
  link: NetworkTopologyLink,
  runtimeItem?: NetworkLinkRuntimeSummary,
) =>
  isNetworkTopologyLinkPendingInterfaceSelection(link)
    ? pendingInterfaceSelectionLineAttrs()
    : lineAttrsFromStatus(runtimeItem?.status);

const terminalPortId = (terminal: unknown): string | undefined => {
  const port = (terminal as { port?: unknown } | null)?.port;
  return typeof port === "string" && port.length > 0 ? port : undefined;
};

const isSameTerminal = (
  actual: unknown,
  expected: { cell: string; port?: string },
): boolean => {
  const value = actual as { cell?: unknown; port?: unknown } | null;
  return value?.cell === expected.cell && value?.port === expected.port;
};

const NetworkCanvas: React.FC<NetworkCanvasProps> = ({
  nodes,
  links,
  runtimeNodes,
  runtimeLinks,
  editMode = false,
  loading = false,
  fatalMessage = null,
  stale = false,
  onGraphReady,
  onSelectNode,
  onSelectLink,
  onNodeMoved,
  onLinkVerticesChanged,
  onLinkTerminalsChanged,
  onNodeContextMenu,
  onLinkContextMenu,
  onDropDevice,
  onConnectPorts,
  testId,
}) => {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const graphHostRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<X6Graph | null>(null);
  const editModeRef = useRef(editMode);
  const onSelectNodeRef = useRef(onSelectNode);
  const onSelectLinkRef = useRef(onSelectLink);
  const onNodeMovedRef = useRef(onNodeMoved);
  const onLinkVerticesChangedRef = useRef(onLinkVerticesChanged);
  const onLinkTerminalsChangedRef = useRef(onLinkTerminalsChanged);
  const onNodeContextMenuRef = useRef(onNodeContextMenu);
  const onLinkContextMenuRef = useRef(onLinkContextMenu);
  const onConnectPortsRef = useRef(onConnectPorts);
  const suppressSelectionUntilRef = useRef(0);
  const pendingVerticesRef = useRef(
    new Map<string, Array<{ x: number; y: number }>>(),
  );

  const flushPendingVertices = useCallback(() => {
    const pending = Array.from(pendingVerticesRef.current.entries());
    if (!pending.length) return;
    pendingVerticesRef.current.clear();
    pending.forEach(([id, vertices]) => {
      onLinkVerticesChangedRef.current?.(id, vertices);
    });
  }, []);

  useEffect(() => {
    if (!editMode) {
      flushPendingVertices();
    }
    editModeRef.current = editMode;
    if (!editMode) {
      (
        graphRef.current as
          | (X6Graph & { cleanSelection?: () => void })
          | null
      )?.cleanSelection?.();
    }
    graphRef.current?.getEdges().forEach((edge) => {
      syncEdgeTools(edge as X6Edge, editMode);
    });
    graphRef.current?.getNodes().forEach((node) => {
      syncNodePorts(node as X6Node, editMode);
    });
  }, [editMode, flushPendingVertices]);

  useEffect(() => {
    onSelectNodeRef.current = onSelectNode;
    onSelectLinkRef.current = onSelectLink;
    onNodeMovedRef.current = onNodeMoved;
    onLinkVerticesChangedRef.current = onLinkVerticesChanged;
    onLinkTerminalsChangedRef.current = onLinkTerminalsChanged;
    onNodeContextMenuRef.current = onNodeContextMenu;
    onLinkContextMenuRef.current = onLinkContextMenu;
    onConnectPortsRef.current = onConnectPorts;
  }, [
    onConnectPorts,
    onLinkContextMenu,
    onLinkTerminalsChanged,
    onLinkVerticesChanged,
    onNodeContextMenu,
    onNodeMoved,
    onSelectLink,
    onSelectNode,
  ]);

  // 同步节点 & 连线到 graph
  const syncNodes = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const runtimeByKey = new Map<string, NetworkNodeRuntime>();
    // 后端 runtime 端点用 `id` 字段（也是 `bk_obj_id:bk_inst_id`）
    // 标识节点 —— 见 buildNetworkNodeClientId。
    (runtimeNodes ?? []).forEach((item) => runtimeByKey.set(item.id, item));
    const existing = new Set<string>();
    graph.getNodes().forEach((cell) => existing.add(cell.id));
    nodes.forEach((node) => {
      const key = `${node.bk_obj_id}:${node.bk_inst_id}`;
      const cell = graph.getCellById(node.id);
      const desired = node.position;
      const runtimeItem = runtimeByKey.get(key);
      const nodeHeight = getNetworkNodeHeight(node);
      if (cell && cell.isNode()) {
        const data = (cell as X6Cell).getData<{
          shapeVersion?: number;
        }>();
        const pos = (cell as X6Node).getPosition();
        const shouldRecreate =
          (cell as X6Cell).prop("shape") !== NETWORK_NODE_SHAPE_NAME ||
          data?.shapeVersion !== NETWORK_NODE_SHAPE_VERSION;
        if (shouldRecreate) {
          cell.remove();
          const nextNode = graph.addNode({
            id: node.id,
            shape: NETWORK_NODE_SHAPE_NAME,
            x: desired?.x ?? pos.x,
            y: desired?.y ?? pos.y,
            zIndex: 1,
            width: NETWORK_NODE_WIDTH,
            height: nodeHeight,
            attrs: buildNodeAttrs(node, runtimeItem, t, editModeRef.current),
            data: {
              node,
              shapeVersion: NETWORK_NODE_SHAPE_VERSION,
              runtime: runtimeItem
                ? { ...runtimeItem, metrics: runtimeItem.metrics }
                : undefined,
            },
          });
          syncNodePorts(nextNode as X6Node, editModeRef.current);
          existing.delete(node.id);
          return;
        }
        const currentSize = (cell as X6Node).size();
        if (
          Math.abs(currentSize.width - NETWORK_NODE_WIDTH) > 1 ||
          Math.abs(currentSize.height - nodeHeight) > 1
        ) {
          (cell as X6Node).resize(NETWORK_NODE_WIDTH, nodeHeight);
        }
        const metrics: NetworkMetricRuntime[] = runtimeItem?.metrics ?? [];
        (cell as X6Cell).setData(
          {
            node,
            shapeVersion: NETWORK_NODE_SHAPE_VERSION,
            runtime: { ...(runtimeItem ?? {}), metrics },
          },
          { overwrite: true },
        );
        (cell as X6Cell).setAttrs(
          buildNodeAttrs(node, runtimeItem, t, editModeRef.current),
          {
            overwrite: true,
          },
        );
        syncNodePorts(cell as X6Node, editModeRef.current);
        existing.delete(node.id);
        return;
      }
      const nextNode = graph.addNode({
        id: node.id,
        shape: NETWORK_NODE_SHAPE_NAME,
        x: desired?.x ?? 40,
        y: desired?.y ?? 40,
        zIndex: 1,
        width: NETWORK_NODE_WIDTH,
        height: nodeHeight,
        attrs: buildNodeAttrs(node, runtimeItem, t, editModeRef.current),
        data: {
          node,
          shapeVersion: NETWORK_NODE_SHAPE_VERSION,
          runtime: runtimeItem
            ? { ...runtimeItem, metrics: runtimeItem.metrics }
            : undefined,
        },
      });
      syncNodePorts(nextNode as X6Node, editModeRef.current);
    });
    existing.forEach((id) => {
      const cell = graph.getCellById(id);
      cell?.remove();
    });
  }, [nodes, runtimeNodes]);

  const syncLinks = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const runtimeById = new Map<string, NetworkLinkRuntimeSummary>();
    (runtimeLinks ?? []).forEach((item) => runtimeById.set(item.id, item));
    const existing = new Set<string>();
    graph.getEdges().forEach((edge) => existing.add(edge.id));
    links.forEach((link) => {
      const cell = graph.getCellById(link.id);
      const runtimeItem = runtimeById.get(link.id);
      if (cell && cell.isEdge()) {
        const edge = cell as X6Edge;
        const terminals = buildNetworkTopologyLinkTerminals(link);
        const renderOptions = buildNetworkTopologyLinkRenderOptions(link);
        const data = (cell as X6Cell).getData<{
          link: NetworkTopologyLink;
        }>();
        (cell as X6Cell).setData(
          { ...(data ?? {}), link, runtime: runtimeItem },
          { overwrite: false },
        );
        (cell as X6Cell).setAttrs({ line: lineAttrsForLinkRuntime(link, runtimeItem) });
        edge.setConnector(renderOptions.connector);
        edge.removeRouter();
        const nextVertices = renderOptions.vertices;
        const isEditingVertices = pendingVerticesRef.current.has(link.id);
        if (
          !isEditingVertices &&
          !isSameVertices(edge.getVertices(), nextVertices)
        ) {
          edge.setVertices(nextVertices);
        }
        if (!isSameTerminal(edge.getSource(), terminals.source)) {
          edge.setSource(terminals.source);
        }
        if (!isSameTerminal(edge.getTarget(), terminals.target)) {
          edge.setTarget(terminals.target);
        }
        if (!isEditingVertices) {
          syncEdgeTools(edge, editModeRef.current);
        }
        existing.delete(link.id);
        return;
      }
      const terminals = buildNetworkTopologyLinkTerminals(link);
      const renderOptions = buildNetworkTopologyLinkRenderOptions(link);
      graph.addEdge({
        id: link.id,
        source: terminals.source,
        target: terminals.target,
        vertices: renderOptions.vertices,
        connector: renderOptions.connector,
        zIndex: 0,
        attrs: {
          line: lineAttrsForLinkRuntime(link, runtimeItem),
        },
        data: { link, runtime: runtimeItem },
      });
      const edge = graph.getCellById(link.id);
      if (edge?.isEdge()) {
        syncEdgeTools(edge as X6Edge, editModeRef.current);
      }
    });
    existing.forEach((id) => {
      const cell = graph.getCellById(id);
      cell?.remove();
    });
  }, [links, runtimeLinks]);

  // 创建 / 销毁 X6 graph。
  // 注意：X6 会接管并清理 container 子节点，graphHost 必须和 React 管理的
  // overlay 分离，否则 HMR / StrictMode 卸载时会触发 removeChild NotFoundError。
  useEffect(() => {
    const host = graphHostRef.current;
    if (!host || graphRef.current) return undefined;
    registerNetworkNodeShapeOnce();
    const graph: X6Graph = new Graph({
      container: host,
      autoResize: true,
      background: {
        color: '#ffffff',
      },
      // 点阵网格(对齐 OpsPilot 画布 Dots gap=12),点色放淡。
      grid: {
        visible: true,
        type: 'dot',
        size: 12,
        args: { color: '#ccd6e0', thickness: 1.2 },
      },
      panning: true,
      mousewheel: {
        enabled: true,
        modifiers: ['ctrl', 'meta'],
      },
      connecting: {
        snap: { radius: 24 },
        allowBlank: false,
        allowLoop: false,
        allowMulti: 'withPort',
        connector: { name: 'normal' },
        connectionPoint: { name: 'boundary' },
        createEdge: () =>
          graph.createEdge({
            connector: { name: 'normal' },
            attrs: {
              line: {
                ...lineAttrsFromStatus('unknown'),
                stroke: '#2d7df0',
              },
            },
            zIndex: 0,
          }),
        validateMagnet: ({ magnet }) =>
          magnet?.getAttribute('magnet') === 'true',
        validateConnection: ({
          sourceMagnet,
          targetMagnet,
          sourceCell,
          targetCell,
        }) => {
          if (!sourceMagnet || !targetMagnet) return false;
          if (sourceCell === targetCell) return false;
          // 仅允许端口之间连线;若拖到 body 上则不创建。
          return (
            sourceMagnet.getAttribute('magnet') === 'true' &&
            targetMagnet.getAttribute('magnet') === 'true'
          );
        },
      },
      interacting: () => ({
        nodeMovable: editModeRef.current,
        edgeMovable: false,
        arrowheadMovable: editModeRef.current,
        vertexMovable: editModeRef.current,
        vertexAddable: editModeRef.current,
        vertexDeletable: editModeRef.current,
        magnetConnectable: editModeRef.current,
      }),
    });

    graph.use(
      new Selection({
        enabled: true,
        rubberband: true,
        showNodeSelectionBox: false,
        modifiers: "shift",
        filter: (cell) =>
          editModeRef.current && (cell.isNode() || cell.isEdge()),
      }),
    );

    const isSelectionSuppressed = () =>
      Date.now() < suppressSelectionUntilRef.current;
    const suppressSelectionBriefly = (duration = 180) => {
      suppressSelectionUntilRef.current = Date.now() + duration;
    };
    const isRightButtonEvent = (event?: { button?: number; buttons?: number }) =>
      event?.button === 2 || event?.buttons === 2;
    const selectNode = (id: string, point?: { x: number; y: number }) => {
      suppressSelectionBriefly();
      onSelectNodeRef.current(id, { point });
    };
    const selectLink = (id: string, point?: { x: number; y: number }) => {
      suppressSelectionBriefly();
      onSelectLinkRef.current(id, { point });
    };

    graph.on("node:click", ({ e, node }) => {
      if (isRightButtonEvent(e)) return;
      if (!editModeRef.current) selectNode(node.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("node:mouseup", ({ e, node }) => {
      if (isRightButtonEvent(e)) return;
      if (isSelectionSuppressed()) return;
      if (!editModeRef.current) selectNode(node.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("node:dblclick", ({ e, node }) => {
      if (isRightButtonEvent(e)) return;
      if (!editModeRef.current) selectNode(node.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("node:contextmenu", ({ e, node }) => {
      e.preventDefault();
      suppressSelectionBriefly();
      onNodeContextMenuRef.current?.(node.id, {
        x: e.clientX,
        y: e.clientY,
      });
    });
    graph.on("edge:click", ({ e, edge }) => {
      if (isRightButtonEvent(e)) return;
      selectLink(edge.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("edge:mouseup", ({ e, edge }) => {
      if (isRightButtonEvent(e)) return;
      if (isSelectionSuppressed()) return;
      selectLink(edge.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("edge:dblclick", ({ e, edge }) => {
      if (isRightButtonEvent(e)) return;
      selectLink(edge.id, { x: e.clientX, y: e.clientY });
    });
    graph.on("edge:contextmenu", ({ e, edge }) => {
      e.preventDefault();
      suppressSelectionBriefly();
      onLinkContextMenuRef.current?.(edge.id, {
        x: e.clientX,
        y: e.clientY,
      });
    });
    graph.on("cell:click", ({ cell, e }) => {
      if (isSelectionSuppressed()) return;
      if (editModeRef.current) return;
      if (cell.isNode()) {
        selectNode(cell.id, { x: e.clientX, y: e.clientY });
        return;
      }
      if (cell.isEdge()) {
        selectLink(cell.id, { x: e.clientX, y: e.clientY });
      }
    });
    graph.on("blank:click", () => {
      if (isSelectionSuppressed()) return;
      onSelectNodeRef.current(null);
      onSelectLinkRef.current(null);
    });
    graph.on("node:moved", ({ node }) => {
      const pos = node.getPosition();
      onNodeMovedRef.current(node.id, { x: pos.x, y: pos.y });
    });
    graph.on("edge:connected", ({ edge }) => {
      if (!editModeRef.current) {
        edge.remove();
        return;
      }
      const currentData = (edge as X6Cell).getData<{
        link?: NetworkTopologyLink;
      }>();
      const sourceId = String(edge.getSourceCellId() ?? "");
      const targetId = String(edge.getTargetCellId() ?? "");
      if (!sourceId || !targetId || sourceId === targetId) {
        if (currentData?.link) {
          const terminals = buildNetworkTopologyLinkTerminals(currentData.link);
          edge.setSource(terminals.source);
          edge.setTarget(terminals.target);
          syncEdgeTools(edge as X6Edge, true);
          return;
        }
        edge.remove();
        return;
      }
      if (currentData?.link) {
        const sourcePortId = terminalPortId(edge.getSource());
        const targetPortId = terminalPortId(edge.getTarget());
        const nextLink = {
          ...currentData.link,
          source_node_id: sourceId,
          target_node_id: targetId,
          source_port_id: sourcePortId,
          target_port_id: targetPortId,
        };
        (edge as X6Cell).setData(
          { ...(currentData ?? {}), link: nextLink },
          { overwrite: true },
        );
        onLinkTerminalsChangedRef.current?.(edge.id, {
          source_node_id: sourceId,
          target_node_id: targetId,
          source_port_id: sourcePortId,
          target_port_id: targetPortId,
        });
        suppressSelectionBriefly(600);
        syncEdgeTools(edge as X6Edge, true);
        return;
      }
      const result = onConnectPortsRef.current?.(
        sourceId,
        targetId,
        terminalPortId(edge.getSource()),
        terminalPortId(edge.getTarget()),
      );
      if (!result || "cancel" in result) {
        edge.remove();
        return;
      }
      suppressSelectionBriefly(600);
      edge.prop("id", result.linkId);
      edge.setAttrs({ line: pendingInterfaceSelectionLineAttrs() });
      syncEdgeTools(edge as X6Edge, true);
    });
    graph.on("edge:change:vertices", ({ edge }) => {
      if (!editModeRef.current) return;
      const vertices = normalizeVertices((edge as X6Edge).getVertices());
      pendingVerticesRef.current.set(edge.id, vertices);
      const currentData = (edge as X6Cell).getData<Record<string, unknown>>();
      (edge as X6Cell).setData(
        {
          ...(currentData ?? {}),
          vertices,
        },
        { overwrite: true },
      );
    });
    graph.on("cell:mouseup", flushPendingVertices);
    graph.on("blank:mouseup", flushPendingVertices);
    window.addEventListener("mouseup", flushPendingVertices);
    window.addEventListener("pointerup", flushPendingVertices);

    graphRef.current = graph;
    onGraphReady?.(graph);
    // 第一次进入时立即 sync 一次,确保 mount 已有节点立刻可见
    syncNodes();
    syncLinks();
    requestAnimationFrame(() => {
      if (graphRef.current !== graph) return;
      const rect = host.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        graph.resize(rect.width, rect.height);
        // 空画布时 centerContent 会因为没有 cell 抛 warning,加保护。
        if (graph.getCells().length > 0) {
          graph.centerContent();
        }
      }
    });
    return () => {
      flushPendingVertices();
      window.removeEventListener("mouseup", flushPendingVertices);
      window.removeEventListener("pointerup", flushPendingVertices);
      if (graphRef.current === graph) {
        graphRef.current = null;
      }
      try {
        graph.dispose();
      } catch (error) {
        if (
          !(error instanceof DOMException) ||
          error.name !== "NotFoundError"
        ) {
          throw error;
        }
      }
    };
    // 故意使用空依赖:只在组件挂载时执行 graph.dispose 的清理,
    // 避免 React 18 StrictMode 下双挂载误杀有效 graph。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 数据变化 -> 同步
  useEffect(() => {
    syncNodes();
  }, [syncNodes]);
  useEffect(() => {
    syncLinks();
  }, [syncLinks]);

  // 宿主尺寸变化时同步 X6 内部画布大小,避免初次挂载或父级布局变化后
  // X6 内部坐标系还停留在旧的宽高(参考 topology canvasShell 的
  // ResizeObserver 写法)。
  useEffect(() => {
    const host = graphHostRef.current;
    if (!host || typeof ResizeObserver === "undefined") return undefined;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const graph = graphRef.current;
        if (!graph) return;
        const rect = host.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          graph.resize(rect.width, rect.height);
        }
      });
    });
    observer.observe(host);
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  // 拖放设备到画布
  useEffect(() => {
    const canvas = canvasRef.current;
    const graphHost = graphHostRef.current;
    if (!canvas || !graphHost) return undefined;
    const handleDragOver = (event: DragEvent) => {
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "copy";
      }
    };
    const handleDrop = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const raw = event.dataTransfer?.getData("application/json");
      if (!raw) return;
      try {
        const item = JSON.parse(raw) as NetworkNodeLibraryItem;
        const rect = graphHost.getBoundingClientRect();
        onDropDevice(item, {
          x: Math.max(0, event.clientX - rect.left - 95),
          y: Math.max(0, event.clientY - rect.top - 56),
        });
      } catch {
        // ignore
      }
    };
    canvas.addEventListener("dragover", handleDragOver);
    canvas.addEventListener("drop", handleDrop);
    return () => {
      canvas.removeEventListener("dragover", handleDragOver);
      canvas.removeEventListener("drop", handleDrop);
    };
  }, [onDropDevice]);

  // editMode 切换 → 实时更新 interacting
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.getNodes().forEach((node) => {
      const data = (node as X6Cell).getData() as
        | { node?: NetworkTopologyNode; runtime?: NetworkNodeRuntime }
        | undefined;
      if (data?.node) {
        (node as X6Cell).setAttrs(
          buildNodeAttrs(data.node, data.runtime, t, editMode),
          { overwrite: true },
        );
      }
      syncNodePorts(node as X6Node, editMode);
    });
  }, [editMode, t]);

  return (
    // 三层嵌套结构(对齐 topology/components/canvasShell.tsx 的高度链路):
    //   1. canvasRef —— flex-1 占据父级剩余高度,挂拖拽事件
    //   2. canvasMiddle —— h-full min-h-0 强制把高度传下去
    //   3. graphHostRef —— X6 真实容器,h-full w-full 撑开
    // 这样即便父级在某些 flex / grid 嵌套下高度坍塌,中间层仍能撑开
    // 高度,X6 不再因 0 尺寸不渲染导致「画布看起来全空白」。
    <div
      ref={canvasRef}
      className="relative h-full min-h-0 w-full flex-1 overflow-hidden bg-[var(--color-bg-2)]"
      data-testid={testId ?? "network-canvas"}
      data-edit-mode={editMode ? "true" : "false"}
    >
      <div className="h-full min-h-0 w-full">
        <div
          ref={graphHostRef}
          className="relative h-full min-h-0 w-full overflow-hidden"
        />
      </div>

      {/* 致命错误横幅(WeOps Token 失效):画布顶部浮层,不阻塞编辑。 */}
      {fatalMessage && (
        <div className="pointer-events-none absolute left-1/2 top-4 z-20 -translate-x-1/2">
          <Alert
            type="error"
            showIcon
            icon={<ExclamationCircleFilled />}
            message={fatalMessage}
            data-testid="network-canvas-fatal"
            className="pointer-events-auto shadow-md"
          />
        </div>
      )}

      {/* Stale 提示:运行态拉取失败但有上次缓存,继续展示,告知用户数据陈旧。 */}
      {!fatalMessage && stale && (
        <div className="pointer-events-none absolute left-1/2 top-4 z-20 -translate-x-1/2">
          <Alert
            type="warning"
            showIcon
            message={t("opsAnalysis.networkTopology.canvas.staleMessage")}
            data-testid="network-canvas-stale"
            className="pointer-events-auto shadow-md"
          />
        </div>
      )}

      {/* 加载蒙层(对齐 topology 画布 loading 行为)。 */}
      {loading && (
        <div
          className="absolute inset-0 z-10 flex items-center justify-center backdrop-blur-sm"
          style={{
            backgroundColor: "var(--color-bg-1)",
            opacity: 0.7,
          }}
          data-testid="network-canvas-loading"
        >
          <Spin size="large" />
        </div>
      )}

      {/* 空状态:不画提示,空画布就是空画布(参考 topology 参考实现)。
          如需提示用户拖拽,放到 NetworkLibrary 顶部 header 区域。 */}
    </div>
  );
};

/**
 * 给父级一个创建草稿 link id 的 helper(design.md §7.4):
 * "拖端口磁铁建连线 → X6 connecting.magnet 自动开 Drawer"。
 */
export const buildDraftLinkId = (
  existingLinks: ReadonlyArray<NetworkTopologyLink>,
): string => {
  const existingIds = existingLinks
    .map((l) => l.id)
    .filter((id): id is string => typeof id === "string");
  return nextSequentialId("link", existingIds);
};

export default NetworkCanvas;
