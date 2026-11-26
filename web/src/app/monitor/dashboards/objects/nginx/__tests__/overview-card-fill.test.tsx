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
      ]
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

const KPI = ['采集状态', '请求速率', '活跃连接', '告警数量'] as const;

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
  it('stretches four KPI cards and three focus cards, including the spark and share bar', () => {
    const model = stubModel();
    expect(model.board.focusThirdTitle).toBe('连接结构');
    const view = renderOverview({ model, alertCount: 2 });

    KPI.forEach((label) => {
      const card = view.container.querySelector(`[data-nginx-tile="${label}"]`);
      expectFill(card);
      const row = card?.querySelector('[data-nginx-figure-row]');
      expect(classNames(row)).toEqual(expect.arrayContaining(['w-full', 'items-baseline']));
      expect(classNames(card?.querySelector('[data-nginx-tile-trail]'))).toContain('w-full');
    });

    const requestSpark = view.container.querySelector('[data-nginx-tile="请求速率"] [data-nginx-spark]');
    const activeSpark = view.container.querySelector('[data-nginx-tile="活跃连接"] [data-nginx-spark]');
    expect(classNames(requestSpark)).toContain('w-full');
    expect(classNames(activeSpark)).toContain('w-full');

    ['请求是否骤变', '是否在丢连接', '连接结构'].forEach((label) => {
      const card = view.container.querySelector(`[data-nginx-focus="${label}"]`);
      expectFill(card);
      const row = card?.querySelector('[data-nginx-figure-row]');
      expect(classNames(row)).toEqual(expect.arrayContaining(['w-full', 'items-baseline']));
      expect(classNames(card?.querySelector('[data-nginx-focus-trail]'))).toContain('w-full');
      expect(card?.querySelector('[data-nginx-focus-title]')?.textContent).not.toContain('次/秒');
      expect(card?.querySelector('[data-nginx-focus-title]')?.textContent).not.toContain('连接/秒');
    });

    const jump = view.container.querySelector('[data-nginx-focus="请求是否骤变"]');
    expect(jump?.querySelector('[data-nginx-figure-row]')?.textContent).toContain('次/秒');
    expect(classNames(jump?.querySelector('[data-nginx-spark]'))).toContain('w-full');

    const drop = view.container.querySelector('[data-nginx-focus="是否在丢连接"]');
    expect(drop?.querySelector('[data-nginx-figure-row]')?.textContent).toContain('连接/秒');
    expect(classNames(drop?.querySelector('[data-nginx-spark]'))).toContain('w-full');

    const structure = view.container.querySelector('[data-nginx-focus="连接结构"] [data-nginx-share-bar]');
    expect(classNames(structure)).toContain('w-full');
  });

  it('keeps the alert card filled in loading, error, and empty', () => {
    (['loading', 'error'] as const).forEach((alertPhase) => {
      const view = renderOverview({ alertPhase, alertCount: null });
      const card = view.container.querySelector('[data-nginx-tile="告警数量"]');
      expectFill(card);
      expect(card?.textContent).toContain(alertPhase === 'loading' ? '加载中' : '加载失败');
      cleanup();
    });

    const empty = renderOverview({ alertPhase: 'ready', alertCount: null });
    const card = empty.container.querySelector('[data-nginx-tile="告警数量"]');
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
    expect(classNames(card?.querySelector('[data-nginx-share-bar]'))).toContain('w-full');
    expect(classNames(card?.querySelector('[data-nginx-focus-trail]'))).toContain('w-full');
  });
});
