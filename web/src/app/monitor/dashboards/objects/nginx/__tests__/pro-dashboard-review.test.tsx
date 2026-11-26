import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NginxFocusTile } from '../layered/nginx-card';
import { buildNginxDashboard, type RangeSeries } from '../layered/model';
import OverviewPane from '../layered/overview-pane';
import { focusCardQueries, NGINX_CARD_QUERIES, phaseOf } from '../layered/query-phase';
import SitesPane from '../layered/sites-pane';
import UpstreamPane from '../layered/upstream-pane';

vi.mock('../../../shared/use-linked-host', () => ({
  useLinkedHost: () => ({ host: null, href: '', pending: false })
}));

vi.mock('../../../shared/widgets/linked-host-segment', () => ({
  LinkedHostSegment: () => <div data-linked-host="" />
}));

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

const readyPhases = Object.fromEntries(
  Object.values(NGINX_CARD_QUERIES).flat().map((key) => [key, 'ready' as const])
);

const series = (
  name: string,
  labels: Record<string, string>,
  points: { time: number; value: number }[]
): RangeSeries => ({ name, labels, points });

describe('upstream request-rate spark', () => {
  it('sums every upstream group instead of drawing the first one', () => {
    const model = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      intervalSeconds: 60,
      data: {
        range: {
          upRequestSum: [
            series('nginx_vts_upstream_requests', { upstream: 'alpha' }, [
              { time: 1, value: 0 },
              { time: 2, value: 4 }
            ]),
            series('nginx_vts_upstream_requests', { upstream: 'beta' }, [
              { time: 1, value: 4 },
              { time: 2, value: 0 }
            ])
          ]
        },
        instant: {
          upstreamFresh: [
            { labels: { metric: 'nginx_vts_upstream_requests', upstream: 'alpha' }, value: now },
            { labels: { metric: 'nginx_vts_upstream_requests', upstream: 'beta' }, value: now }
          ],
          upstreamCap: [{ labels: { metric: 'nginx_vts_upstream_requests' }, value: 1 }]
        }
      }
    });

    expect(model.board.upRate).toBe('4');
    expect(model.board.upstreamRateSpark).toEqual([
      { time: 1, value: 4 },
      { time: 2, value: 4 }
    ]);
    expect(model.board.upstreamGroupTrend[0]?.points).toEqual([
      { time: 1, value: 0 },
      { time: 2, value: 4 }
    ]);

    const view = render(
      <UpstreamPane
        model={model}
        phases={readyPhases}
        emptyText="暂无数据"
        onRetry={() => undefined}
        onRetryFailed={() => undefined}
      />
    );
    expect(view.container.querySelector('[data-nginx-tile="上游请求速率"] [data-nginx-spark]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-chart="上游请求速率"]')).toBeTruthy();
  });
});

describe('vts probe failure', () => {
  it('keeps the tabs when the probe fails and treats a successful empty result as stub', () => {
    const failed = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: { range: {}, instant: {} },
      capabilityPhases: { serverCap: 'error', upstreamCap: 'error' }
    });
    expect(failed.tabs).toEqual({ sites: true, upstream: true });
    expect(failed.board.focusThirdTitle).toBe('站点与上游异常');

    const stub = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: { range: {}, instant: { serverCap: [], upstreamCap: [] } },
      capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
    });
    expect(stub.tabs).toEqual({ sites: false, upstream: false });
    expect(stub.board.focusThirdTitle).toBe('连接结构');

    const present = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: {
        range: {},
        instant: {
          serverCap: [{ labels: { metric: 'nginx_vts_server_requests' }, value: 1 }],
          upstreamCap: []
        }
      },
      capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
    });
    expect(present.tabs).toEqual({ sites: true, upstream: false });
  });

  it('shows 加载失败 and retry on the anomaly card when the probe failed', () => {
    const model = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: { range: {}, instant: {} },
      capabilityPhases: { serverCap: 'error' }
    });
    const phases = Object.fromEntries(focusCardQueries(model.board.focusThirdTab).map((key) => [key, 'ready' as const]));
    phases.serverCap = 'error';
    expect(phaseOf(focusCardQueries('sites'), phases)).toBe('error');

    const retried: string[][] = [];
    const view = render(
      <OverviewPane
        model={model}
        phases={phases}
        alertPhase="error"
        emptyText="暂无数据"
        alertCount={0}
        alertEvents={[]}
        nodeId=""
        ip=""
        onOpenAlerts={() => undefined}
        onFocusAlert={() => undefined}
        onOpen={() => undefined}
        onRetry={(keys) => retried.push([...keys])}
        onRetryFailed={() => undefined}
        onRetryAlerts={() => undefined}
      />
    );
    const card = view.container.querySelector('[data-nginx-focus="站点与上游异常"]');
    expect(card?.textContent).toContain('加载失败');
    expect(card?.textContent).toContain('重试');
    card?.querySelector('button')?.click();
    expect(retried[0]).toContain('serverCap');

    const sites = render(
      <SitesPane
        model={model}
        phases={Object.fromEntries(Object.keys(readyPhases).map((key) => [key, 'error' as const]))}
        emptyText="暂无数据"
        onRetry={() => undefined}
        onRetryFailed={() => undefined}
      />
    );
    expect(sites.container.textContent).toContain('加载失败');
    expect(sites.container.textContent).toContain('重试');
  });
});

describe('site and upstream anomaly empty state', () => {
  it('shows 暂无数据 when the window has no requests and keeps a real zero', () => {
    const empty = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: {
        range: {},
        instant: { serverCap: [{ labels: {}, value: 1 }] }
      }
    });
    expect(empty.board.focusThirdTitle).toBe('站点与上游异常');
    expect(empty.board.focusThirdFigure).toBe('暂无数据');

    const zeroTotal = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: {
        range: {},
        instant: {
          serverCap: [{ labels: {}, value: 1 }],
          starWindowRequests: [{ labels: { zone: '*' }, value: 0 }]
        }
      }
    });
    expect(zeroTotal.board.focusThirdFigure).toBe('暂无数据');

    const zeroShare = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: {
        range: {},
        instant: {
          serverCap: [{ labels: {}, value: 1 }],
          starWindowRequests: [{ labels: { zone: '*' }, value: 10 }],
          starWindowStatus: [{ labels: { zone: '*', code: '5xx' }, value: 0 }]
        }
      }
    });
    expect(zeroShare.board.focusThirdFigure).toBe('0');

    const ready = render(
      <NginxFocusTile label="站点与上游异常" figure={empty.board.focusThirdFigure} phase="ready" onRetry={() => undefined} />
    );
    expect(ready.container.querySelector('[data-nginx-focus="站点与上游异常"]')?.textContent).toContain('暂无数据');
    expect(ready.container.textContent).not.toContain('加载失败');

    cleanup();
    const broken = render(
      <NginxFocusTile label="站点与上游异常" figure={empty.board.focusThirdFigure} phase="error" onRetry={() => undefined} />
    );
    expect(broken.container.textContent).toContain('加载失败');
    expect(broken.container.querySelector('[data-nginx-focus="站点与上游异常"]')?.textContent).not.toContain('暂无数据');
  });
});

describe('site table processing time', () => {
  const timeSeries = (zone: string, value: number): RangeSeries => series(
    'nginx_vts_server_request_time',
    { zone, metric: 'nginx_vts_server_request_time' },
    [{ time: now, value }]
  );

  const dashboard = (zoneMs: number, totalMs: number) => buildNginxDashboard({
    onboarded: true,
    nowSeconds: now,
    intervalSeconds: 60,
    data: {
      range: {
        zoneTime: [timeSeries('www', zoneMs)],
        starTime: [timeSeries('*', totalMs)]
      },
      instant: {
        serverCap: [{ labels: { metric: 'nginx_vts_server_requests' }, value: 1 }],
        serverFresh: [
          { labels: { metric: 'nginx_vts_server_request_time', zone: 'www' }, value: now },
          { labels: { metric: 'nginx_vts_server_request_time', zone: '*' }, value: now }
        ]
      }
    }
  });

  const timeCells = (zoneMs: number, totalMs: number) => {
    const model = dashboard(zoneMs, totalMs);
    const view = render(
      <SitesPane
        model={model}
        phases={readyPhases}
        emptyText="暂无数据"
        onRetry={() => undefined}
        onRetryFailed={() => undefined}
      />
    );
    const detailRow = view.container.querySelector('[data-row-key="www"]');
    return {
      model,
      detail: detailRow?.textContent ?? '',
      total: view.container.querySelector('[data-row-key="total"]')?.textContent ?? ''
    };
  };

  it('uses one unit for the detail row and the total row', () => {
    const mixed = timeCells(200, 1500);
    expect(mixed.model.zoneTimeUnit).toBe('ms');
    expect(mixed.model.requestTimeUnit).toBe('s');
    expect(mixed.detail).toContain('0.2 秒');
    expect(mixed.detail).not.toContain('ms');
    expect(mixed.total).toContain('1.5 秒');
    expect(mixed.total).not.toContain('ms');

    cleanup();
    const flipped = timeCells(1500, 200);
    expect(flipped.detail).toContain('1.5 秒');
    expect(flipped.total).toContain('0.2 秒');
    expect(flipped.total).not.toContain('ms');

    cleanup();
    const small = timeCells(200, 400);
    expect(small.detail).toContain('200 ms');
    expect(small.total).toContain('400 ms');
  });
});
