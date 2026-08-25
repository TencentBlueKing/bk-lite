import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';
import ApmTopologyPage, { TopologyCanvas } from '../page';

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

const edge = (source: string, target: string): ApmTopologyEdge => ({
  source,
  target,
  health: 'healthy',
  sampled_calls: 10,
  error_calls: 0,
  average_duration_ms: 12,
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
    expect(screen.getByText('Py')).not.toBeNull();
    expect(screen.getAllByText('Go')).toHaveLength(2);
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
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow-healthy)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
  });

  it('页面只提供自动分层拓扑，不展示布局选择器', async () => {
    renderWithApmIntl(<ApmTopologyPage />);

    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    expect(screen.queryByRole('radiogroup', { name: '拓扑布局' })).toBeNull();
    expect(screen.queryByRole('radio', { name: '环形' })).toBeNull();
  });

  it('把健康图例叠在图形画布上，列表视图不再单独占一张卡片', async () => {
    renderWithApmIntl(<ApmTopologyPage />);

    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    expect(screen.getByRole('list', { name: '节点健康图例' })).not.toBeNull();

    const viewToggle = screen.getByRole('radiogroup', { name: '拓扑视图' });
    expect(viewToggle.className).toMatch(/w-32/);
    expect(viewToggle.classList.contains('ant-segmented-block')).toBe(true);
    expect(screen.getByRole('radio', { name: '图形' })).not.toBeNull();
    screen.getByRole('radio', { name: '列表' }).click();
    expect(screen.queryByRole('list', { name: '节点健康图例' })).toBeNull();
    expect(screen.getByRole('columnheader', { name: '健康' })).not.toBeNull();
  });
});
