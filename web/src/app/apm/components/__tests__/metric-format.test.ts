import { describe, expect, it } from 'vitest';
import {
  deriveHealth,
  formatErrorRate,
  formatLatency,
  formatRelativeTime,
  formatThroughput,
  isErrorRateDanger,
} from '../metric-format';

describe('APM metric-format', () => {
  it('按错误率与目录状态推导健康等级', () => {
    expect(deriveHealth('active', 0)).toBe(5);
    expect(deriveHealth('active', 0.02)).toBe(2);
    expect(deriveHealth('active', 0.08)).toBe(1);
    expect(deriveHealth('silent', null)).toBe(3);
    expect(deriveHealth('archived', null)).toBe(4);
  });

  it('格式化吞吐、错误率与时延', () => {
    expect(formatThroughput(null)).toBe('—');
    expect(formatThroughput(null, true)).toBe('查询失败');
    expect(formatThroughput(12.4)).toBe('12.4');
    expect(formatThroughput(1500)).toBe('1.5k');
    expect(formatErrorRate(0.0123)).toBe('1.23%');
    expect(formatErrorRate(0.2)).toBe('20.0%');
    expect(formatLatency(42)).toBe('42ms');
    expect(formatLatency(1500)).toBe('1.50s');
    expect(isErrorRateDanger(0.01)).toBe(true);
    expect(isErrorRateDanger(0.009)).toBe(false);
  });

  it('格式化相对时间', () => {
    expect(formatRelativeTime(undefined)).toBe('—');
    expect(formatRelativeTime('not-a-date')).toBe('—');
    expect(formatRelativeTime(new Date().toISOString())).toBe('刚刚');
  });
});
