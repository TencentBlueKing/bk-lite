import { describe, expect, it } from 'vitest';
import type { ApmTopologyEdge, ApmTopologyGraph, ApmTopologyNode } from '@/app/apm/types';
import {
  buildTopologyEdgeGeometry,
  filterTopologyByKeyword,
  focusApplicationTopology,
  isolateTopologyNeighborhood,
  layoutForceTopology,
  layoutLayeredTopology,
  topologyNodeNameWidth,
  truncateTopologyNodeLabel,
} from '../topology-layout';

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

  it('力导向连线使用分离曲线', () => {
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

  it('应用聚焦不把推断下游算进一跳邻居', () => {
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
    expect(focused.graph.nodes.map((item) => item.id)).toEqual(['checkout']);
    expect(focused.graph.edges).toEqual([]);
  });
});

describe('APM 服务拓扑力导向布局', () => {
  it('为每个节点生成画布内坐标', async () => {
    const result = await layoutForceTopology(demoNodes, demoEdges);
    expect(result).toHaveLength(demoNodes.length);
    expect(new Set(result.map((item) => item.id)).size).toBe(demoNodes.length);
    result.forEach((item) => {
      expect(item.x).toBeGreaterThanOrEqual(90);
      expect(item.x).toBeLessThanOrEqual(950);
      expect(item.y).toBeGreaterThanOrEqual(90);
      expect(item.y).toBeLessThanOrEqual(540);
    });
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
});

describe('APM 服务拓扑节点标签', () => {
  it('推断节点为角标和健康点预留名称宽度', () => {
    expect(topologyNodeNameWidth(148, false)).toBeGreaterThan(topologyNodeNameWidth(148, true));
    expect(topologyNodeNameWidth(148, true)).toBe(148 - 30 - 22 - 28);
  });

  it('超长服务名在可用宽度内截断并保留省略号', () => {
    expect(truncateTopologyNodeLabel('redis', 70)).toBe('redis');
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70)).toMatch(/^demo-.+…$/);
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70).length).toBeLessThan('demo-payment-gateway'.length);
    expect(truncateTopologyNodeLabel('demo-payment-gateway', 70)).not.toBe('demo-payment-gateway');
  });
});
