import { describe, expect, it, vi } from 'vitest';
import {
  aggregateApplicationRedTrends,
  deriveHealth,
  formatErrorRate,
  formatDateTime,
  formatLatency,
  formatMetricEmpty,
  formatPerSecond,
  formatPercentage,
  formatRelativeTime,
  formatRequestRate,
  formatThroughput,
  formatTopologyEdgeMetrics,
  isErrorRateDanger,
  metricEmptyHint,
} from '../metric-format';

describe('APM metric-format', () => {
  it('按错误率与目录状态推导健康等级', () => {
    expect(deriveHealth('active', 0)).toBe(5);
    expect(deriveHealth('active', 0.02)).toBe(2);
    expect(deriveHealth('active', 0.08)).toBe(1);
    expect(deriveHealth('silent', null)).toBe(3);
    expect(deriveHealth('archived', null)).toBe(4);
  });

  it('区分无数据与查询失败空态', () => {
    expect(formatMetricEmpty()).toBe('无数据');
    expect(formatMetricEmpty(true)).toBe('查询失败');
    expect(metricEmptyHint()).toContain('暂无遥测样本');
    expect(metricEmptyHint(true)).toContain('可点击重试');
    expect(formatThroughput(null)).toBe('无数据');
    expect(formatThroughput(null, true)).toBe('查询失败');
    expect(formatErrorRate(null, true)).toBe('查询失败');
    expect(formatLatency(null)).toBe('无数据');
  });

  it('格式化吞吐、错误率与时延', () => {
    expect(formatThroughput(12.4)).toBe('12.4');
    expect(formatThroughput(1500)).toBe('1.5k');
    expect(formatErrorRate(0.0123)).toBe('1.23%');
    expect(formatErrorRate(0.2)).toBe('20.0%');
    expect(formatPercentage(99.9)).toBe('99.90%');
    expect(formatPercentage('83.6712')).toBe('83.67%');
    expect(formatLatency(42)).toBe('42ms');
    expect(formatLatency(1500)).toBe('1.50s');
    expect(isErrorRateDanger(0.01)).toBe(true);
    expect(isErrorRateDanger(0.009)).toBe(false);
  });

  it('格式化相对时间', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-21T08:00:00Z'));
    try {
      expect(formatRelativeTime(undefined)).toBe('—');
      expect(formatRelativeTime('not-a-date')).toBe('—');
      expect(formatRelativeTime('2026-08-21T08:00:00Z')).toBe('刚刚');
      expect(formatRelativeTime('2026-08-21T07:59:30Z')).toBe('30 秒前');
      expect(formatRelativeTime('2026-08-21T07:55:00Z')).toBe('5 分钟前');
      expect(formatRelativeTime('2026-08-21T06:00:00Z')).toBe('2 小时前');
      expect(formatRelativeTime('2026-08-20T08:00:00Z')).toBe('1 天前');
    } finally {
      vi.useRealTimers();
    }
  });

  it('根据当前 locale 格式化空态和相对时间', () => {
    const messages: Record<string, string> = {
      'apm.common.noData': 'No data',
      'apm.common.queryFailed': 'Query failed',
      'apm.common.metricNoSamplesHint': 'No telemetry samples',
      'apm.common.justNow': 'Just now',
      'apm.common.secondsAgo': '{count} seconds ago',
      'apm.common.minutesAgo': '{count} minutes ago',
      'apm.common.secondsValue': '{value} seconds',
      'apm.common.perSecondValue': '{value} per second',
      'apm.common.requestsPerSecondValue': '{value} requests per second',
    };
    const t = (id: string, fallback?: string, values?: Record<string, string | number>) => {
      const template = messages[id] || fallback || id;
      return Object.entries(values ?? {}).reduce(
        (result, [key, value]) => result.replace(`{${key}}`, String(value)),
        template,
      );
    };

    expect(formatMetricEmpty(false, t)).toBe('No data');
    expect(formatThroughput(null, true, t)).toBe('Query failed');
    expect(metricEmptyHint(false, t)).toBe('No telemetry samples');
    expect(formatRelativeTime(new Date().toISOString(), t)).toBe('Just now');
    expect(formatLatency(1500, false, t)).toBe('1.50 seconds');
    expect(formatPerSecond('12.4', t)).toBe('12.4 per second');
    expect(formatRequestRate(12.4, false, t)).toBe('12.4 requests per second');
    expect(formatDateTime('not-a-date')).toBe('—');
  });

  it('按时间戳对齐并加权聚合应用级趋势', () => {
    const trends = aggregateApplicationRedTrends([
      {
        timeseries: [
          { timestamp: 't1', request_rate: 10, error_rate: 0.1 },
          { timestamp: 't2', request_rate: 20, error_rate: 0.0 },
        ],
      },
      {
        timeseries: [
          { timestamp: 't1', request_rate: 30, error_rate: 0.2 },
          { timestamp: 't2', request_rate: 10, error_rate: 0.1 },
        ],
      },
    ]);
    expect(trends.requestRateTrend).toEqual([40, 30]);
    // t1: (10*0.1 + 30*0.2) / 40 = 0.175; t2: (20*0 + 10*0.1) / 30 ≈ 0.0333
    expect(trends.errorRateTrend[0]).toBeCloseTo(0.175);
    expect(trends.errorRateTrend[1]).toBeCloseTo(1 / 30);
  });

  it('无时序时返回空趋势', () => {
    expect(aggregateApplicationRedTrends([{ timeseries: [] }])).toEqual({
      requestRateTrend: [],
      errorRateTrend: [],
    });
  });

  it('拓扑连线展示 总数 / P95 / 错误数', () => {
    expect(formatTopologyEdgeMetrics({
      sampled_calls: 153,
      error_calls: 0,
    })).toBe('153 / — / 0');
  });

  it('有边级 P95 时放在总数和错误数中间，错误数大于 0 仍拼进同一行', () => {
    expect(formatTopologyEdgeMetrics({
      sampled_calls: 153,
      error_calls: 12,
      p95_ms: 40,
    })).toBe('153 / 40ms / 12');
  });
});
