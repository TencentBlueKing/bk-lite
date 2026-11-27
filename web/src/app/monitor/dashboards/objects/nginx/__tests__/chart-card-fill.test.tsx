import { cleanup, render, type RenderResult } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildNginxDashboard } from '../layered/model';
import ConnectionsPane from '../layered/connections-pane';
import { NGINX_SPAN } from '../layered/nginx-card';
import SitesPane from '../layered/sites-pane';
import UpstreamPane from '../layered/upstream-pane';
import { NGINX_CARD_QUERIES, type NginxQueryPhase } from '../layered/query-phase';

vi.mock('../layered/nginx-plot', () => ({
  NginxPlot: () => <div data-nginx-plot="" />
}));

vi.mock('../../../shared/widgets/useECharts', () => ({
  useECharts: () => ({ containerRef: () => undefined, getInstance: () => null })
}));

vi.mock('../layered/nginx-hint', () => ({
  NginxHint: () => null
}));

afterEach(() => {
  cleanup();
});

const now = 1_700_000_000;

const readyPhases = (): Record<string, NginxQueryPhase> => ({
  ...Object.fromEntries(Object.values(NGINX_CARD_QUERIES).flat().map((key) => [key, 'ready' as const]))
});

const model = buildNginxDashboard({
  onboarded: true,
  nowSeconds: now,
  data: { range: {}, instant: { serverCap: [], upstreamCap: [] } }
});

const classNames = (node: Element | null | undefined) => (node?.getAttribute('class') ?? '').split(/\s+/).filter(Boolean);

const expectFill = (node: Element | null | undefined) => {
  const names = classNames(node);
  expect(names).toContain('w-full');
  expect(names).toContain('h-full');
};

const SPAN_CLASS: Record<string, string> = {
  '1/4': 'min-[1100px]:col-span-3',
  '1/3': 'min-[1100px]:col-span-4',
  '1/2': 'min-[1100px]:col-span-6',
  '3/4': 'min-[1100px]:col-span-9'
};

const expectSpanCardsFill = (view: RenderResult, expected: number) => {
  const cards = [
    ...view.container.querySelectorAll('[data-nginx-width] [data-nginx-chart], [data-nginx-width] [data-nginx-pie], [data-nginx-width] [data-nginx-rank]')
  ];
  expect(cards).toHaveLength(expected);
  cards.forEach((card) => {
    expectFill(card);
    const span = card.parentElement;
    const width = span?.getAttribute('data-nginx-width') ?? '';
    expect(span?.getAttribute('data-nginx-width')).toBeTruthy();
    expect(classNames(span)).toEqual(expect.arrayContaining(['w-full', 'flex', SPAN_CLASS[width]]));
  });
};

describe('nginx chart cards fill declared spans', () => {
  it('keeps the declared column spans and stretches each span to the cell', () => {
    expect(NGINX_SPAN.quarter).toContain('w-full');
    expect(NGINX_SPAN.quarter).toContain('min-[1100px]:col-span-3');
    expect(NGINX_SPAN.third).toContain('w-full');
    expect(NGINX_SPAN.third).toContain('min-[1100px]:col-span-4');
    expect(NGINX_SPAN.half).toContain('w-full');
    expect(NGINX_SPAN.half).toContain('min-[1100px]:col-span-6');
    expect(NGINX_SPAN.threeQuarter).toContain('w-full');
    expect(NGINX_SPAN.threeQuarter).toContain('min-[1100px]:col-span-9');
  });

  it('fills connection composition and trend cards', () => {
    const view = render(
      <ConnectionsPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expectSpanCardsFill(view, 4);
    expect(view.container.querySelector('[data-nginx-pie="连接构成"]')?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="连接占比趋势"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="连接数"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="丢弃连接速率"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
  });

  it('fills site status, traffic, and rank cards', () => {
    const view = render(
      <SitesPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expectSpanCardsFill(view, 6);
    expect(view.container.querySelector('[data-nginx-chart="状态码分布"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-pie="状态码构成"]')?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="入站与出站流量"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="平均处理时间趋势"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="站点请求速率"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-rank="站点请求排行"]')?.closest('[data-nginx-width="1/2"]')).toBeTruthy();
  });

  it('fills upstream trend and status cards', () => {
    const view = render(
      <UpstreamPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expectSpanCardsFill(view, 5);
    expect(view.container.querySelectorAll('[data-nginx-width="1/3"] [data-nginx-chart]')).toHaveLength(3);
    ['上游请求速率', '响应时间', '请求处理时间'].forEach((title) => {
      expect(view.container.querySelector(`[data-nginx-chart="${title}"]`)?.closest('[data-nginx-width="1/3"]')).toBeTruthy();
    });
    expect(view.container.querySelector('[data-nginx-chart="上游状态码分布"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-pie="上游状态码构成"]')?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
  });
});
