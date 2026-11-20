import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { describe, expect, it, vi } from 'vitest';
import zh from '../../../../../locales/zh.json';
import en from '../../../../../locales/en.json';
import { MYSQL_CATEGORY_COPY } from '../../../mysql/layered/mysql-copy';
import { REDIS_CATEGORY_COPY } from '../../../redis/layered/redis-copy';
import MongoOverview from '../../../mongodb/layered/overview-pane';
import PostgresOverview from '../../../postgresql/layered/overview-pane';
import RedisOverview from '../../../redis/layered/overview-pane';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: 'unauthenticated' })
}));

vi.mock('../../../../shared/widgets/useECharts', () => ({
  useECharts: () => ({ containerRef: () => undefined, getInstance: () => null })
}));

const text = zh.monitor.dashboards.text;
const english = en.monitor.dashboards.text;

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

describe('professional alert kpi label', () => {
  it('五盘健康概览告警标题都是告警数量，排队写不再在标题旁标个', () => {
    expect(text.mysqlCategoryKpiAlerts).toBe('告警数量');
    expect(text.redisCategoryKpiAlerts).toBe('告警数量');
    expect(text.mysqlCategoryKpiAlerts).not.toBe('告警');
    expect(text.redisCategoryKpiAlerts).not.toContain('事件统计');
    expect(english.mysqlCategoryKpiAlerts).toBe('Alert count');
    expect(english.redisCategoryKpiAlerts).toBe('Alert count');
    expect(MYSQL_CATEGORY_COPY.kpiAlerts[1]).toBe('告警数量');
    expect(REDIS_CATEGORY_COPY.kpiAlerts[1]).toBe('告警数量');
    expect(MYSQL_CATEGORY_COPY.replicaCount[1]).toBe('{n} 个从库');

    const mongo = mount(
      <MongoOverview
        metricMap={{}}
        pendingMetricNames={new Set()}
        booting={false}
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        eventsLoading={false}
        onOpenAlerts={() => undefined}
        onOpenTarget={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    const mongoAlerts = mongo.container.querySelector('[data-kpi="alerts"]');
    expect(mongoAlerts?.textContent).toContain('告警数量');
    expect(mongoAlerts?.textContent).not.toContain('个');
    const queued = mongo.container.querySelector('[data-mongodb-focus="queued-writes"]');
    expect(queued?.textContent).toContain('排队写操作');
    expect(queued?.textContent).not.toContain('(个)');
    expect(queued?.textContent).not.toContain('个');

    const postgres = mount(
      <PostgresOverview
        metricMap={{}}
        pendingMetricNames={new Set()}
        booting={false}
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        eventsLoading={false}
        onOpenAlerts={() => undefined}
        onOpenFocus={() => undefined}
        onFocusAlert={() => undefined}
      />
    );
    const pgAlerts = postgres.container.querySelector('[data-kpi="alerts"]');
    expect(pgAlerts?.textContent).toContain('告警数量');
    expect(pgAlerts?.textContent).not.toContain('个');

    const redis = mount(
      <RedisOverview
        summaryCards={[]}
        loading={false}
        metricMap={{}}
        pendingMetricNames={new Set()}
        alertCount={0}
        alertsOpen={false}
        alertEvents={[]}
        eventsLoading={false}
        onOpenAlerts={() => undefined}
        onFocusAlert={() => undefined}
        onOpen={() => undefined}
      />
    );
    const redisAlerts = redis.container.querySelector('[data-kpi="alerts"]');
    expect(redisAlerts?.textContent).toContain('告警数量');
    expect(redisAlerts?.textContent).not.toContain('告警事件统计');
    expect(redisAlerts?.textContent).not.toContain('个');
  });
});
