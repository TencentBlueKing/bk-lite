import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NGINX_HINTS } from '../layered/hints';
import { buildNginxDashboard, type RangeSeries } from '../layered/model';
import ConnectionsPane from '../layered/connections-pane';
import OverviewPane from '../layered/overview-pane';
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

vi.mock('../../host/layered/events-rail', () => ({
  default: () => <div data-events-rail="">暂无事件</div>
}));

afterEach(() => {
  cleanup();
});

const now = 1_700_000_000;

const readyPhases = (): Record<string, NginxQueryPhase> => ({
  ...Object.fromEntries(Object.values(NGINX_CARD_QUERIES).flat().map((key) => [key, 'ready' as const])),
  serverCap: 'ready',
  upstreamCap: 'ready'
});

const series = (
  name: string,
  labels: Record<string, string>,
  points: { time: number; value: number }[]
): RangeSeries => ({ name, labels, points });

const fresh = (metric: string, extra: Record<string, string> = {}) => ({
  labels: { metric, ...extra },
  value: now
});

const vtsModel = () => buildNginxDashboard({
  onboarded: true,
  nowSeconds: now,
  intervalSeconds: 60,
  data: {
    range: {
      requestsRate: [series('nginx_requests', {}, [{ time: now, value: 4 }])],
      acceptsRate: [series('nginx_accepts', {}, [{ time: now, value: 3 }])],
      handledRate: [series('nginx_handled', {}, [{ time: now, value: 1 }])],
      conn: [
        series('nginx_connections', { status: 'active' }, [{ time: now, value: 3 }]),
        series('nginx_connections', { status: 'reading' }, [{ time: now, value: 1 }]),
        series('nginx_connections', { status: 'writing' }, [{ time: now, value: 1 }]),
        series('nginx_connections', { status: 'waiting' }, [{ time: now, value: 1 }])
      ],
      starStatusStep: [series('nginx_vts_server_response_2xx_count', { code: '2xx', zone: '*' }, [{ time: now, value: 2 }])],
      upRequestSum: [series('nginx_vts_upstream_requests', { upstream: 'backend' }, [{ time: now, value: 1 }])],
      upRequestRate: [
        series('nginx_vts_upstream_requests', { upstream: 'backend', upstream_address: '10.0.0.8:80', code: 'total' }, [{ time: now, value: 1 }]),
        series('nginx_vts_upstream_requests', { upstream: 'backend', upstream_address: '---', code: 'total' }, [{ time: now, value: 9 }])
      ]
    },
    instant: {
      serverCap: [{ labels: { metric: 'nginx_vts_server_requests' }, value: 1 }],
      upstreamCap: [{ labels: { metric: 'nginx_vts_upstream_requests' }, value: 1 }],
      stubFresh: [
        fresh('nginx_requests'),
        fresh('nginx_active'),
        fresh('nginx_reading'),
        fresh('nginx_writing'),
        fresh('nginx_waiting'),
        fresh('nginx_accepts'),
        fresh('nginx_handled')
      ],
      droppedWindow: [{ labels: {}, value: 2 }],
      starWindowRequests: [{ labels: { zone: '*' }, value: 10 }],
      starWindowStatus: [
        { labels: { zone: '*', code: '4xx' }, value: 3 },
        { labels: { zone: '*', code: '5xx' }, value: 1 }
      ],
      upWindowRequests: [{ labels: {}, value: 8 }],
      upWindow5xx: [{ labels: {}, value: 2 }],
      upWindowStatus: [
        { labels: { code: '2xx' }, value: 6 },
        { labels: { code: '5xx' }, value: 2 }
      ],
      upstreamFresh: [fresh('nginx_vts_upstream_requests', { upstream: 'backend', upstream_address: '10.0.0.8:80' })]
    }
  },
  capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
});

const renderOverview = (model = vtsModel()) => render(
  <OverviewPane
    model={model}
    phases={readyPhases()}
    alertPhase="ready"
    emptyText="暂无数据"
    alertCount={0}
    alertEvents={[]}
    nodeId="node"
    ip="10.0.0.8"
    onOpenAlerts={() => undefined}
    onFocusAlert={() => undefined}
    onOpen={() => undefined}
    onRetry={() => undefined}
    onRetryFailed={() => undefined}
    onRetryAlerts={() => undefined}
  />
);

describe('nginx spec v2.1 layout', () => {
  it('keeps the four health metrics, adds alert count, and drops the host strip', () => {
    const view = renderOverview();
    const health = view.container.querySelector('#nginx-health');
    const labels = [...(health?.querySelectorAll('[data-nginx-tile]') ?? [])]
      .map((node) => node.getAttribute('data-nginx-tile'));
    expect(labels).toEqual(['请求速率', '活跃连接', '等待连接', '丢弃连接', '告警数量']);
    expect(health?.querySelector('[data-nginx-health-row="5"]') ?? view.container.querySelector('[data-nginx-health-row="5"]')).toBeTruthy();
    ['请求速率', '活跃连接', '等待连接', '丢弃连接', '告警数量'].forEach((label) => {
      const card = health?.querySelector(`[data-nginx-tile="${label}"]`);
      expect(card?.closest('[data-nginx-width="1/5"]')).toBeTruthy();
      expect(card?.getAttribute('data-nginx-kpi-height')).toBe('72');
      expect(card?.className).not.toContain('h-[104px]');
    });
    expect(health?.querySelector('[data-nginx-width="1/3"], [data-nginx-width="1/2"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-host]')).toBeNull();
    expect(view.container.querySelector('[data-linked-host]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="采集状态"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-events]')).toBeTruthy();
    expect(view.container.querySelectorAll('[data-nginx-tile] [data-nginx-spark]')).toHaveLength(0);
    expect(view.container.querySelectorAll('[data-nginx-focus][data-nginx-focus-layout="split"]')).toHaveLength(3);
    expect(view.container.querySelector('[data-nginx-focus="是否在丢连接"]')?.textContent).not.toContain('完成率');
    expect(view.container.querySelectorAll('[data-nginx-focus] [data-nginx-spark]')).toHaveLength(3);
    expect(view.container.querySelector('[data-nginx-tile="丢弃连接"]')?.textContent).toContain('2');
    const requestTitle = view.container.querySelector('[data-nginx-tile="请求速率"] [data-nginx-title]');
    expect(requestTitle?.textContent).toContain('次/秒');
    expect(requestTitle?.querySelector('[data-nginx-unit]')).toBeTruthy();
    expect(requestTitle?.className).not.toContain('justify-between');
    const requestChart = view.container.querySelector('[data-nginx-chart="请求速率"]');
    expect(requestChart?.querySelector('[data-nginx-unit]')?.textContent).toBe('(次/秒)');
    expect(requestChart?.querySelector('[data-nginx-legend-reading]')?.textContent).toContain('4');
    expect(requestChart?.querySelector('[data-nginx-side-list]')).toBeNull();
    const acceptChart = view.container.querySelector('[data-nginx-chart="连接接受与处理速率"]');
    expect(acceptChart?.querySelectorAll('[data-nginx-legend-reading]')).toHaveLength(2);
  });

  it('shows 4xx, 5xx, and upstream 5xx as counts', () => {
    const model = vtsModel();
    expect(model.board.count4xx).toBe('3');
    expect(model.board.count5xx).toBe('1');
    expect(model.board.count5xxHot).toBe(true);
    expect(model.board.up5xx).toBe('2');
    expect(model.board.up5xx).not.toContain('%');
    expect(model.board.focusThirdFigure).toBe('1');
    expect(model.board.busyFigure).toBe('2');

    const sites = render(
      <SitesPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expect(sites.container.querySelector('[data-nginx-tile="4xx 次数"]')).toBeNull();
    expect(sites.container.querySelector('[data-nginx-tile="5xx 次数"]')).toBeNull();
    expect(sites.container.querySelector('[data-nginx-tile="窗口请求数"]')).toBeNull();
    expect(sites.container.textContent).not.toContain('5xx 比例');
    expect(sites.container.querySelector('[data-nginx-pie="状态码构成"]')?.textContent).toContain('3');
    expect(sites.container.querySelector('[data-nginx-pie="状态码构成"]')?.textContent).toContain('1');
    expect(sites.container.querySelector('[data-nginx-pie="状态码构成"] [data-nginx-pie-shape]')).toBeTruthy();
    expect(sites.container.querySelector('[data-nginx-pie="状态码构成"]')?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
    expect(sites.container.querySelector('[data-nginx-chart="状态码分布"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(sites.container.querySelector('[data-nginx-chart="状态码分布"][data-nginx-count-axis]')).toBeTruthy();
    expect(sites.container.textContent).toContain('状态码');
    expect(sites.container.textContent).toContain('流量与处理');
    expect(sites.container.textContent).toContain('站点明细');
    const exportName = sites.container.querySelector('[data-pro-table="站点"] [data-pro-table-export]')?.getAttribute('data-export-name');
    expect(exportName).toBe('nginx-请求与站点-站点.csv');

    const quiet = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: {
        range: {},
        instant: {
          serverCap: [{ labels: {}, value: 1 }],
          starWindowRequests: [{ labels: { zone: '*' }, value: 0 }],
          upWindowRequests: [{ labels: {}, value: 0 }],
          upstreamCap: [{ labels: {}, value: 1 }]
        }
      }
    });
    expect(quiet.board.count4xx).toBe('暂无数据');
    expect(quiet.board.count5xx).toBe('暂无数据');
    expect(quiet.board.up5xx).toBe('暂无数据');
    expect(quiet.board.up5xxSub).toBe('窗口内上游没有请求');
  });

  it('draws connection mix as a pie and keeps connection counts on an integer axis', () => {
    const model = vtsModel();
    const view = render(
      <ConnectionsPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expect(view.container.querySelector('[data-nginx-tile="繁忙连接"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="读取连接"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="繁忙连接占比"]')).toBeNull();
    expect(view.container.textContent).toContain('连接构成与占比');
    expect(view.container.textContent).toContain('连接趋势');
    const pie = view.container.querySelector('[data-nginx-pie="连接构成"]');
    expect(pie?.getAttribute('data-nginx-chart-kind')).toBe('pie');
    expect(pie?.getAttribute('data-nginx-pie-layout')).toBe('stack');
    expect(pie?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="连接占比趋势"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(pie?.querySelector('[data-nginx-pie-shape]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-share-bar]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-chart="连接数"][data-nginx-count-axis]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="连接数"] [data-nginx-legend-reading]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-chart="连接数"] [data-nginx-side-list]')).toBeNull();
    expect(view.container.querySelectorAll('[data-nginx-chart="连接占比趋势"] [data-nginx-legend-reading]')).toHaveLength(2);
    expect(view.container.querySelector('[data-nginx-chart="丢弃连接速率"] [data-nginx-legend-reading]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-chart="丢弃连接速率"]')?.hasAttribute('data-nginx-count-axis')).toBe(false);
  });

  it('exports the upstream table and hides blank addresses', () => {
    const model = vtsModel();
    expect(model.upstreamGroups.flatMap((group) => group.members).map((member) => member.address)).toEqual(['10.0.0.8:80']);
    expect(JSON.stringify(model.upstreamGroups)).not.toContain('---');
    const view = render(
      <UpstreamPane model={model} phases={readyPhases()} emptyText="暂无数据" onRetry={() => undefined} onRetryFailed={() => undefined} />
    );
    expect(view.container.querySelector('[data-nginx-tile="上游 5xx 次数"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="在线成员"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="上游请求速率"]')).toBeNull();
    expect(view.container.textContent).toContain('上游趋势');
    expect(view.container.textContent).toContain('上游状态码');
    expect(view.container.textContent).toContain('上游成员');
    expect(view.container.querySelectorAll('[data-nginx-width="1/3"] [data-nginx-chart]')).toHaveLength(3);
    expect(view.container.querySelector('[data-nginx-chart="上游状态码分布"]')?.closest('[data-nginx-width="3/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-pie="上游状态码构成"]')?.closest('[data-nginx-width="1/4"]')).toBeTruthy();
    expect(view.container.querySelector('[data-nginx-pie="上游状态码构成"] [data-nginx-pie-shape]')).toBeTruthy();
    const cells = [...view.container.querySelectorAll('[data-pro-table="上游"] td')].map((cell) => cell.textContent);
    expect(cells).toContain('10.0.0.8:80');
    expect(cells).not.toContain('---');
    expect(cells).not.toContain('地址未上报');
    expect(view.container.querySelector('[data-pro-table="上游"] [data-pro-table-export]')?.getAttribute('data-export-name')).toBe('nginx-上游-上游.csv');
  });

  it('keeps the question copy from the spec', () => {
    expect(NGINX_HINTS.request).toEqual({
      lead: '请求速率',
      body: '所选时间范围内，Nginx 平均每秒处理的 HTTP 请求数。'
    });
    expect(NGINX_HINTS.count4xx.body).toBe('所选时间范围内的客户端错误响应次数，常见原因是地址错误或缺少权限。');
    expect(NGINX_HINTS.count5xx.body).toBe('所选时间范围内的服务端错误响应次数。');
    expect(NGINX_HINTS.up5xx.body).toBe('所选时间范围内上游返回的服务端错误次数。');
    expect(NGINX_HINTS.busy.body).toBe('正在读取或写入的连接数，即读取连接加写入连接。');
    expect(NGINX_HINTS.siteUpstream.body).toBe('5xx 次数：所选时间范围内的服务端错误响应次数。\n已下线成员：被标记为下线的上游服务器数量。');
    expect(NGINX_HINTS.request.body).not.toContain('(每秒)');
  });
});

describe('expired nginx KPI', () => {
  it('shows 暂无数据 and the last reading time instead of zero', () => {
    const staleAt = now - 3600;
    const model = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      intervalSeconds: 60,
      data: {
        range: {
          requestsRate: [series('nginx_requests', {}, [
            { time: staleAt - 60, value: 12 },
            { time: staleAt, value: 0 }
          ])]
        },
        instant: {
          stubFresh: [{ labels: { metric: 'nginx_requests' }, value: staleAt }]
        }
      }
    });
    expect(model.board.requestFigure).toBe('暂无数据');
    expect(model.board.requestSub).toMatch(/^最近读数 \d{2}:\d{2}$/);
    expect(model.requestPoints.some((point) => point.value > 0)).toBe(true);

    const freshZero = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      intervalSeconds: 60,
      data: {
        range: {
          requestsRate: [series('nginx_requests', {}, [
            { time: now - 60, value: 12 },
            { time: now, value: 0 }
          ])]
        },
        instant: {
          stubFresh: [{ labels: { metric: 'nginx_requests' }, value: now }]
        }
      }
    });
    expect(freshZero.board.requestFigure).toBe('0');
    expect(freshZero.board.requestSub).toBe('');

    const view = renderOverview(model);
    const card = view.container.querySelector('[data-nginx-tile="请求速率"]');
    expect(card?.querySelector('[data-nginx-figure]')?.textContent).toBe('暂无数据');
    expect(card?.querySelector('[data-nginx-sub]')?.textContent).toMatch(/^最近读数 \d{2}:\d{2}$/);
  });
});
