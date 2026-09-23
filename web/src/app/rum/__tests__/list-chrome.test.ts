import { describe, expect, it } from 'vitest';

import { exportRowsToCsv } from '@/app/rum/components/export-button';
import { parseRumTraffic } from '@/app/rum/lib/search-params';
import { parseRumPageSize, sliceRumPage } from '@/app/rum/lib/table-pagination';

describe('rum list chrome', () => {
  it('parses RUM traffic scopes including automated', () => {
    expect(parseRumTraffic('automated')).toBe('automated');
    expect(parseRumTraffic('visitors')).toBe('visitors');
    expect(parseRumTraffic('all')).toBe('all');
    expect(parseRumTraffic('nope')).toBe('visitors');
  });

  it('builds CSV with UTF-8 BOM for Excel', () => {
    const csv = exportRowsToCsv([
      { name: 'a', count: 1 },
      { name: 'b,c', count: 2 },
    ]);
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain('name,count');
    expect(csv).toContain('"b,c",2');
  });

  it('RumListToolbar is the shared list chrome entry', async () => {
    const mod = await import('@/app/rum/components/rum-list-toolbar');
    expect(typeof mod.default).toBe('function');
  });

  it('exposes dual and single workbench shells', async () => {
    const mod = await import('@/app/rum/components/rum-dual-workbench');
    expect(typeof mod.RumDualWorkbench).toBe('function');
    expect(typeof mod.RumSingleWorkbench).toBe('function');
    expect(mod.RUM_WORKBENCH_ASIDE_WIDTH).toContain('200px');
    expect(mod.RUM_WORKBENCH_HEAD).toContain('h-10');
  });

  it('RumRangeSegmented exposes short analytics ranges', async () => {
    const mod = await import('@/app/rum/components/rum-range-segmented');
    expect(typeof mod.default).toBe('function');
    expect(mod.RUM_ANALYTICS_RANGES).toEqual(['1h', '24h', '7d']);
  });

  it('slices list rows onto a clamped page', () => {
    expect(parseRumPageSize('20')).toBe(20);
    expect(parseRumPageSize('7')).toBe(20);
    const sliced = sliceRumPage(['a', 'b', 'c', 'd', 'e'], 2, 2);
    expect(sliced).toEqual({ current: 2, pageSize: 2, total: 5, rows: ['c', 'd'] });
    expect(sliceRumPage(['a', 'b'], 9, 10).current).toBe(1);
  });

  it('RumBackButton and RumRefreshButton are shared detail chrome', async () => {
    const back = await import('@/app/rum/components/rum-back-button');
    const refresh = await import('@/app/rum/components/rum-refresh-button');
    expect(typeof back.default).toBe('function');
    expect(typeof refresh.default).toBe('function');
  });
});
