import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';
import ApmTopologyPage from '../page';
import TopologyCanvas from '../topology-canvas';
import { formatTopologyEdgeMetrics } from '@/app/apm/components/metric-format';

const api = {
  getServices: vi.fn(),
  getTopology: vi.fn(),
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

const node = (id: string): ApmTopologyNode => ({
  id,
  service_namespace: 'apm-demo-shop',
  service_name: id,
  environment: 'local',
  health: 'healthy',
  sampled_spans: 100,
  error_spans: 0,
  language: id === 'catalog' ? 'python' : 'go',
});

const edge = (source: string, target: string, errorCalls = 0): ApmTopologyEdge => ({
  source,
  target,
  health: errorCalls > 0 ? 'critical' : 'healthy',
  sampled_calls: 153,
  error_calls: errorCalls,
  average_duration_ms: 0.32,
});

const nodes = [node('catalog'), node('inventory'), node('storefront')];
const edges = [edge('catalog', 'inventory'), edge('storefront', 'catalog')];

const edgePairs = (container: HTMLElement) => Array.from(
  container.querySelectorAll<SVGGElement>('g[data-source][data-target]'),
).map((item) => `${item.dataset.source}>${item.dataset.target}`).sort();

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  api.getServices.mockResolvedValue([]);
  api.getTopology.mockResolvedValue({
    nodes,
    edges,
    sampled_traces: 20,
    truncated: false,
    data_state: 'available',
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('APM 服务拓扑画布', () => {
  it('自动分层布局保持依赖方向和箭头端点', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas edges={edges} keyword="" nodes={nodes} zoom={1} />,
    );

    await waitFor(() => {
      expect(edgePairs(result.container)).toEqual(['catalog>inventory', 'storefront>catalog']);
    });
    result.container.querySelectorAll<SVGPathElement>('g[data-source] > path').forEach((path) => {
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow-healthy)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
    const canvas = result.container.querySelector('svg[role="img"]');
    expect(canvas?.querySelectorAll('svg').length).toBeGreaterThan(0);
    expect(canvas?.querySelector('[fill="#3776AB"]')).not.toBeNull();
    expect(canvas?.querySelector('[fill="#00ADD8"]')).not.toBeNull();
    expect(result.container.querySelector('[data-topology-surface]')?.className).toContain('[background-size:24px_24px]');
    expect(screen.queryByText('Py')).toBeNull();
    expect(screen.queryByText('Go')).toBeNull();
  });

  it('双向调用使用两条分离曲线且每条只有终点箭头', async () => {
    const reciprocalEdges = [edge('catalog', 'inventory'), edge('inventory', 'catalog')];
    const result = renderWithApmIntl(
      <TopologyCanvas edges={reciprocalEdges} keyword="" nodes={nodes.slice(0, 2)} zoom={1} />,
    );

    await waitFor(() => expect(edgePairs(result.container)).toEqual(['catalog>inventory', 'inventory>catalog']));
    const paths = Array.from(result.container.querySelectorAll<SVGPathElement>('g[data-source] > path'));
    expect(paths).toHaveLength(2);
    expect(new Set(paths.map((path) => path.getAttribute('d'))).size).toBe(2);
    paths.forEach((path) => {
      expect(path.getAttribute('d')).toContain(' L ');
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow-healthy)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
  });

  it('连线展示调用数、平均耗时和错误数，有错误时连线为红色', async () => {
    const errorEdge = edge('catalog', 'inventory', 1);
    const result = renderWithApmIntl(
      <TopologyCanvas edges={[errorEdge]} keyword="" nodes={nodes.slice(0, 2)} zoom={1} />,
    );

    await waitFor(() => expect(edgePairs(result.container)).toEqual(['catalog>inventory']));
    expect(screen.getByText(formatTopologyEdgeMetrics(errorEdge))).not.toBeNull();
    const path = result.container.querySelector<SVGPathElement>('g[data-source] > path');
    expect(path?.getAttribute('stroke')).toBe('var(--color-fail)');
    expect(path?.getAttribute('marker-end')).toBe('url(#apm-arrow-critical)');
  });

  it('页面提供层次/力导向布局，并以总调用数替代观测 Trace', async () => {
    renderWithApmIntl(<ApmTopologyPage />);

    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    expect(screen.getByRole('radiogroup', { name: '拓扑布局' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: '层次' })).not.toBeNull();
    expect(screen.getByRole('radio', { name: '力导向' })).not.toBeNull();
    expect(screen.queryByRole('radio', { name: '图形' })).toBeNull();
    expect(screen.queryByRole('radio', { name: '列表' })).toBeNull();
    expect(screen.getByText('总调用数')).not.toBeNull();
    expect(screen.queryByText('观测 Trace')).toBeNull();
    expect(screen.getByRole('list', { name: '节点健康图例' })).not.toBeNull();
  });
});
