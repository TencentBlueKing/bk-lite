import { describe, expect, it } from 'vitest';
import {
  MSSQL_WAIT_TOP_VIEWPORT,
  MSSQL_WAIT_TOP_VISIBLE_ROWS,
  formatMssqlDuration,
  mssqlLockedReading
} from '../display-units';
import { clerkChart } from '../series';
import type { MetricSeries } from '../../../common/simple-dashboard-core';

const series = (name: string, points: MetricSeries['viewData']): MetricSeries => ({
  name,
  display_name: name,
  description: '',
  unit: 'kibibytes',
  query: '',
  color: '#000',
  viewData: points,
  loadState: 'success'
});

describe('mssql card units', () => {
  it('时延按本卡峰值换算，整数不补 .00', () => {
    expect(formatMssqlDuration(5551, 5551)).toBe('5.55 s');
    expect(formatMssqlDuration(53599, 53599)).toBe('53.60 s');
    expect(formatMssqlDuration(788756, 788756)).toBe('13.15 min');
    expect(formatMssqlDuration(2000, 2000)).toBe('2 s');
    expect(formatMssqlDuration(999, 999)).toBe('999 ms');
    expect(formatMssqlDuration(0, 0)).toBe('0 ms');
    expect(formatMssqlDuration(5551, 788756)).toBe('0.09 min');
  });

  it('同一张内存卡按最大量级锁成一个单位', () => {
    const format = mssqlLockedReading('kibibytes', 1024 * 1024);
    expect(format?.(757 * 1024)).toBe('0.74 GiB');
    expect(format?.(1015 * 1024)).toBe('0.99 GiB');
    expect(format?.(1024 * 1024)).toBe('1 GiB');
    const smaller = mssqlLockedReading('kibibytes', 800 * 1024);
    expect(smaller?.(757 * 1024)).toBe('757 MiB');
  });

  it('ms/s 和次/秒不按时长或字节换算', () => {
    expect(mssqlLockedReading('msps', 788756)).toBeNull();
    expect(mssqlLockedReading('cps', 12)).toBeNull();
    expect(mssqlLockedReading('percent', 100)).toBeNull();
  });

  it('Clerk 列表读数跟整张卡同一个单位', () => {
    const chart = clerkChart({
      mssql_pro_clerks: series('mssql_pro_clerks', [{
        time: 1,
        value1: 757 * 1024,
        value2: 1024 * 1024,
        seriesMetrics: {
          value1: { clerk_type: 'CACHESTORE' },
          value2: { clerk_type: 'MEMORYCLERK' }
        }
      } as never])
    });
    expect(chart.legends.map((item) => item.reading)).toEqual(['1 GiB', '0.74 GiB']);
    expect(chart.formatReading?.(757 * 1024)).toBe('0.74 GiB');
    expect(chart.formatReading?.(1015 * 1024)).toBe('0.99 GiB');
  });

  it('等待 Top 可视高度按 5 行固定', () => {
    expect(MSSQL_WAIT_TOP_VISIBLE_ROWS).toBe(5);
    expect(MSSQL_WAIT_TOP_VIEWPORT).toBe(180);
  });
});
