import { describe, expect, it } from 'vitest';

import type { RumApplicationHealthItem } from '@/app/rum/api';
import { homeGlance } from '@/app/rum/applications/lib/home-glance';

function app(partial: Partial<RumApplicationHealthItem> & Pick<RumApplicationHealthItem, 'application'>): RumApplicationHealthItem {
  return {
    enabled: true,
    sessions: 20,
    views: 10,
    errors: 0,
    lcpP75: 1000,
    inpP75: 100,
    errorRate: 0,
    ...partial,
  };
}

describe('homeGlance', () => {
  it('按列表里的体验口径统计，并挑出错误率最高和 LCP 最差的应用', () => {
    const glance = homeGlance([
      app({ application: 'store', errorRate: 0.22, lcpP75: 2400, errors: 4 }),
      app({ application: 'console', errorRate: 0, lcpP75: 1600 }),
      app({ application: 'docs', enabled: true, sessions: 0, lcpP75: 0, errorRate: 0 }),
    ]);
    expect(glance.total).toBe(3);
    expect(glance.counts).toEqual({ poor: 1, watch: 0, observing: 1, empty: 1 });
    expect(glance.topError?.application).toBe('store');
    expect(glance.worstLcp?.application).toBe('store');
  });

  it('会话不到 5 个时仍按错误率和体验指标归类，和差体验应用同一口径', () => {
    const glance = homeGlance([
      app({ application: 'demo', sessions: 4, errorRate: 0.5, lcpP75: 104, inpP75: 32 }),
    ]);
    expect(glance.counts.poor).toBe(1);
    expect(glance.counts.observing).toBe(0);
  });
});
