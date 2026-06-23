'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Empty, Spin, Segmented, Button, message, Modal } from 'antd';
import { DownloadOutlined, InfoCircleOutlined } from '@ant-design/icons';
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
import { ForceLayout } from '@antv/layout';
import { useTranslation } from '@/utils/i18n';
import { getIconUrl } from '@/app/cmdb/utils/common';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useModelApi } from '@/app/cmdb/api';
import { useRelationships } from '@/app/cmdb/context/relationships';
import type {
  NetworkTopoData,
  NetworkTopoLink,
  NetworkTopoNode,
} from '@/app/cmdb/types/assetData';
import EditToolbar from './networkTopo/EditToolbar';
import PortLinkModal, { type PortEndpoint } from './networkTopo/PortLinkModal';
import AddDevicePanel, {
  type AddableDevice,
} from './networkTopo/AddDevicePanel';
import {
  useTopoEditing,
  type PendingLink,
  type ContextMenuInfo,
} from './networkTopo/useTopoEditing';
import {
  buildConnectPayload,
  buildLinkFromConnection,
  nextFloatingPosition,
  validateConnection,
} from './networkTopo/topoEditingUtils';
import { HUB_COLOR, NODE_LIMIT } from './networkTopo/constants';
import {
  NETWORK_TOPO_VISUAL,
  buildNetworkTopoPortLabel,
} from './networkTopo/visualStyles';
import topoStyle from './index.module.scss';

const NODE_WIDTH = NETWORK_TOPO_VISUAL.node.width;
const NODE_HEIGHT = NETWORK_TOPO_VISUAL.node.height;
const DEVICE_NODE_SHAPE = 'topo-network-device';

// 展开策略：首屏 2 跳，最多 4 跳，节点上限 100（与后端常量一致）
const DEFAULT_HOP = 2;
const MAX_HOP = 4;

// 分层布局列距/行距：列距需足够大，让接口标签落在设备卡片之间的空隙、不遮挡卡片
const HIER_COL_GAP = NETWORK_TOPO_VISUAL.layout.columnGap;
const HIER_ROW_GAP = NETWORK_TOPO_VISUAL.layout.rowGap;

type LayoutMode = 'hierarchical' | 'force' | 'circular';

const DEFAULT_BODY_ATTRS = NETWORK_TOPO_VISUAL.node.defaultBody;
const ACTIVE_BODY_ATTRS = NETWORK_TOPO_VISUAL.node.activeBody;

// inst_name 形如 `${device}-${端口名}`，展示端口时剥掉设备前缀
const stripDevicePrefix = (instName?: string, device?: string): string => {
  if (!instName) return '--';
  if (device && instName.startsWith(`${device}-`)) {
    return instName.slice(device.length + 1) || '--';
  }
  return instName;
};

const ensureDeviceNodeRegistered = () => {
  Graph.registerNode(
    DEVICE_NODE_SHAPE,
    {
      inherit: 'rect',
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'rect', selector: 'iconColumn' },
        { tagName: 'line', selector: 'divider' },
        { tagName: 'rect', selector: 'iconPlate' },
        { tagName: 'image', selector: 'img' },
        { tagName: 'circle', selector: 'statusDot' },
        { tagName: 'title', selector: 'tt' },
        { tagName: 'text', selector: 'lbl' },
        { tagName: 'text', selector: 'subLbl' },
      ],
      attrs: {
        body: {
          rx: NETWORK_TOPO_VISUAL.node.radius,
          ry: NETWORK_TOPO_VISUAL.node.radius,
          cursor: 'pointer',
          ...DEFAULT_BODY_ATTRS,
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
        // img/lbl 设为 pointer-events:none，让整张卡片的命中目标始终是 body —
        // 否则从图标/文字区域起拖会落在子元素上、拿不到 body 的 magnet，连线起拖不稳定
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

interface MergedGraph {
  nodes: Map<string, NetworkTopoNode>;
  links: Map<string, NetworkTopoLink>; // key: relationship_id
}

// 在合并后的连线图上从中心做 BFS，算出每个节点到中心的跳数，用于最大跳数限制与分层布局
const computeHops = (
  merged: MergedGraph,
  centerId: string
): Map<string, number> => {
  const adj = new Map<string, Set<string>>();
  merged.links.forEach((l) => {
    if (!adj.has(l.source_device)) adj.set(l.source_device, new Set());
    if (!adj.has(l.target_device)) adj.set(l.target_device, new Set());
    adj.get(l.source_device)!.add(l.target_device);
    adj.get(l.target_device)!.add(l.source_device);
  });
  const hops = new Map<string, number>([[centerId, 0]]);
  const queue: string[] = [centerId];
  while (queue.length) {
    const cur = queue.shift() as string;
    const d = hops.get(cur) as number;
    (adj.get(cur) || new Set()).forEach((nb) => {
      if (!hops.has(nb)) {
        hops.set(nb, d + 1);
        queue.push(nb);
      }
    });
  }
  return hops;
};

type PosMap = Map<string, { x: number; y: number }>;

// 按布局模式算出每个节点的中心坐标。prev 为上一次坐标，力导向据此增量布局、避免每次展开整图重排
const computePositions = async (
  merged: MergedGraph,
  centerId: string,
  mode: LayoutMode,
  prev?: PosMap
): Promise<PosMap> => {
  const ids = Array.from(merged.nodes.keys());
  const pos: PosMap = new Map();

  if (mode === 'force') {
    const data = {
      // 已有节点用上次坐标作为初值（增量稳定），新节点从中心附近出发
      nodes: ids.map((id) => {
        const p = prev?.get(id);
        return p ? { id, x: p.x, y: p.y } : { id };
      }),
      edges: Array.from(merged.links.values()).map((l) => ({
        source: l.source_device,
        target: l.target_device,
      })),
    };
    const layout = new ForceLayout({
      dimensions: 2,
      width: 1200,
      height: 800,
      // 设备卡片较宽，且边上要放两段接口名，必须拉大节点间距、避免标签压住卡片
      linkDistance: 640,
      nodeStrength: 2000,
      edgeStrength: 0.5,
      preventOverlap: true,
      nodeSize: [NODE_WIDTH, NODE_HEIGHT],
      nodeSpacing: 80,
    });
    try {
      await layout.execute(data as any);
      let cx = 0;
      let cy = 0;
      layout.forEachNode((n: any) => {
        pos.set(String(n.id), { x: n.x, y: n.y });
        if (String(n.id) === centerId) {
          cx = n.x;
          cy = n.y;
        }
      });
      // 平移使中心节点落在原点，便于 fitView 居中
      pos.forEach((p) => {
        p.x -= cx;
        p.y -= cy;
      });
    } finally {
      // 结束模拟，避免实例与定时器悬留
      try {
        (layout as any).stop?.();
      } catch {
        // ignore
      }
    }
    return pos;
  }

  if (mode === 'hierarchical') {
    const hopMap = computeHops(merged, centerId);
    const byHop = new Map<number, string[]>();
    ids.forEach((id) => {
      const h = hopMap.get(id) ?? 99;
      if (!byHop.has(h)) byHop.set(h, []);
      byHop.get(h)!.push(id);
    });
    byHop.forEach((arr, h) => {
      const n = arr.length;
      arr.forEach((id, i) => {
        pos.set(id, { x: h * HIER_COL_GAP, y: (i - (n - 1) / 2) * HIER_ROW_GAP });
      });
    });
    return pos;
  }

  // circular：中心居中，其余均匀分布在一个圆上
  const others = ids.filter((id) => id !== centerId);
  const count = others.length;
  const radius = Math.max(300, count * 64);
  pos.set(centerId, { x: 0, y: 0 });
  others.forEach((id, index) => {
    const angle = (index / Math.max(count, 1)) * Math.PI * 2 - Math.PI / 2;
    pos.set(id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  });
  return pos;
};

const portLabel = (position: number, text: string) => ({
  ...buildNetworkTopoPortLabel(position, text),
});

interface BuiltGraph {
  nodes: any[];
  edges: any[];
}

// 把合并后的 nodes/links + 坐标转成 x6 图数据
const buildGraphData = (
  merged: MergedGraph,
  centerId: string,
  nameOf: (id: string) => string,
  subtitleOf: (id: string) => string,
  positions: PosMap
): BuiltGraph => {
  const ids = Array.from(merged.nodes.keys());
  const centers: Record<string, { x: number; y: number }> = {};

  const nodes = ids.map((id) => {
    const p = positions.get(id) || { x: 0, y: 0 };
    centers[id] = { x: p.x, y: p.y };
    const label = nameOf(id);
    const subtitle = subtitleOf(id);
    return {
      id,
      x: p.x - NODE_WIDTH / 2,
      y: p.y - NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      shape: DEVICE_NODE_SHAPE,
      data: {
        isCenter: id === centerId,
      },
      attrs: {
        body: id === centerId ? ACTIVE_BODY_ATTRS : {},
        iconColumn: {
          fill: id === centerId ? '#eef7ff' : '#f7fbff',
        },
        divider: {
          stroke: id === centerId ? '#c7def8' : '#e1ebf6',
        },
        statusDot: {
          fill: id === centerId ? '#42d9a6' : '#7dd3fc',
          stroke: id === centerId ? '#eafff7' : '#eff8ff',
        },
        img: {
          'xlink:href': getIconUrl({
            icn: '',
            model_id: merged.nodes.get(id)?.model_id || '',
          }),
        },
        tt: { text: label },
        lbl: { text: label, title: label },
        subLbl: { text: subtitle, title: subtitle },
      },
    };
  });

  const links = Array.from(merged.links.values());
  const pairCount: Record<string, number> = {};
  const pairIndex: Record<string, number> = {};
  links.forEach((l) => {
    const key = [l.source_device, l.target_device].sort().join('__');
    pairCount[key] = (pairCount[key] || 0) + 1;
  });

  const edges = links.map((l) => {
    const key = [l.source_device, l.target_device].sort().join('__');
    const total = pairCount[key];
    const idx = pairIndex[key] || 0;
    pairIndex[key] = idx + 1;

    let vertices: Array<{ x: number; y: number }> | undefined;
    if (total > 1) {
      const a = centers[l.source_device];
      const b = centers[l.target_device];
      if (a && b) {
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy) || 1;
        const offset = (idx - (total - 1) / 2) * 48;
        if (offset !== 0) {
          vertices = [{ x: mx + (-dy / len) * offset, y: my + (dx / len) * offset }];
        }
      }
    }

    return {
      id: `edge-${l.relationship_id}`,
      source: l.source_device,
      target: l.target_device,
      vertices,
      connector: { name: 'smooth' },
      attrs: {
        line: {
          stroke: NETWORK_TOPO_VISUAL.edge.stroke,
          strokeWidth: NETWORK_TOPO_VISUAL.edge.strokeWidth,
          strokeLinecap: 'round',
          strokeLinejoin: 'round',
          targetMarker: null,
          filter: 'drop-shadow(0 1px 2px rgba(28, 55, 92, 0.16))',
        },
      },
      labels: [
        portLabel(
          NETWORK_TOPO_VISUAL.portLabelPosition.source,
          stripDevicePrefix(l.source_inst_name, nameOf(l.source_device))
        ),
        portLabel(
          NETWORK_TOPO_VISUAL.portLabelPosition.target,
          stripDevicePrefix(l.target_inst_name, nameOf(l.target_device))
        ),
      ],
    };
  });

  return { nodes, edges };
};

interface NetworkTopoProps {
  modelId: string;
  instId: string;
}

interface GraphLoaderProps {
  data: BuiltGraph;
  centerId: string;
  expandedRef: React.MutableRefObject<Set<string>>;
  onExpand: (node: NetworkTopoNode) => void;
  nodesMap: Map<string, NetworkTopoNode>;
  graphRef: React.MutableRefObject<Graph | null>;
  editing: boolean;
  onGraphReady?: (g: Graph | null) => void;
}

const GraphLoader: React.FC<GraphLoaderProps> = ({
  data,
  centerId,
  expandedRef,
  onExpand,
  nodesMap,
  graphRef,
  editing,
  onGraphReady,
}) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();

  useEffect(() => {
    ensureDeviceNodeRegistered();
    initData({ nodes: data.nodes, edges: data.edges });
  }, [initData, data]);

  // 把 graph 实例提升到父级 ref，并注册导出插件（供工具栏的导出图片按钮使用）
  useEffect(() => {
    if (!graph) return;
    graphRef.current = graph;
    onGraphReady?.(graph);
    if (!graph.getPlugin('export')) {
      graph.use(new Export());
    }
    return () => {
      graphRef.current = null;
      onGraphReady?.(null);
    };
  }, [graph, graphRef, onGraphReady]);

  // 数据/布局变化后重新适配视口，避免切换布局后节点跑到画布外
  useEffect(() => {
    if (!graph) return;
    const timer = window.setTimeout(() => {
      try {
        graph.zoomToFit({ padding: 112, maxScale: 1.12 });
      } catch {
        // 图未就绪时忽略
      }
    }, 60);
    return () => window.clearTimeout(timer);
  }, [graph, data]);

  useEffect(() => {
    if (!graph) return;
    const handleNodeClick = ({ node }: { node: any }) => {
      if (editing) return; // 编辑态点节点不展开，让位连线/选择
      const id = node.id as string;
      if (id === centerId || expandedRef.current.has(id)) return;
      const target = nodesMap.get(id);
      if (target) onExpand(target);
    };
    graph.on('node:click', handleNodeClick);
    return () => {
      graph.off('node:click', handleNodeClick);
    };
  }, [graph, centerId, expandedRef, onExpand, nodesMap, editing]);

  return null;
};

const NetworkTopo: React.FC<NetworkTopoProps> = ({ modelId, instId }) => {
  const { t } = useTranslation();
  const {
    getNetworkTopo,
    createInstanceAssociation,
    deleteInstanceAssociation,
  } = useInstanceApi();
  const { getModelAssociations } = useModelApi();
  const { modelList } = useRelationships();
  const [loading, setLoading] = useState<boolean>(false);
  const [centerId, setCenterId] = useState<string>('');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('hierarchical');
  const mergedRef = useRef<MergedGraph>({ nodes: new Map(), links: new Map() });
  const expandedRef = useRef<Set<string>>(new Set());
  const hopMapRef = useRef<Map<string, number>>(new Map());
  const posRef = useRef<PosMap>(new Map());
  const graphRef = useRef<Graph | null>(null);
  const mountedRef = useRef<boolean>(true);
  const [graphData, setGraphData] = useState<BuiltGraph>({ nodes: [], edges: [] });

  // 编辑态
  const [editing, setEditing] = useState(false);
  const [addPanelOpen, setAddPanelOpen] = useState(false);
  const [pendingLink, setPendingLink] = useState<PendingLink | null>(null);
  const [graphInstance, setGraphInstance] = useState<Graph | null>(null);
  const [networkModels, setNetworkModels] = useState<string[]>([]);
  // 右键连线交互：已选起点 + 右键上下文菜单
  const [linkingSourceId, setLinkingSourceId] = useState<string | null>(null);
  const [menu, setMenu] = useState<ContextMenuInfo | null>(null);
  // 游离节点：id -> {node, x, y}，单独维护、并入渲染；仅内存，刷新即清空
  const floatingRef = useRef<
    Map<string, { node: NetworkTopoNode; x: number; y: number }>
  >(new Map());

  const modelOf = useCallback(
    (id: string) =>
      mergedRef.current.nodes.get(id)?.model_id ||
      floatingRef.current.get(id)?.node.model_id,
    []
  );
  const modelNameOf = useCallback(
    (mid: string) =>
      modelList.find((m: any) => m.model_id === mid)?.model_name || mid,
    [modelList]
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // 预取网络设备模型集（interface 的 belong 关联的 dst 模型）。
  // 只跑一次：getModelAssociations 每次渲染都是新引用，若入依赖会无限请求后端。
  useEffect(() => {
    getModelAssociations('interface')
      .then((assoc: any[]) =>
        setNetworkModels(
          (assoc || [])
            .filter(
              (a) => a.asst_id === 'belong' && a.src_model_id === 'interface'
            )
            .map((a) => a.dst_model_id)
        )
      )
      .catch(() => setNetworkModels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rebuild = useCallback(async (center: string, mode: LayoutMode) => {
    // 渲染节点集 = 已合并节点 + 未连线的游离节点
    const renderNodes = new Map(mergedRef.current.nodes);
    hopMapRef.current = computeHops(mergedRef.current, center);
    const positions = await computePositions(
      mergedRef.current,
      center,
      mode,
      posRef.current
    );
    if (!mountedRef.current) return;
    floatingRef.current.forEach((f, id) => {
      if (!renderNodes.has(id)) {
        renderNodes.set(id, f.node);
        positions.set(id, { x: f.x, y: f.y });
      }
    });
    posRef.current = positions;
    setGraphData(
      buildGraphData(
        { nodes: renderNodes, links: mergedRef.current.links },
        center,
        (id) => renderNodes.get(id)?.name || id,
        (id) => modelNameOf(renderNodes.get(id)?.model_id || ''),
        positions
      )
    );
  }, [modelNameOf]);

  // 合并新拓扑数据；后端 expanded=true 的节点（已查询过其邻居）记入已展开集合
  const mergeData = useCallback((data: NetworkTopoData) => {
    const merged = mergedRef.current;
    const markExpanded = (n: NetworkTopoNode) => {
      merged.nodes.set(n.id, n);
      if (n.expanded) expandedRef.current.add(n.id);
    };
    (data.nodes || []).forEach(markExpanded);
    if (data.center) markExpanded(data.center);
    (data.links || []).forEach((l) => merged.links.set(l.relationship_id, l));
  }, []);

  // 初次加载：默认展开 2 跳
  useEffect(() => {
    if (!modelId || !instId) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const data: NetworkTopoData = await getNetworkTopo(
          modelId,
          instId,
          DEFAULT_HOP
        );
        if (cancelled) return;
        // 接口异常或空响应可能没有 center，按空拓扑处理，避免崩溃
        if (!data?.center?.id) return;
        mergedRef.current = { nodes: new Map(), links: new Map() };
        expandedRef.current = new Set();
        posRef.current = new Map();
        mergeData(data);
        setCenterId(data.center.id);
        await rebuild(data.center.id, layoutMode);
        if (data.truncated) {
          message.warning(t('Model.networkTopoNodeLimit'));
        }
      } catch {
        // 首屏拉取失败：保持空态，不抛未捕获异常
      } finally {
        if (!cancelled && mountedRef.current) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, instId]);

  // 点击对端设备：取其下一跳并合并（受最大跳数与节点上限约束）
  const handleExpand = useCallback(
    async (node: NetworkTopoNode) => {
      if (expandedRef.current.has(node.id)) return;
      const hop = hopMapRef.current.get(node.id) ?? 0;
      if (hop >= MAX_HOP) {
        message.warning(t('Model.networkTopoMaxHop'));
        return;
      }
      if (mergedRef.current.nodes.size >= NODE_LIMIT) {
        message.warning(t('Model.networkTopoNodeLimit'));
        return;
      }
      expandedRef.current.add(node.id);
      setLoading(true);
      try {
        const data: NetworkTopoData = await getNetworkTopo(
          node.model_id,
          node.id,
          1
        );
        if (!mountedRef.current) return;
        mergeData(data);
        await rebuild(centerId, layoutMode);
        if (data.truncated || mergedRef.current.nodes.size >= NODE_LIMIT) {
          message.warning(t('Model.networkTopoNodeLimit'));
        }
      } catch {
        // 展开失败：撤销已展开标记，允许用户重试
        expandedRef.current.delete(node.id);
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    },
    [getNetworkTopo, mergeData, rebuild, centerId, layoutMode, t]
  );

  const handleLayoutChange = useCallback(
    (mode: LayoutMode) => {
      setLayoutMode(mode);
      if (centerId) rebuild(centerId, mode);
    },
    [centerId, rebuild]
  );

  const handleExportImage = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    // 默认 copyStyles 会临时禁用整页样式表再恢复，导致页面闪烁/抖动；这里关掉它，
    // 改为只把节点用到的几个 CSS 变量解析后注入导出 SVG，颜色仍正常且不动整页样式。
    const cs = getComputedStyle(document.documentElement);
    const fallback: Record<string, string> = {
      '--color-bg-1': '#ffffff',
      '--color-text-1': '#1f2329',
      '--color-text-4': '#8a8f99',
      '--color-border-1': '#e5e6eb',
      '--color-border-3': '#c9cdd4',
    };
    const decls = Object.keys(fallback)
      .map((v) => `${v}:${cs.getPropertyValue(v).trim() || fallback[v]};`)
      .join('');
    graph.exportPNG('network-topo', {
      padding: 40,
      backgroundColor: '#ffffff',
      copyStyles: false,
      stylesheet: `:root,svg{${decls}}`,
    });
  }, []);

  // 删除连线（已落库），更新合并图并 rebuild
  const handleDeleteLink = useCallback(
    async (relationshipId: string) => {
      await deleteInstanceAssociation(relationshipId);
      mergedRef.current.links.delete(relationshipId);
      message.success(t('successfullyDisassociated'));
      await rebuild(centerId, layoutMode);
    },
    [deleteInstanceAssociation, rebuild, centerId, layoutMode, t]
  );

  // 删除连线（带「采集可能加回」提示）
  const confirmDeleteLink = useCallback(
    (relationshipId: string) => {
      Modal.confirm({
        title: t('Model.networkTopoDeleteLinkTitle'),
        content: t('Model.networkTopoDeleteLinkContent'),
        centered: true,
        onOk: () => handleDeleteLink(relationshipId),
      });
    },
    [handleDeleteLink, t]
  );

  // 右键菜单：节点->新增连线菜单；边->删除连线菜单
  const handleContextMenu = useCallback((info: ContextMenuInfo) => {
    setMenu(info);
  }, []);

  // 连线进行中点击目标设备：校验后弹端口小窗
  const handlePickTarget = useCallback(
    (targetId: string) => {
      const sourceId = linkingSourceId;
      setLinkingSourceId(null);
      if (!sourceId) return;
      const v = validateConnection({
        sourceId,
        targetId,
        modelOf,
        networkModels,
      });
      if (!v.ok) {
        if (v.reason === 'self') message.warning(t('Model.networkTopoNoSelfLink'));
        else if (v.reason === 'not_network')
          message.warning(t('Model.networkTopoOnlyNetwork'));
        return;
      }
      setPendingLink({ sourceId, targetId });
    },
    [linkingSourceId, modelOf, networkModels, t]
  );

  // X6 编辑副作用：右键菜单 + 连线目标选择（左键拖动=移动设备）
  useTopoEditing({
    graph: graphInstance,
    editing,
    linkingSourceId,
    // 节点+边总数作为版本：连线/加设备/删线后变化，触发光标/高亮重应用
    revision: graphData.nodes.length + graphData.edges.length,
    onContextMenu: handleContextMenu,
    onPickTarget: handlePickTarget,
    onCancel: () => setLinkingSourceId(null),
  });

  // Esc 取消连线 / 关闭菜单
  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setLinkingSourceId(null);
        setMenu(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [editing]);

  // 退出编辑态时清理连线/菜单状态
  useEffect(() => {
    if (!editing) {
      setLinkingSourceId(null);
      setMenu(null);
    }
  }, [editing]);

  // 端口小窗的端点信息
  const endpointOf = useCallback((id: string): PortEndpoint => {
    const n =
      mergedRef.current.nodes.get(id) || floatingRef.current.get(id)?.node;
    return { id, name: n?.name || id, model_id: n?.model_id || '' };
  }, []);

  // 端口小窗确认 -> 建 connect 关联 + 合并链路（游离节点转正）
  const handleConfirmLink = useCallback(
    async (r: {
      sourcePortId: string;
      sourcePortName: string;
      targetPortId: string;
      targetPortName: string;
    }) => {
      if (!pendingLink) return;
      const res = await createInstanceAssociation(
        buildConnectPayload(r.sourcePortId, r.targetPortId)
      );
      const { sourceId, targetId } = pendingLink;
      [sourceId, targetId].forEach((id) => {
        const f = floatingRef.current.get(id);
        if (f && !mergedRef.current.nodes.has(id)) {
          mergedRef.current.nodes.set(id, f.node);
          floatingRef.current.delete(id);
        }
      });
      const link = buildLinkFromConnection({
        relationshipId: String(res._id),
        sourceDevice: sourceId,
        targetDevice: targetId,
        sourcePortName: r.sourcePortName,
        targetPortName: r.targetPortName,
      });
      mergedRef.current.links.set(link.relationship_id, link);
      setPendingLink(null);
      message.success(t('successfullyAssociated'));
      await rebuild(centerId, layoutMode);
    },
    [pendingLink, createInstanceAssociation, rebuild, centerId, layoutMode, t]
  );

  // 添加画布外设备 -> 游离节点（受节点上限约束）
  const handleAddDevices = useCallback(
    (devices: AddableDevice[]) => {
      let idx = floatingRef.current.size + mergedRef.current.nodes.size;
      devices.forEach((d) => {
        if (mergedRef.current.nodes.has(d.id) || floatingRef.current.has(d.id))
          return;
        if (
          mergedRef.current.nodes.size + floatingRef.current.size >=
          NODE_LIMIT
        ) {
          message.warning(t('Model.networkTopoNodeLimit'));
          return;
        }
        const pos = nextFloatingPosition(idx++);
        floatingRef.current.set(d.id, {
          node: { id: d.id, name: d.name, model_id: d.model_id, expanded: false },
          x: pos.x,
          y: pos.y,
        });
      });
      rebuild(centerId, layoutMode);
    },
    [rebuild, centerId, layoutMode, t]
  );

  const existingIds = new Set<string>([
    ...Array.from(mergedRef.current.nodes.keys()),
    ...Array.from(floatingRef.current.keys()),
  ]);

  const hasGraph = graphData.nodes.length > 0;

  return (
    <div>
      <Spin spinning={loading}>
        <div
          className={topoStyle.topo}
          style={{
            height: 'calc(100vh - 178px)',
            minHeight: 620,
            position: 'relative',
            ...NETWORK_TOPO_VISUAL.canvas,
          }}
        >
          <div
            className="absolute left-4 top-4 z-20 flex items-center"
            style={{
              padding: 3,
              borderRadius: 8,
              background: 'rgba(255,255,255,0.9)',
              border: '1px solid rgba(215, 229, 244, 0.92)',
              boxShadow: '0 10px 24px rgba(37, 72, 111, 0.09)',
              backdropFilter: 'blur(8px)',
            }}
          >
            <Segmented
              value={layoutMode}
              onChange={(val) => handleLayoutChange(val as LayoutMode)}
              options={[
                { label: t('Model.layoutHierarchical'), value: 'hierarchical' },
                { label: t('Model.layoutForce'), value: 'force' },
                { label: t('Model.layoutCircular'), value: 'circular' },
              ]}
            />
          </div>
          <div
            className={`${topoStyle.topoCommandBar} absolute right-4 top-4 z-20 flex items-center gap-2`}
          >
            <EditToolbar
              editing={editing}
              onToggle={() => setEditing((v) => !v)}
              onAddDevice={() => setAddPanelOpen(true)}
            />
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExportImage}
              disabled={!hasGraph}
            >
              {t('Model.exportImage')}
            </Button>
          </div>
          {editing && (
            <div
              className="absolute left-4 top-[58px] z-20 px-3 py-1.5 text-[13px] flex items-center gap-1.5"
              style={{
                borderRadius: 8,
                background: linkingSourceId
                  ? 'rgba(232, 243, 255, 0.94)'
                  : 'rgba(255, 255, 255, 0.88)',
                border: '1px solid rgba(205, 222, 241, 0.9)',
                boxShadow: '0 8px 22px rgba(37, 72, 111, 0.08)',
                color: linkingSourceId
                  ? HUB_COLOR
                  : 'var(--color-text-3, #86909c)',
                backdropFilter: 'blur(8px)',
              }}
            >
              <InfoCircleOutlined style={{ color: HUB_COLOR }} />
              {linkingSourceId
                ? t('Model.networkTopoPickTargetHint')
                : t('Model.networkTopoEditHint')}
            </div>
          )}
          {hasGraph ? (
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
                width={200}
                height={120}
                style={NETWORK_TOPO_VISUAL.minimap}
              />
              <GraphLoader
                data={graphData}
                centerId={centerId}
                expandedRef={expandedRef}
                onExpand={handleExpand}
                nodesMap={mergedRef.current.nodes}
                graphRef={graphRef}
                editing={editing}
                onGraphReady={setGraphInstance}
              />
            </XFlow>
          ) : (
            !loading && (
              <div className="flex items-center justify-center h-full">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('Model.noNetworkTopo')}
                />
              </div>
            )
          )}
        </div>
      </Spin>
      <PortLinkModal
        open={!!pendingLink}
        source={pendingLink ? endpointOf(pendingLink.sourceId) : null}
        target={pendingLink ? endpointOf(pendingLink.targetId) : null}
        onCancel={() => setPendingLink(null)}
        onConfirm={handleConfirmLink}
      />
      <AddDevicePanel
        open={addPanelOpen}
        onClose={() => setAddPanelOpen(false)}
        existingIds={existingIds}
        modelNameOf={modelNameOf}
        onAdd={handleAddDevices}
      />
      {menu && (
        <>
          {/* 透明遮罩：点空白处关闭菜单 */}
          <div
            className="fixed inset-0 z-[1000]"
            onClick={() => setMenu(null)}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu(null);
            }}
          />
          <div
            className="fixed z-[1001] min-w-[120px] py-1 rounded shadow-lg"
            style={{
              left: menu.x,
              top: menu.y,
              background: 'var(--color-bg-1, #fff)',
              border: '1px solid var(--color-border-2, #e5e6eb)',
            }}
          >
            {menu.kind === 'node' ? (
              <div
                className="px-3 py-1.5 text-[13px] cursor-pointer hover:bg-[var(--color-fill-1,#f2f3f5)]"
                onClick={() => {
                  setLinkingSourceId(menu.id);
                  setMenu(null);
                }}
              >
                {t('Model.networkTopoAddLink')}
              </div>
            ) : (
              <div
                className="px-3 py-1.5 text-[13px] cursor-pointer text-[var(--color-error,#f53f3f)] hover:bg-[var(--color-fill-1,#f2f3f5)]"
                onClick={() => {
                  confirmDeleteLink(menu.id);
                  setMenu(null);
                }}
              >
                {t('Model.networkTopoDeleteLink')}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default NetworkTopo;
