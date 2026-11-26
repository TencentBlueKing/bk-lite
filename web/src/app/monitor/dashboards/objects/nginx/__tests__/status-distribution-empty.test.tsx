import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildNginxDashboard, type RangeSeries } from '../layered/model';
import SitesPane from '../layered/sites-pane';
import UpstreamPane from '../layered/upstream-pane';
import { NGINX_CARD_QUERIES, type NginxQueryPhase } from '../layered/query-phase';

vi.mock('../layered/nginx-plot', () => ({
  NginxPlot: () => <div data-nginx-plot="" />
}));

vi.mock('../layered/nginx-hint', () => ({
  NginxHint: () => null
}));

afterEach(() => {
  cleanup();
});

const now = 1_700_000_000;

const readyPhases = (): Record<string, NginxQueryPhase> => Object.fromEntries(
  Object.values(NGINX_CARD_QUERIES).flat().map((key) => [key, 'ready' as const])
);

const series = (
  name: string,
  labels: Record<string, string>,
  points: { time: number; value: number }[]
): RangeSeries => ({ name, labels, points });

const flatSteps = (name: string, labels: Record<string, string>) => series(name, labels, [
  { time: now - 120, value: 0 },
  { time: now - 60, value: 0 },
  { time: now, value: 0 }
]);

const quietDashboard = (totals: 'zero' | 'missing') => buildNginxDashboard({
  onboarded: true,
  nowSeconds: now,
  intervalSeconds: 60,
  data: {
    range: {
      starStatusStep: [flatSteps('nginx_vts_server_response_2xx_count', { code: '2xx', zone: '*' })],
      upStatusStep: [flatSteps('nginx_vts_upstream_response', { code: '2xx', upstream: 'backend' })]
    },
    instant: {
      serverCap: [{ labels: {}, value: 1 }],
      upstreamCap: [{ labels: {}, value: 1 }],
      ...(totals === 'zero' ? {
        starWindowRequests: [{ labels: { zone: '*' }, value: 0 }],
        upWindowRequests: [{ labels: {}, value: 0 }]
      } : {})
    }
  }
});

const liveDashboard = () => buildNginxDashboard({
  onboarded: true,
  nowSeconds: now,
  intervalSeconds: 60,
  data: {
    range: {
      starStatusStep: [series('nginx_vts_server_response_2xx_count', { code: '2xx', zone: '*' }, [
        { time: now - 60, value: 4 },
        { time: now, value: 6 }
      ])],
      upStatusStep: [series('nginx_vts_upstream_response', { code: '5xx', upstream: 'backend' }, [
        { time: now - 60, value: 1 },
        { time: now, value: 2 }
      ])]
    },
    instant: {
      serverCap: [{ labels: {}, value: 1 }],
      upstreamCap: [{ labels: {}, value: 1 }],
      starWindowRequests: [{ labels: { zone: '*' }, value: 10 }],
      starWindowStatus: [{ labels: { zone: '*', code: '2xx' }, value: 10 }],
      upWindowRequests: [{ labels: {}, value: 8 }],
      upWindow5xx: [{ labels: {}, value: 2 }],
      upWindowStatus: [{ labels: { code: '5xx' }, value: 2 }]
    }
  }
});

const chartOf = (container: HTMLElement, title: string) => container.querySelector(`[data-nginx-chart="${title}"]`);

const renderSites = (
  model: ReturnType<typeof buildNginxDashboard>,
  phases: Record<string, NginxQueryPhase> = readyPhases(),
  onRetry: (keys: readonly string[]) => void = () => undefined
) => render(
  <SitesPane model={model} phases={phases} emptyText="暂无数据" onRetry={onRetry} onRetryFailed={() => undefined} />
);

const renderUpstream = (
  model: ReturnType<typeof buildNginxDashboard>,
  phases: Record<string, NginxQueryPhase> = readyPhases(),
  onRetry: (keys: readonly string[]) => void = () => undefined
) => render(
  <UpstreamPane model={model} phases={phases} emptyText="暂无数据" onRetry={onRetry} onRetryFailed={() => undefined} />
);

describe('status distribution empty window', () => {
  it('shows 暂无数据 instead of an empty-axis bar when the window has no requests', () => {
    for (const totals of ['zero', 'missing'] as const) {
      const model = quietDashboard(totals);
      expect(model.board.windowRequests === '暂无数据' || model.board.windowRequests === '0').toBe(true);
      expect(model.board.up5xx).toBe('暂无数据');
      expect(model.board.statusSteps.some((item) => item.points.length > 0)).toBe(true);
      expect(model.board.upstreamStatusSteps.some((item) => item.points.length > 0)).toBe(true);

      const sites = renderSites(model);
      const siteChart = chartOf(sites.container, '状态码分布');
      expect(siteChart?.textContent).toContain('暂无数据');
      expect(siteChart?.querySelector('[data-nginx-plot]')).toBeNull();
      expect(siteChart?.textContent).not.toContain('加载失败');
      expect(sites.container.querySelector('[data-nginx-pie="状态码构成"] [data-nginx-pie-shape]')).toBeNull();
      cleanup();

      const upstream = renderUpstream(model);
      const upstreamChart = chartOf(upstream.container, '上游状态码分布');
      expect(upstreamChart?.textContent).toContain('暂无数据');
      expect(upstreamChart?.querySelector('[data-nginx-plot]')).toBeNull();
      expect(upstreamChart?.textContent).not.toContain('加载失败');
      expect(upstream.container.querySelector('[data-nginx-pie="上游状态码构成"] [data-nginx-pie-shape]')).toBeNull();
      cleanup();
    }
  });

  it('still draws the status bars when the window has real counts', () => {
    const model = liveDashboard();
    expect(model.board.windowRequests).not.toBe('暂无数据');
    expect(model.board.windowRequests).not.toBe('0');
    expect(model.board.up5xx).not.toBe('暂无数据');
    expect(model.board.statusSteps.some((item) => item.points.some((point) => point.value > 0))).toBe(true);
    expect(model.board.upstreamStatusSteps.some((item) => item.points.some((point) => point.value > 0))).toBe(true);

    const sites = renderSites(model);
    const siteChart = chartOf(sites.container, '状态码分布');
    expect(siteChart?.querySelector('[data-nginx-plot]')).toBeTruthy();
    expect(siteChart?.textContent).not.toContain('暂无数据');
    expect(sites.container.querySelector('[data-nginx-pie="状态码构成"] [data-nginx-pie-shape]')).toBeTruthy();
    cleanup();

    const upstream = renderUpstream(model);
    const upstreamChart = chartOf(upstream.container, '上游状态码分布');
    expect(upstreamChart?.querySelector('[data-nginx-plot]')).toBeTruthy();
    expect(upstreamChart?.textContent).not.toContain('暂无数据');
    expect(upstream.container.querySelector('[data-nginx-pie="上游状态码构成"] [data-nginx-pie-shape]')).toBeTruthy();
  });

  it('keeps 加载失败 and retry when the status query failed', () => {
    const model = quietDashboard('zero');
    const siteRetried: string[][] = [];
    const sitePhases = readyPhases();
    NGINX_CARD_QUERIES.sitesStatus.forEach((key) => {
      sitePhases[key] = 'error';
    });
    const sites = renderSites(model, sitePhases, (keys) => {
      siteRetried.push([...keys]);
    });
    const siteChart = chartOf(sites.container, '状态码分布');
    expect(siteChart?.textContent).toContain('加载失败');
    expect(siteChart?.textContent).toContain('重试');
    expect(siteChart?.textContent).not.toContain('暂无数据');
    expect(siteChart?.querySelector('[data-nginx-plot]')).toBeNull();
    siteChart?.querySelector('button')?.click();
    expect(siteRetried).toEqual([[...NGINX_CARD_QUERIES.sitesStatus]]);
    cleanup();

    const upstreamRetried: string[][] = [];
    const upstreamPhases = readyPhases();
    NGINX_CARD_QUERIES.upstreamStatus.forEach((key) => {
      upstreamPhases[key] = 'error';
    });
    const upstream = renderUpstream(model, upstreamPhases, (keys) => {
      upstreamRetried.push([...keys]);
    });
    const upstreamChart = chartOf(upstream.container, '上游状态码分布');
    expect(upstreamChart?.textContent).toContain('加载失败');
    expect(upstreamChart?.textContent).toContain('重试');
    expect(upstreamChart?.textContent).not.toContain('暂无数据');
    expect(upstreamChart?.querySelector('[data-nginx-plot]')).toBeNull();
    upstreamChart?.querySelector('button')?.click();
    expect(upstreamRetried).toEqual([[...NGINX_CARD_QUERIES.upstreamStatus]]);
  });
});
