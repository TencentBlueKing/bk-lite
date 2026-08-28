import React from 'react';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmTopologyEdge, ApmTopologyNode } from '@/app/apm/types';
import ApmTopologyPage from '../page';
import TopologyCanvas from '../topology-canvas';
import { formatTopologyEdgeMetrics } from '@/app/apm/components/metric-format';

const api = {
  getServices: vi.fn(),
  getTopology: vi.fn(),
  getTraces: vi.fn(),
};

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/app/apm/components/apm-route-shell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  ApmSurface: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

const node = (id: string, extras: Partial<ApmTopologyNode> = {}): ApmTopologyNode => ({
  id,
  service_namespace: 'apm-demo-shop',
  service_name: id,
  environment: 'local',
  health: 'healthy',
  sampled_spans: 100,
  error_spans: 0,
  language: id === 'catalog' ? 'python' : 'go',
  request_rate: 8,
  error_rate: 0,
  p95_ms: 42,
  ...extras,
});

const edge = (source: string, target: string): ApmTopologyEdge => ({
  source,
  target,
  health: 'unknown',
  sampled_calls: 153,
  error_calls: 0,
  average_duration_ms: 0,
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
  api.getTraces.mockResolvedValue({
    items: [{
      trace_id: 'abc123',
      started_at: '2026-08-26T00:00:00.000Z',
      duration_ms: 80,
      service_namespace: 'apm-demo-shop',
      service_name: 'catalog',
      environment: 'local',
      instance_id: null,
      status: 'ok',
      root_span_name: 'GET /catalog',
      span_count: 3,
    }],
    next_cursor: null,
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
    expect(result.container.querySelector('[data-topology-layout-pending="true"]')).not.toBeNull();
    expect(result.container.querySelector('[aria-busy="true"]')).not.toBeNull();

    await waitFor(() => {
      expect(edgePairs(result.container)).toEqual(['catalog>inventory', 'storefront>catalog']);
    });
    expect(result.container.querySelector('[data-topology-layout-pending="true"]')).toBeNull();
    result.container.querySelectorAll<SVGPathElement>('g[data-source] > path').forEach((path) => {
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
    const canvas = result.container.querySelector('svg[role="img"]');
    expect(canvas?.querySelectorAll('svg').length).toBeGreaterThan(0);
    expect(canvas?.querySelector('[fill="#3776AB"]')).not.toBeNull();
    expect(canvas?.querySelector('[fill="#00ADD8"]')).not.toBeNull();
    expect(result.container.querySelector('[data-topology-surface]')?.className).toContain('bg-[var(--color-fill-1)]');
    expect(result.container.querySelector('[data-topology-surface]')?.className).not.toContain('[background-size:24px_24px]');
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
      expect(path.getAttribute('marker-end')).toBe('url(#apm-arrow)');
      expect(path.getAttribute('marker-start')).toBeNull();
    });
  });

  it('连线只展示观测调用量，不把缺失的边级错误画成红色', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas edges={[edge('catalog', 'inventory')]} keyword="" nodes={nodes.slice(0, 2)} zoom={1} />,
    );

    await waitFor(() => expect(edgePairs(result.container)).toEqual(['catalog>inventory']));
    expect(screen.getByText(formatTopologyEdgeMetrics(edge('catalog', 'inventory')))).not.toBeNull();
    const path = result.container.querySelector<SVGPathElement>('g[data-source] > path');
    expect(path?.getAttribute('stroke')).not.toBe('var(--color-fail)');
    expect(path?.getAttribute('marker-end')).toBe('url(#apm-arrow)');
  });

  it('严重节点用状态点表达健康度，不把服务名涂成红色', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas
        edges={[edge('catalog', 'inventory')]}
        keyword=""
        nodes={[node('catalog', { health: 'critical', error_rate: 0.2 }), node('inventory', { health: 'warning', error_rate: 0.02 })]}
        zoom={1}
      />,
    );

    await waitFor(() => expect(result.container.querySelector('[data-node-id="catalog"]')).not.toBeNull());
    const name = Array.from(result.container.querySelectorAll('text')).find((item) => item.textContent === 'catalog');
    expect(name?.getAttribute('fill')).toBe('var(--color-text-1)');
    expect(result.container.querySelector('[data-node-id="catalog"] rect')?.getAttribute('stroke')).toBe('var(--color-border)');
    expect(result.container.querySelector('[data-node-id="catalog"] circle[fill="var(--color-fail)"]')).not.toBeNull();
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
    expect(screen.getByRole('complementary', { name: '拓扑调查栏' })).not.toBeNull();
  });

  it('点选节点停在图上打开调查栏并加载样本 Trace', async () => {
    renderWithApmIntl(<ApmTopologyPage />);
    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    fireEvent.click(screen.getByRole('button', { name: /catalog/ }));
    expect(await screen.findByRole('button', { name: '隔离一跳' })).not.toBeNull();
    expect(screen.getByRole('link', { name: '更多调用链' })).not.toBeNull();
    await waitFor(() => expect(api.getTraces).toHaveBeenCalled());
    expect(await screen.findByText('GET /catalog')).not.toBeNull();
  });

  it('隔离一跳后只保留目标服务的直接邻居', async () => {
    const result = renderWithApmIntl(<ApmTopologyPage />);
    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    fireEvent.click(screen.getByRole('button', { name: /storefront/ }));
    fireEvent.click(await screen.findByRole('button', { name: '隔离一跳' }));
    await waitFor(() => {
      expect(result.container.querySelector('[data-node-id="inventory"]')).toBeNull();
    });
    expect(result.container.querySelector('[data-node-id="storefront"]')).not.toBeNull();
    expect(result.container.querySelector('[data-node-id="catalog"]')).not.toBeNull();
    expect(screen.getByText('正在隔离查看一个服务及其直接依赖。')).not.toBeNull();
  });

  it('推断节点展示角标，调查栏隐藏服务详情并列出样本 Client Span', async () => {
    api.getTopology.mockResolvedValue({
      nodes: [
        node('catalog'),
        node('mysql', {
          kind: 'inferred',
          fold_key: 'mysql',
          inferred_system: 'mysql',
          language: '',
          request_rate: null,
          peer_address: 'db.internal:3306, 10.0.0.2:3306',
          db_name: 'shop',
          sample_traces: [{
            trace_id: 'mysql-trace',
            span_id: 'span-1',
            span_name: 'SELECT orders',
            started_at: '2026-08-26T00:00:00.000Z',
            duration_ms: 12,
            status: 'ok',
            caller_service_name: 'catalog',
            peer_address: 'db.internal:3306',
            db_name: 'shop',
          }, {
            trace_id: 'mysql-trace-2',
            span_id: 'span-2',
            span_name: 'SELECT inventory',
            started_at: '2026-08-26T00:00:01.000Z',
            duration_ms: 9,
            status: 'ok',
            caller_service_name: 'catalog',
            peer_address: '10.0.0.2:3306',
            db_name: 'shop',
          }],
        }),
      ],
      edges: [edge('catalog', 'mysql')],
      sampled_traces: 1,
      truncated: false,
      data_state: 'available',
    });
    const result = renderWithApmIntl(<ApmTopologyPage />);
    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    await waitFor(() => expect(result.container.querySelector('[data-node-kind="inferred"]')).not.toBeNull());
    expect(result.container.querySelector('[data-node-kind="inferred"] [data-service-icon="mysql"]')).not.toBeNull();
    expect(result.container.querySelector('[data-node-kind="inferred"] image')?.getAttribute('href')).toContain('cc-mysql_MySQL');
    expect(screen.getAllByText('推断').length).toBeGreaterThan(0);
    fireEvent.click(result.container.querySelector('[data-node-id="mysql"]') as Element);
    expect(await screen.findByText('样本 Client Span')).not.toBeNull();
    expect(result.container.querySelector('[data-peer-address="db.internal:3306, 10.0.0.2:3306"]')).not.toBeNull();
    expect(screen.getByText('db.internal:3306, 10.0.0.2:3306')).not.toBeNull();
    expect(screen.getAllByText('shop').length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /SELECT orders/ }).textContent).toContain('db.internal:3306');
    expect(screen.getByRole('link', { name: /SELECT inventory/ }).textContent).toContain('10.0.0.2:3306');
    expect(screen.queryByRole('link', { name: '服务详情' })).toBeNull();
    expect(screen.getByRole('button', { name: '隔离一跳' })).not.toBeNull();
  });

  it('推断网关节点使用网关图标，长服务名在推断角标前截断', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas
        edges={[edge('catalog', 'demo-payment-gateway')]}
        keyword=""
        nodes={[
          node('catalog'),
          node('demo-payment-gateway', {
            kind: 'inferred',
            fold_key: 'demo-payment-gateway',
            inferred_system: 'http',
            language: '',
            service_name: 'demo-payment-gateway',
          }),
        ]}
        zoom={1}
      />,
    );

    await waitFor(() => expect(result.container.querySelector('[data-node-id="demo-payment-gateway"]')).not.toBeNull());
    const inferred = result.container.querySelector('[data-node-id="demo-payment-gateway"]') as SVGGElement;
    expect(inferred.querySelector('[data-service-icon="gateway"]')).not.toBeNull();
    expect(inferred.querySelector('image')?.getAttribute('href')).toContain('cc-nginx_Nginx');
    expect(inferred.textContent).not.toContain('</>');
    const label = inferred.querySelector('[data-node-label]');
    expect(label?.textContent).toMatch(/…$/);
    expect(label?.textContent).not.toBe('demo-payment-gateway');
    expect(screen.getAllByText('推断').length).toBeGreaterThan(0);
  });

  it('用户请求入口节点使用用户图标、本地化标签与虚线入口边', async () => {
    const result = renderWithApmIntl(
      <TopologyCanvas
        edges={[edge('user_request:local', 'storefront'), edge('storefront', 'catalog')]}
        keyword=""
        nodes={[
          node('storefront'),
          node('catalog'),
          node('user_request:local', {
            service_name: 'user_request',
            service_namespace: '',
            kind: 'user_request',
            health: 'unknown',
            language: '',
            request_rate: null,
            error_rate: null,
            p95_ms: null,
            sampled_spans: 12,
          }),
        ]}
        zoom={1}
      />,
    );

    await waitFor(() => expect(result.container.querySelector('[data-node-kind="user_request"]')).not.toBeNull());
    const entry = result.container.querySelector('[data-node-kind="user_request"]') as SVGGElement;
    expect(entry.querySelector('[data-service-icon="user-request"]')).not.toBeNull();
    expect(entry.querySelector('[data-node-label]')?.textContent).toBe('用户请求');
    expect(entry.textContent).toContain('观测请求 12 次');
    expect(entry.textContent).not.toContain('无数据');
    const entryEdge = result.container.querySelector('g[data-source="user_request:local"] > path');
    expect(entryEdge?.getAttribute('stroke-dasharray')).toBe('5 4');
    const serviceEdge = result.container.querySelector('g[data-source="storefront"] > path');
    expect(serviceEdge?.getAttribute('stroke-dasharray')).toBeNull();
  });

  it('仅错误请求与只看异常可同时存在且语义不同', async () => {
    renderWithApmIntl(<ApmTopologyPage />);
    await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    expect(screen.getByRole('button', { name: '只看异常' })).not.toBeNull();
    expect(screen.getByRole('combobox', { name: '按请求状态切片' })).not.toBeNull();
    expect(screen.getByRole('textbox', { name: '按操作名切片' })).not.toBeNull();
    const callsBeforeAnomaly = api.getTopology.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '只看异常' }));
    expect(api.getTopology.mock.calls.length).toBe(callsBeforeAnomaly);
  });

  it('缩放按钮改变画布视图而不离开页面', async () => {
    renderWithApmIntl(<ApmTopologyPage />);
    const svg = await screen.findByRole('img', { name: 'APM 服务调用拓扑' });
    expect(svg.getAttribute('data-topology-scale')).toBe('1.00');
    fireEvent.click(screen.getByRole('button', { name: '放大拓扑' }));
    expect(svg.getAttribute('data-topology-scale')).not.toBe('1.00');
  });
});
