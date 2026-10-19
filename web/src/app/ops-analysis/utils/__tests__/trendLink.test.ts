import { describe, expect, it } from 'vitest';

import type { ChartLinkPoint } from '@/app/ops-analysis/utils/interactionLink';
import {
  bindTrendGridClick,
  categoryIndexFromAxisValue,
  readTrendCategoryIndex,
  resolveTrendColumnPoint,
  resolveTrendGridClick,
  trendColumnCanOpen,
  trendPointsFromTooltip,
  trendTemplateNeedsPointValue,
  type TrendGridChart,
} from '@/app/ops-analysis/utils/trendLink';

const point = (
  numeric: number | null,
  extra: Partial<ChartLinkPoint> = {},
): ChartLinkPoint => ({
  seriesName: 'cpu',
  ...(numeric != null && Number.isFinite(numeric) ? { numeric } : {}),
  ...extra,
});

describe('trend column link', () => {
  it('opens an empty column when the template only uses time or a filter', () => {
    const empty = point(null, { time: '2020-01-01T00:00:00.000Z' });
    expect(trendTemplateNeedsPointValue('https://x/$__value.time$', [])).toBe(false);
    expect(trendTemplateNeedsPointValue('https://x/$env$', [])).toBe(false);
    expect(trendColumnCanOpen('https://x/$__value.time$', [], [empty])).toBe(true);
    expect(trendColumnCanOpen('https://x/$env$', [], [empty])).toBe(true);
    expect(resolveTrendColumnPoint({
      template: 'https://x/$__value.time$',
      candidates: [{ point: empty }],
    })?.time).toBe('2020-01-01T00:00:00.000Z');
  });

  it('opens without a numeric when the only field token is the axis dimension', () => {
    const empty = point(null, { axisField: 'name', fields: { name: 'web' } });
    expect(trendTemplateNeedsPointValue('https://x/$__data.fields.name$', ['name'])).toBe(false);
    expect(trendColumnCanOpen('https://x/$__data.fields.name$', ['name'], [empty])).toBe(true);
  });

  it('refuses an empty column when the template needs a value, series name, or other field', () => {
    const empty = point(null, { fields: { host: 'web' } });
    expect(trendColumnCanOpen('https://x/$__value.numeric$', [], [empty])).toBe(false);
    expect(trendColumnCanOpen('https://x/$__value.raw$', [], [empty])).toBe(false);
    expect(trendColumnCanOpen('https://x/$__series.name$', [], [empty])).toBe(false);
    expect(trendColumnCanOpen('https://x/$__data.fields.host$', ['name'], [empty])).toBe(false);
    expect(resolveTrendColumnPoint({
      template: 'https://x/$__series.name$',
      candidates: [{ point: empty }, { point: undefined }],
    })).toBeUndefined();
  });

  it('treats numeric zero as a value', () => {
    const zero = point(0);
    expect(trendColumnCanOpen('https://x/$__value.numeric$', [], [zero])).toBe(true);
    expect(resolveTrendColumnPoint({
      template: 'https://x/$__value.numeric$',
      candidates: [{ point: zero }],
    })?.numeric).toBe(0);
  });

  it('picks the valued series closest to the pointer and ignores empty series', () => {
    const picked = resolveTrendColumnPoint({
      template: 'https://x/$__value.numeric$',
      pointerY: 12,
      candidates: [
        { point: point(null, { seriesName: 'miss' }), pixelY: 10 },
        { point: point(1, { seriesName: 'low' }), pixelY: 80 },
        { point: point(9, { seriesName: 'high' }), pixelY: 20 },
      ],
    });
    expect(picked?.seriesName).toBe('high');
  });

  it('rounds in-range category indexes and rejects labels', () => {
    expect(categoryIndexFromAxisValue(1.4, 3)).toBe(1);
    expect(categoryIndexFromAxisValue(2.6, 3)).toBeUndefined();
    expect(categoryIndexFromAxisValue(-0.2, 3)).toBe(0);
    expect(categoryIndexFromAxisValue('cpu', 3)).toBeUndefined();
    expect(categoryIndexFromAxisValue(Number.NaN, 3)).toBeUndefined();
  });

  it('reads a category only inside the grid and skips hidden series', () => {
    const calls: number[] = [];
    const chart = {
      containPixel: (_finder: { gridIndex: number }, value: number[]) => value[0] >= 0,
      convertFromPixel: () => [1.2, 40],
      convertToPixel: (finder: { seriesIndex: number }, value: unknown[]) => {
        calls.push(finder.seriesIndex);
        const numeric = (value as number[])[1];
        return [10, 100 - numeric];
      },
      getZr: () => ({ on() {}, off() {} }),
    } as TrendGridChart;
    expect(readTrendCategoryIndex(chart, -1, 8, 4)).toBeUndefined();

    const cpu = point(10, { seriesName: 'cpu' });
    const mem = point(80, { seriesName: 'mem' });
    const disk = point(15, { seriesName: 'disk' });
    const series = [
      { name: 'cpu', points: [point(null), cpu] },
      { name: 'mem', points: [point(null), mem] },
      { name: 'disk', points: [point(null), disk] },
    ];
    const picked = resolveTrendGridClick({
      chart,
      offsetX: 12,
      offsetY: 18,
      categoryCount: 2,
      template: 'https://x/$__value.numeric$',
      series,
      legendSelected: { cpu: true, mem: true, disk: false },
    });
    expect(picked).toBe(mem);
    expect(calls).toEqual([0, 1]);
  });

  it('reads link points from axis tooltip params', () => {
    const link = point(3);
    expect(trendPointsFromTooltip([
      { data: { value: 3, __link: link } },
      { data: { value: 0 } },
    ])).toEqual([link]);
  });

  it('binds one grid click and removes it', () => {
    const handlers: Array<(event: { offsetX: number; offsetY: number }) => void> = [];
    const chart = {
      containPixel: () => true,
      convertFromPixel: () => [0, 0],
      convertToPixel: () => [0, 0],
      getZr: () => ({
        on: (_event: string, handler: (event: { offsetX: number; offsetY: number }) => void) => {
          handlers.push(handler);
        },
        off: (_event: string, handler: (event: { offsetX: number; offsetY: number }) => void) => {
          const index = handlers.indexOf(handler);
          if (index >= 0) handlers.splice(index, 1);
        },
      }),
    } satisfies TrendGridChart;
    const seen: number[] = [];
    const off = bindTrendGridClick(chart, (x, y) => {
      seen.push(x, y);
    });
    handlers[0]?.({ offsetX: 4, offsetY: 9 });
    expect(seen).toEqual([4, 9]);
    off();
    expect(handlers).toHaveLength(0);
  });
});
