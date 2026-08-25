import { describe, expect, it } from 'vitest';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';
import {
  buildTopologyEdgeGeometry,
  layoutLayeredTopology,
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
  it('根据真实依赖关系分层，而不是按节点名称排成一行', async () => {
    const result = await layoutLayeredTopology(demoNodes, demoEdges);
    const byId = new Map(result.map((item) => [item.id, item]));

    expect(byId.get('demo-storefront')?.x).toBeLessThan(byId.get('demo-catalog')?.x ?? 0);
    expect(byId.get('demo-storefront')?.x).toBeLessThan(byId.get('demo-orders')?.x ?? 0);
    expect(byId.get('demo-catalog')?.x).toBeLessThan(byId.get('demo-inventory')?.x ?? 0);
    expect(byId.get('demo-orders')?.x).toBeLessThan(byId.get('demo-payment')?.x ?? 0);
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
  it('单向依赖只在目标端生成箭头路径', () => {
    const geometry = buildTopologyEdgeGeometry(
      { x: 100, y: 100, radius: 28 },
      { x: 300, y: 100, radius: 28 },
      false,
    );

    expect(geometry.path).toMatch(/^M /);
    expect(geometry.path).toContain(' Q ');
    expect(geometry.startX).toBeLessThan(geometry.endX);
    expect(geometry.labelX).toBeGreaterThan(geometry.startX);
    expect(geometry.labelX).toBeLessThan(geometry.endX);
  });

  it('真实双向依赖绘制为两条分离曲线', () => {
    const forward = buildTopologyEdgeGeometry(
      { x: 100, y: 100, radius: 28 },
      { x: 300, y: 100, radius: 28 },
      true,
    );
    const reverse = buildTopologyEdgeGeometry(
      { x: 300, y: 100, radius: 28 },
      { x: 100, y: 100, radius: 28 },
      true,
    );

    expect(forward.path).not.toBe(reverse.path);
    expect(forward.controlY).toBeGreaterThan(100);
    expect(reverse.controlY).toBeLessThan(100);
    expect(forward.labelY).toBeGreaterThan(100);
    expect(reverse.labelY).toBeLessThan(100);
  });
});
