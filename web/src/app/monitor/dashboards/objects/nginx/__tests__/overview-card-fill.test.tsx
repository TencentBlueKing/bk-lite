import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildNginxDashboard, type RangeSeries } from '../layered/model';
import OverviewPane from '../layered/overview-pane';
import { NGINX_CARD_QUERIES, focusCardQueries, type NginxQueryPhase } from '../layered/query-phase';

vi.mock('../../../shared/use-linked-host', () => ({
  useLinkedHost: () => ({ host: null, href: '', pending: false })
}));

vi.mock('../../../shared/widgets/linked-host-segment', () => ({
  LinkedHostSegment: () => <div data-linked-host="" />
}));

vi.mock('../../host/layered/events-rail', () => ({
  default: () => <div data-events-rail="" />
}));

vi.mock('../layered/nginx-hint', () => ({
  NginxHint: () => null
}));

vi.mock('../layered/nginx-plot', () => ({
  NginxPlot: () => <div data-nginx-plot="" />
}));

vi.mock('../../../shared/widgets/useECharts', () => ({
  useECharts: () => ({ containerRef: () => undefined, getInstance: () => null })
}));

afterEach(() => {
  cleanup();
});

const now = 1_700_000_000;

const series = (
  name: string,
  labels: Record<string, string>,
  points: { time: number; value: number }[]
): RangeSeries => ({ name, labels, points });

const fresh = (metric: string) => ({ labels: { metric }, value: now });

const stubModel = () => buildNginxDashboard({
  onboarded: true,
  nowSeconds: now,
  intervalSeconds: 60,
  data: {
    range: {
      requestsRate: [series('nginx_requests', {}, [
        { time: now - 60, value: 1 },
        { time: now, value: 4 }
      ])],
      acceptsRate: [series('nginx_accepts', {}, [
        { time: now - 60, value: 4 },
        { time: now, value: 6 }
      ])],
      handledRate: [series('nginx_handled', {}, [
        { time: now - 60, value: 3 },
        { time: now, value: 5 }
      ])],
      conn: [
        series('nginx_connections', { status: 'active' }, [{ time: now, value: 10 }]),
        series('nginx_connections', { status: 'reading' }, [{ time: now, value: 2 }]),
        series('nginx_connections', { status: 'writing' }, [{ time: now, value: 3 }]),
        series('nginx_connections', { status: 'waiting' }, [{ time: now, value: 5 }])
      ]
    },
    instant: {
      serverCap: [],
      upstreamCap: [],
      stubFresh: [
        fresh('nginx_requests'),
        fresh('nginx_active'),
        fresh('nginx_reading'),
        fresh('nginx_writing'),
        fresh('nginx_waiting'),
        fresh('nginx_accepts'),
        fresh('nginx_handled')
      ],
      droppedWindow: [{ labels: {}, value: 1 }]
    }
  },
  capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
});

const readyPhases = (): Record<string, NginxQueryPhase> => {
  const phases: Record<string, NginxQueryPhase> = {};
  Object.values(NGINX_CARD_QUERIES).flat().forEach((key) => {
    phases[key] = 'ready';
  });
  return phases;
};

const KPI = ['请求速率', '活跃连接', '告警数量', '等待连接', '丢弃连接'] as const;

const classNames = (node: Element | null | undefined) => (node?.getAttribute('class') ?? '').split(/\s+/).filter(Boolean);

const expectFill = (node: Element | null | undefined) => {
  const names = classNames(node);
  expect(names).toContain('w-full');
  expect(names).toContain('h-full');
};

const renderOverview = ({
  alertPhase = 'ready',
  alertCount = 2,
  phases = readyPhases(),
  model = stubModel()
}: {
  alertPhase?: NginxQueryPhase;
  alertCount?: number | null;
  phases?: Record<string, NginxQueryPhase>;
  model?: ReturnType<typeof stubModel>;
} = {}) => render(
  <OverviewPane
    model={model}
    phases={phases}
    alertPhase={alertPhase}
    emptyText="暂无数据"
    alertCount={alertCount}
    alertEvents={[]}
    nodeId=""
    ip=""
    onOpenAlerts={() => undefined}
    onFocusAlert={() => undefined}
    onOpen={() => undefined}
    onRetry={() => undefined}
    onRetryFailed={() => undefined}
    onRetryAlerts={() => undefined}
  />
);

describe('overview cards fill their grid cells', () => {
  it('stretches health KPIs without mini trends and gives focus cards a sparkline', () => {
    const model = stubModel();
    expect(model.board.focusThirdTitle).toBe('连接结构');
    const view = renderOverview({ model, alertCount: 2 });

    expect(view.container.querySelector('[data-nginx-host]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="采集状态"]')).toBeNull();
    expect(view.container.querySelector('[data-nginx-tile="告警数量"]')?.textContent).toContain('2');
    expect(view.container.textContent).toContain('健康概览');
    expect(view.container.textContent).toContain('事件');
    expect(view.container.textContent).toContain('重点关注');
    expect(view.container.textContent).toContain('趋势');

    const health = view.container.querySelector('[data-nginx-health-row="5"]');
    expect(health?.querySelectorAll('[data-nginx-width="1/5"]')).toHaveLength(5);
    expect(health?.querySelector('[data-nginx-width="1/3"], [data-nginx-width="1/2"]')).toBeNull();
    expect([...health!.querySelectorAll('[data-nginx-tile]')].map((node) => node.getAttribute('data-nginx-tile'))).toEqual([
      '请求速率', '活跃连接', '等待连接', '丢弃连接', '告警数量'
    ]);

    KPI.forEach((label) => {
      const card = view.container.querySelector(`[data-nginx-tile="${label}"]`);
      expectFill(card);
      expect(card?.closest('[data-nginx-width="1/5"]')).toBeTruthy();
      expect(card?.getAttribute('data-nginx-kpi-height')).toBe('72');
      expect(card?.className).toContain('h-[72px]');
      expect(card?.className).not.toContain('h-[104px]');
      const row = card?.querySelector('[data-nginx-figure-row]');
      expect(classNames(row)).toEqual(expect.arrayContaining(['w-full', 'items-baseline']));
      expect(card?.querySelector('[data-nginx-spark], [data-nginx-plot]')).toBeNull();
    });

    ['请求是否骤变', '是否在丢连接', '连接结构'].forEach((label) => {
      const card = view.container.querySelector(`[data-nginx-focus="${label}"]`);
      expectFill(card);
      expect(card?.className).toContain('h-[168px]');
      expect(card?.getAttribute('data-nginx-focus-layout')).toBe('split');
      expect(card?.getAttribute('data-nginx-focus-height')).toBe('168');
      expect(card?.closest('[data-nginx-width="1/3"]') ?? card).toBeTruthy();
      expect(card?.getAttribute('data-nginx-width')).toBe('1/3');
      const copy = card?.querySelector('[data-nginx-focus-copy]');
      const plot = card?.querySelector('[data-nginx-focus-plot]');
      expect(copy).toBeTruthy();
      expect(plot).toBeTruthy();
      expect(copy!.compareDocumentPosition(plot!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(card?.querySelector('[data-nginx-spark]')).toBeTruthy();
      expect(card?.querySelector('[data-nginx-share-bar]')).toBeNull();
    });
    expect(view.container.querySelector('[data-nginx-focus="是否在丢连接"]')?.textContent).not.toContain('完成率');

    const jump = view.container.querySelector('[data-nginx-focus="请求是否骤变"]');
    expect(jump?.querySelector('[data-nginx-focus-title]')?.textContent).toContain('次/秒');
    expect(jump?.querySelector('[data-nginx-figure-row]')?.textContent).not.toContain('次/秒');

    const drop = view.container.querySelector('[data-nginx-focus="是否在丢连接"]');
    expect(drop?.querySelector('[data-nginx-focus-title]')?.textContent).toContain('连接/秒');
    expect(drop?.querySelector('[data-nginx-figure-row]')?.textContent).not.toContain('连接/秒');
  });

  it('keeps the request card filled in loading, error, and empty', () => {
    (['loading', 'error'] as const).forEach((phase) => {
      const phases = readyPhases();
      NGINX_CARD_QUERIES.request.forEach((key) => {
        phases[key] = phase;
      });
      const view = renderOverview({ phases });
      const card = view.container.querySelector('[data-nginx-tile="请求速率"]');
      expectFill(card);
      expect(card?.textContent).toContain(phase === 'loading' ? '加载中' : '加载失败');
      cleanup();
    });

    const emptyModel = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: { range: {}, instant: { serverCap: [], upstreamCap: [] } },
      capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
    });
    const empty = renderOverview({ model: emptyModel });
    const card = empty.container.querySelector('[data-nginx-tile="请求速率"]');
    expectFill(card);
    expect(card?.textContent).toContain('暂无数据');
  });

  it('keeps the connection-structure card filled in loading, error, and empty', () => {
    const model = stubModel();
    const thirdKeys = focusCardQueries(model.board.focusThirdTab);
    expect(model.board.focusThirdTitle).toBe('连接结构');

    (['loading', 'error'] as const).forEach((phase) => {
      const phases = readyPhases();
      thirdKeys.forEach((key) => {
        phases[key] = phase;
      });
      const view = renderOverview({ model, phases });
      const card = view.container.querySelector('[data-nginx-focus="连接结构"]');
      expectFill(card);
      expect(card?.textContent).toContain(phase === 'loading' ? '加载中' : '加载失败');
      cleanup();
    });

    const emptyModel = buildNginxDashboard({
      onboarded: true,
      nowSeconds: now,
      data: { range: {}, instant: { serverCap: [], upstreamCap: [] } },
      capabilityPhases: { serverCap: 'ready', upstreamCap: 'ready' }
    });
    expect(emptyModel.board.focusThirdTitle).toBe('连接结构');
    expect(emptyModel.board.focusThirdFigure).toBe('暂无数据');
    const empty = renderOverview({ model: emptyModel });
    const card = empty.container.querySelector('[data-nginx-focus="连接结构"]');
    expectFill(card);
    expect(card?.textContent).toContain('暂无数据');
    expect(card?.querySelector('[data-nginx-share-bar]')).toBeNull();
    expect(card?.querySelector('[data-nginx-spark]')).toBeNull();
  });
});
