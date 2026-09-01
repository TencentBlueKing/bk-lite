import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyNode } from '@/app/apm/types';
import {
  buildTopologyEdgeGeometry,
  filterAnomalousTopology,
  filterTopologyByKeyword,
  focusApplicationTopology,
  isolateTopologyNeighborhood,
  layoutForceTopology,
  layoutLayeredTopology,
  topologyCardsOverlap,
  TOPOLOGY_CANVAS_SIZE,
  topologyEntryPillWidth,
  topologyNodeNameWidth,
  truncateTopologyNodeLabel,
} from '../topology-layout';

const topologyLayoutSource = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../topology-layout.ts'),
  'utf8',
);

const node = (id: string): ApmTopologyNode => ({
  id,
  service_namespace: 'apm-demo-shop',
  service_name: id,
  environment: 'local',
  health: 'healthy',
  sampled_spans: 100,
  error_spans: 0,
});

const edge = (source: string, target: string): ApmTopologyEdge => ({
  source,
  target,
  health: 'healthy',
  sampled_calls: 10,
  error_calls: 0,
  average_duration_ms: 12,
});

const demoNodes = [
  node('demo-catalog'),
  node('demo-inventory'),
  node('demo-orders'),
  node('demo-payment'),
  node('demo-storefront'),
];

const demoEdges = [
  edge('demo-catalog', 'demo-inventory'),
  edge('demo-orders', 'demo-inventory'),
  edge('demo-orders', 'demo-payment'),
  edge('demo-storefront', 'demo-catalog'),
  edge('demo-storefront', 'demo-orders'),
];

describe('APM 服务拓扑布局', () => {
  it('按调用方向自上而下分层，根服务在上层', async () => {
    const result = await layoutLayeredTopology(demoNodes, demoEdges);
    const byId = new Map(result.map((item) => [item.id, item]));

    expect(byId.get('demo-storefront')?.y).toBeLessThan(byId.get('demo-catalog')?.y ?? 0);
    expect(byId.get('demo-storefront')?.y).toBeLessThan(byId.get('demo-orders')?.y ?? 0);
    expect(byId.get('demo-catalog')?.y).toBeLessThan(byId.get('demo-inventory')?.y ?? 0);
    expect(byId.get('demo-orders')?.y).toBeLessThan(byId.get('demo-payment')?.y ?? 0);
    expect(new Set(result.map((item) => `${item.x}:${item.y}`)).size).toBe(result.length);
  });

  it('分层布局始终落在画布安全区域内', async () => {
    const result = await layoutLayeredTopology(demoNodes, demoEdges);

    result.forEach((item) => {
      expect(item.x).toBeGreaterThanOrEqual(90);
      expect(item.x).toBeLessThanOrEqual(950);
      expect(item.y).toBeGreaterThanOrEqual(90);
      expect(item.y).toBeLessThanOrEqual(540);
    });
    expect(topologyCardsOverlap(result)).toBe(false);
  });

  it('同层多个服务卡片不重叠，即使超出默认视口', async () => {
    const root = node('root');
    const siblings = ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => node(id));
    const result = await layoutLayeredTopology([root, ...siblings], siblings.map((item) => edge('root', item.id)));
    const childXs = result.filter((item) => item.id !== 'root').map((item) => item.x);
    expect(Math.max(...childXs) - Math.min(...childXs)).toBeGreaterThan(TOPOLOGY_CANVAS_SIZE.width / 2);
    expect(topologyCardsOverlap(result)).toBe(false);
  });
});

describe('APM 服务拓扑力导向稳定性', () => {
  const directedNodes: ApmTopologyNode[] = [
    node('storefront'),
    node('catalog'),
    node('inventory'),
    { ...node('user_request'), id: 'user_request:local', service_name: 'user_request', service_namespace: '', kind: 'user_request', health: 'unknown' },
    { ...node('mysql'), id: 'inferred:local:mysql', kind: 'inferred', fold_key: 'mysql' },
  ];
  const directedEdges: ApmTopologyEdge[] = [
    edge('user_request:local', 'storefront'),
    edge('storefront', 'catalog'),
    edge('catalog', 'inventory'),
    edge('inventory', 'inferred:local:mysql'),
  ];
  const positionsById = (items: { id: string; x: number; y: number }[]) => (
    Object.fromEntries(items.map((item) => [item.id, { x: item.x, y: item.y }]))
  );
  const distance = (
    left: { x: number; y: number } | undefined,
    right: { x: number; y: number } | undefined,
  ) => Math.hypot((left?.x ?? 0) - (right?.x ?? 0), (left?.y ?? 0) - (right?.y ?? 0));

  it('同一份拓扑数据布局两次，节点坐标一致', async () => {
    const first = await layoutForceTopology(directedNodes, directedEdges);
    const second = await layoutForceTopology(directedNodes, directedEdges);
    expect(first).toHaveLength(directedNodes.length);
    expect(Object.keys(positionsById(first)).sort()).toEqual(directedNodes.map((item) => item.id).sort());
    expect(positionsById(first)).toEqual(positionsById(second));
  });

  it('layoutForceTopology 不得使用 Math.random', () => {
    expect(topologyLayoutSource).not.toMatch(/Math\.random/);
  });

  it('用户请求入口和推断下游不会漂到任意层或角落', async () => {
    const result = await layoutForceTopology(directedNodes, directedEdges);
    const byId = new Map(result.map((item) => [item.id, item]));
    const entry = byId.get('user_request:local');
    const storefront = byId.get('storefront');
    const inventory = byId.get('inventory');
    const inferred = byId.get('inferred:local:mysql');
    const ys = result.map((item) => item.y);

    expect(entry?.y).toBe(Math.min(...ys));
    expect(inferred?.y).toBe(Math.max(...ys));
    expect(entry?.y).toBeLessThan(storefront?.y ?? 0);
    expect(storefront?.y).toBeLessThan(byId.get('catalog')?.y ?? 0);
    expect(byId.get('catalog')?.y).toBeLessThan(inventory?.y ?? 0);
    expect(inventory?.y).toBeLessThan(inferred?.y ?? 0);
    expect(distance(entry, storefront)).toBeLessThan(distance(entry, inferred));
    expect(distance(inferred, inventory)).toBeLessThan(distance(inferred, entry));
    expect(topologyCardsOverlap(result)).toBe(false);
    expect(Math.abs((entry?.x ?? 0) - (storefront?.x ?? 0))).toBeLessThan(TOPOLOGY_CANVAS_SIZE.width / 2);
    expect(Math.abs((inferred?.x ?? 0) - (inventory?.x ?? 0))).toBeLessThan(TOPOLOGY_CANVAS_SIZE.width / 2);
  });
});

describe('APM 服务拓扑连线', () => {
  it('层次布局使用折线连接上下层', () => {
    const geometry = buildTopologyEdgeGeometry(
      { x: 100, y: 80, radius: 16 },
      { x: 220, y: 220, radius: 16 },
      false,
      'polyline',
    );

    expect(geometry.path).toMatch(/^M /);
    expect(geometry.path).toContain(' L ');
    expect(geometry.path).toContain(' Q ');
    expect(geometry.startY).toBeLessThan(geometry.endY);
    expect(geometry.labelY).toBeGreaterThan(geometry.startY);
    expect(geometry.labelY).toBeLessThan(geometry.endY);
  });

  it('真实双向依赖绘制为两条分离折线', () => {
    const forward = buildTopologyEdgeGeometry(
      { x: 100, y: 80, radius: 16 },
      { x: 220, y: 220, radius: 16 },
      true,
      'polyline',
    );
    const reverse = buildTopologyEdgeGeometry(
      { x: 220, y: 220, radius: 16 },
      { x: 100, y: 80, radius: 16 },
      true,
      'polyline',
    );

    expect(forward.path).not.toBe(reverse.path);
    expect(forward.controlY).not.toBe(reverse.controlY);
  });

  it('互为反向的曲线连线分离', () => {
    const forward = buildTopologyEdgeGeometry(
      { x: 100, y: 100, radius: 28 },
      { x: 300, y: 100, radius: 28 },
      true,
      'curve',
    );
    const reverse = buildTopologyEdgeGeometry(
      { x: 300, y: 100, radius: 28 },
      { x: 100, y: 100, radius: 28 },
      true,
      'curve',
    );

    expect(forward.path).toContain(' Q ');
    expect(forward.path).not.toBe(reverse.path);
    expect(forward.controlY).toBeGreaterThan(100);
    expect(reverse.controlY).toBeLessThan(100);
  });
});

describe('APM 应用拓扑聚焦', () => {
  it('保留本应用服务及其一跳上下游', () => {
    const graph: ApmTopologyGraph = {
      nodes: [
        { ...node('gateway'), id: 'gateway', service_namespace: 'store' },
        { ...node('checkout'), id: 'checkout', service_namespace: 'shop' },
        { ...node('invoice'), id: 'invoice', service_namespace: 'billing' },
        { ...node('email'), id: 'email', service_namespace: 'notify' },
      ],
      edges: [
        edge('gateway', 'checkout'),
        edge('checkout', 'invoice'),
        edge('invoice', 'email'),
      ],
      sampled_traces: 3,
      truncated: false,
      data_state: 'available',
    };

    const focused = focusApplicationTopology(graph, 'shop');
    expect([...focused.focusNodeIds]).toEqual(['checkout']);
    expect(focused.graph.nodes.map((item) => item.id).sort()).toEqual(['checkout', 'gateway', 'invoice']);
    expect(focused.graph.edges.map((item) => `${item.source}>${item.target}`).sort()).toEqual([
      'checkout>invoice',
      'gateway>checkout',
    ]);
  });

  it('应用聚焦保留本应用已插桩服务的直接推断下游', () => {
    const graph: ApmTopologyGraph = {
      nodes: [
        { ...node('checkout'), id: 'checkout', service_namespace: 'shop' },
        { ...node('mysql'), id: 'inferred:prod:mysql', kind: 'inferred', fold_key: 'mysql' },
      ],
      edges: [edge('checkout', 'inferred:prod:mysql')],
      sampled_traces: 1,
      truncated: false,
      data_state: 'available',
    };
    const focused = focusApplicationTopology(graph, 'shop');
    expect(focused.graph.nodes.map((item) => item.id).sort()).toEqual(['checkout', 'inferred:prod:mysql']);
    expect(focused.graph.edges.map((item) => `${item.source}>${item.target}`)).toEqual(['checkout>inferred:prod:mysql']);
  });

  it('应用聚焦不把一跳邻居的推断下游算进本应用图', () => {
    const graph: ApmTopologyGraph = {
      nodes: [
        { ...node('checkout'), id: 'checkout', service_namespace: 'shop' },
        { ...node('invoice'), id: 'invoice', service_namespace: 'billing' },
        { ...node('mysql'), id: 'inferred:prod:mysql', kind: 'inferred', fold_key: 'mysql' },
      ],
      edges: [edge('checkout', 'invoice'), edge('invoice', 'inferred:prod:mysql')],
      sampled_traces: 1,
      truncated: false,
      data_state: 'available',
    };
    const focused = focusApplicationTopology(graph, 'shop');
    expect(focused.graph.nodes.map((item) => item.id).sort()).toEqual(['checkout', 'invoice']);
    expect(focused.graph.edges.map((item) => `${item.source}>${item.target}`)).toEqual(['checkout>invoice']);
  });

  it('应用聚焦保留连入焦点服务的用户请求入口节点', () => {
    const graph: ApmTopologyGraph = {
      nodes: [
        { ...node('checkout'), id: 'checkout', service_namespace: 'shop' },
        { ...node('user_request'), id: 'user_request:prod', service_namespace: '', kind: 'user_request', health: 'unknown' },
      ],
      edges: [edge('user_request:prod', 'checkout')],
      sampled_traces: 1,
      truncated: false,
      data_state: 'available',
    };
    const focused = focusApplicationTopology(graph, 'shop');
    expect(focused.graph.nodes.map((item) => item.id).sort()).toEqual(['checkout', 'user_request:prod']);
    expect(focused.graph.edges.map((item) => `${item.source}>${item.target}`)).toEqual(['user_request:prod>checkout']);
  });
});

describe('APM 服务拓扑调查过滤', () => {
  it('隔离只保留目标服务的直接入出邻居', () => {
    const isolated = isolateTopologyNeighborhood(demoNodes, demoEdges, 'demo-orders');
    expect(isolated.nodes.map((item) => item.id).sort()).toEqual([
      'demo-inventory',
      'demo-orders',
      'demo-payment',
      'demo-storefront',
    ]);
    expect(isolated.edges.map((item) => `${item.source}>${item.target}`).sort()).toEqual([
      'demo-orders>demo-inventory',
      'demo-orders>demo-payment',
      'demo-storefront>demo-orders',
    ]);
  });

  it('关键字过滤隐藏不匹配的节点和边', () => {
    const filtered = filterTopologyByKeyword(demoNodes, demoEdges, 'payment');
    expect(filtered.nodes.map((item) => item.id)).toEqual(['demo-payment']);
    expect(filtered.edges).toEqual([]);
  });

  it('只看异常只保留失败调用及其两端服务', () => {
    const filtered = filterAnomalousTopology(
      demoNodes,
      [
        { ...edge('demo-storefront', 'demo-catalog'), error_calls: 2 },
        edge('demo-storefront', 'demo-orders'),
        edge('demo-catalog', 'demo-inventory'),
      ],
    );
    expect(filtered.nodes.map((item) => item.id).sort()).toEqual(['demo-catalog', 'demo-storefront']);
    expect(filtered.edges.map((item) => `${item.source}>${item.target}`)).toEqual(['demo-storefront>demo-catalog']);
  });
});

describe('APM 服务拓扑节点标签', () => {
  it('推断节点为角标和健康点预留名称宽度', () => {
    expect(topologyNodeNameWidth(148, false)).toBeGreaterThan(topologyNodeNameWidth(148, true));
    expect(topologyNodeNameWidth(148, true)).toBe(148 - 40 - 22 - 28);
  });

  it('超长服务名在可用宽度内截断并保留省略号', () => {
    expect(truncateTopologyNodeLabel('redis', 70)).toBe('redis');
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70)).toMatch(/^demo-.+…$/);
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70).length).toBeLessThan('demo-payment-gateway'.length);
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70)).not.toBe('demo-payment-gateway');
  });

  it('用户请求入口按内容收缩为胶囊宽度，不超过服务卡片下限', () => {
    const zhWidth = topologyEntryPillWidth('用户请求', '12');
    const enWidth = topologyEntryPillWidth('User requests', '155');
    expect(zhWidth).toBeGreaterThanOrEqual(128);
    expect(zhWidth).toBeLessThan(176);
    expect(enWidth).toBeGreaterThan(zhWidth);
    expect(enWidth).toBeLessThanOrEqual(176);
  });
});
