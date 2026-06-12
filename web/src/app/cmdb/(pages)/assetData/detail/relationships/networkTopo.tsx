'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Empty, Spin, Segmented, Button, message } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
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
import type {
  NetworkTopoData,
  NetworkTopoLink,
  NetworkTopoNode,
} from '@/app/cmdb/types/assetData';

const NODE_WIDTH = 260;
const NODE_HEIGHT = 72;
const DEVICE_NODE_SHAPE = 'topo-network-device';
const HUB_COLOR = '#0070fa';

// 展开策略：首屏 2 跳，最多 4 跳，节点上限 100（与后端常量一致）
const DEFAULT_HOP = 2;
const MAX_HOP = 4;
const NODE_LIMIT = 100;

// 分层布局列距/行距：列距需足够大，让接口标签落在设备卡片之间的空隙、不遮挡卡片
const HIER_COL_GAP = 720;
const HIER_ROW_GAP = 160;

type LayoutMode = 'hierarchical' | 'force' | 'circular';

const DEFAULT_BODY_ATTRS = {
  stroke: 'var(--color-border-1)',
  strokeWidth: 1,
  filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.08))',
};
const ACTIVE_BODY_ATTRS = {
  stroke: HUB_COLOR,
  strokeWidth: 2,
  filter: 'drop-shadow(0 2px 10px rgba(0,112,250,0.35))',
};

// inst_name 形如 `${device}-${端口名}`，展示端口时剥掉设备前缀
const stripDevicePrefix = (instName?: string, device?: string): string => {
  if (!instName) return '--';
  if (device && instName.startsWith(`${device}-`)) {
    return instName.slice(device.length + 1) || '--';
  }
  return instName;
};

let deviceNodeRegistered = false;
const ensureDeviceNodeRegistered = () => {
  if (deviceNodeRegistered) return;
  Graph.registerNode(
    DEVICE_NODE_SHAPE,
    {
      inherit: 'rect',
      markup: [
        { tagName: 'rect', selector: 'body' },
        { tagName: 'image', selector: 'img' },
        { tagName: 'title', selector: 'tt' },
        { tagName: 'text', selector: 'lbl' },
      ],
      attrs: {
        body: {
          rx: 10,
          ry: 10,
          fill: 'var(--color-bg-1)',
          cursor: 'pointer',
          ...DEFAULT_BODY_ATTRS,
        },
        img: { width: 44, height: 44, x: 18, y: (NODE_HEIGHT - 44) / 2 },
        lbl: {
          refX: 0.27,
          refY: 0.5,
          textAnchor: 'start',
          textVerticalAnchor: 'middle',
          fontSize: 16,
          fontWeight: 600,
          fill: 'var(--color-text-1)',
          textWrap: { width: NODE_WIDTH - 84, height: 24, ellipsis: true },
        },
      },
    },
    true
  );
  deviceNodeRegistered = true;
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

const portLabelFill = 'var(--color-text-4)';
const portLabel = (position: number, text: string) => ({
  position,
  markup: [
    { tagName: 'rect', selector: 'bg' },
    { tagName: 'text', selector: 'txt' },
  ],
  attrs: {
    txt: {
      text: text || '--',
      fill: portLabelFill,
      fontSize: 11,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
    bg: {
      ref: 'txt',
      refWidth: '130%',
      refHeight: '130%',
      refX: '-15%',
      refY: '-15%',
      fill: 'var(--color-bg-1)',
      stroke: 'var(--color-border-3)',
      rx: 3,
      ry: 3,
    },
  },
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
  positions: PosMap
): BuiltGraph => {
  const deviceIcon = getIconUrl({ icn: '', model_id: 'network' });
  const ids = Array.from(merged.nodes.keys());
  const centers: Record<string, { x: number; y: number }> = {};

  const nodes = ids.map((id) => {
    const p = positions.get(id) || { x: 0, y: 0 };
    centers[id] = { x: p.x, y: p.y };
    const label = nameOf(id);
    return {
      id,
      x: p.x - NODE_WIDTH / 2,
      y: p.y - NODE_HEIGHT / 2,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      shape: DEVICE_NODE_SHAPE,
      attrs: {
        body: id === centerId ? ACTIVE_BODY_ATTRS : {},
        img: { 'xlink:href': deviceIcon },
        tt: { text: label },
        lbl: { text: label, title: label },
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
        line: { stroke: 'var(--color-border-3)', strokeWidth: 1, targetMarker: null },
      },
      labels: [
        portLabel(0.32, stripDevicePrefix(l.source_inst_name, nameOf(l.source_device))),
        portLabel(0.68, stripDevicePrefix(l.target_inst_name, nameOf(l.target_device))),
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
}

const GraphLoader: React.FC<GraphLoaderProps> = ({
  data,
  centerId,
  expandedRef,
  onExpand,
  nodesMap,
  graphRef,
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
    if (!graph.getPlugin('export')) {
      graph.use(new Export());
    }
    return () => {
      graphRef.current = null;
    };
  }, [graph, graphRef]);

  // 数据/布局变化后重新适配视口，避免切换布局后节点跑到画布外
  useEffect(() => {
    if (!graph) return;
    const timer = window.setTimeout(() => {
      try {
        graph.zoomToFit({ padding: 40, maxScale: 1.2 });
      } catch {
        // 图未就绪时忽略
      }
    }, 60);
    return () => window.clearTimeout(timer);
  }, [graph, data]);

  useEffect(() => {
    if (!graph) return;
    const handleNodeClick = ({ node }: { node: any }) => {
      const id = node.id as string;
      if (id === centerId || expandedRef.current.has(id)) return;
      const target = nodesMap.get(id);
      if (target) onExpand(target);
    };
    graph.on('node:click', handleNodeClick);
    return () => {
      graph.off('node:click', handleNodeClick);
    };
  }, [graph, centerId, expandedRef, onExpand, nodesMap]);

  return null;
};

const NetworkTopo: React.FC<NetworkTopoProps> = ({ modelId, instId }) => {
  const { t } = useTranslation();
  const { getNetworkTopo } = useInstanceApi();
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

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const rebuild = useCallback(async (center: string, mode: LayoutMode) => {
    hopMapRef.current = computeHops(mergedRef.current, center);
    const positions = await computePositions(
      mergedRef.current,
      center,
      mode,
      posRef.current
    );
    if (!mountedRef.current) return;
    posRef.current = positions;
    setGraphData(
      buildGraphData(
        mergedRef.current,
        center,
        (id) => mergedRef.current.nodes.get(id)?.name || id,
        positions
      )
    );
  }, []);

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

  const hasGraph = graphData.nodes.length > 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-[10px] gap-2">
        <Segmented
          value={layoutMode}
          onChange={(val) => handleLayoutChange(val as LayoutMode)}
          options={[
            { label: t('Model.layoutHierarchical'), value: 'hierarchical' },
            { label: t('Model.layoutForce'), value: 'force' },
            { label: t('Model.layoutCircular'), value: 'circular' },
          ]}
        />
        <Button
          icon={<DownloadOutlined />}
          onClick={handleExportImage}
          disabled={!hasGraph}
        >
          {t('Model.exportImage')}
        </Button>
      </div>
      <Spin spinning={loading}>
        <div style={{ height: '66vh', position: 'relative' }}>
          {hasGraph ? (
            <XFlow>
              <XFlowGraph zoomable pannable minScale={0.2} maxScale={4} fitView />
              <Grid type="dot" options={{ color: '#ccc', thickness: 1 }} />
              <Minimap
                width={200}
                height={120}
                style={{
                  border: '1px solid var(--color-border-3)',
                  bottom: '10px',
                  right: '10px',
                  position: 'absolute',
                }}
              />
              <GraphLoader
                data={graphData}
                centerId={centerId}
                expandedRef={expandedRef}
                onExpand={handleExpand}
                nodesMap={mergedRef.current.nodes}
                graphRef={graphRef}
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
    </div>
  );
};

export default NetworkTopo;
