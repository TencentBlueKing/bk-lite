import { describe, expect, it } from 'vitest';

import {
  downsampleValues,
  formatSparklineNumber,
  sparklineFromChartRows,
  sparklineFromValueSeries,
} from '../sparkline';

describe('sparkline', () => {
  it('rounds integers and one decimal', () => {
    expect(formatSparklineNumber(82.94)).toBe(82.9);
    expect(formatSparklineNumber(100.4)).toBe(100);
    expect(formatSparklineNumber(3)).toBe(3);
  });

  it('keeps nulls for gaps and downsamples to max points', () => {
    const values = [1, null, 3, 4, 5, 6, 7, 8, 9, 10];
    expect(downsampleValues(values, 20)).toEqual([1, null, 3, 4, 5, 6, 7, 8, 9, 10]);
    const sampled = downsampleValues(Array.from({ length: 100 }, (_, index) => index), 5);
    expect(sampled).toHaveLength(5);
    expect(sampled[0]).toBe(0);
    expect(sampled[4]).toBe(99);
  });

  it('builds window metadata from unix seconds', () => {
    const start = 1_704_067_200;
    const times = [start, start + 900];
    const spark = sparklineFromValueSeries(times, [71.12, 82.94], { name: '磁盘使用率', unit: '%' });
    expect(spark.name).toBe('磁盘使用率');
    expect(spark.latest).toBe(82.9);
    expect(spark.min).toBe(71.1);
    expect(spark.max).toBe(82.9);
    expect(spark.range).toBe('15min');
    expect(spark.time).toMatch(/^\d{2}:\d{2}~\d{2}:\d{2}$/);
    expect(spark.value).toEqual([71.1, 82.9]);
  });

  it('reads value1 from chart rows', () => {
    const spark = sparklineFromChartRows(
      [
        { time: 1_704_067_200, value1: 10, value2: 99 },
        { time: 1_704_067_260, value1: 12 },
      ],
      { name: 'CPU', group: '计算', metric: 'cpu_usage' },
    );
    expect(spark?.metric).toBe('cpu_usage');
    expect(spark?.group).toBe('计算');
    expect(spark?.value).toEqual([10, 12]);
    expect(spark?.latest).toBe(12);
  });

  it('returns null when rows have no timestamps', () => {
    expect(sparklineFromChartRows([{ value1: 1 }], { name: 'x' })).toBeNull();
  });
});
