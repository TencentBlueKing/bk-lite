import { describe, expect, it } from 'vitest';
import {
  aggregateConditionText,
  aggregateDetailRows,
  aggregateNoDataMessage,
  formatAggregateMetric,
  readAggregateConditions,
  readEventAggregateResult,
} from '../aggregateConditionHit';

const t = (key: string, _defaultMessage?: string, values?: { count?: number | string }) => {
  if (key === 'log.event.noDataWindowLine') {
    return `本窗无日志，上一窗 ${values?.count} 条`;
  }
  return key;
};

describe('聚合命中区', () => {
  it('从事件原文读出 conditions，旧结果没有 conditions 时不渲染', () => {
    const withConditions = readEventAggregateResult({
      raw_data: {
        data: {
          aggregate_result: {
            conditions: [{ func: 'count', current: 180, baseline: 120, value: 50, matched: true }],
          },
        },
      },
    });
    expect(readAggregateConditions(withConditions)?.[0].current).toBe(180);
    expect(readAggregateConditions({ count: 180 })).toBeNull();
    expect(readEventAggregateResult({ raw_data: { data: [{ _msg: 'old' }] } })).toBeNull();
  });

  it('条件列用函数词条，浮点保留两位', () => {
    expect(
      aggregateConditionText(
        {
          func: 'ratio',
          field: '_msg',
          params: { filter: 'message:ERR' },
          compare: { kind: 'absolute' },
        },
        t,
      ),
    ).toBe('log.event.funcRatio(message:ERR)');
    expect(formatAggregateMetric(6.875984)).toBe('6.88');
    expect(formatAggregateMetric(8886)).toBe('8886');
    expect(formatAggregateMetric(null)).toBe('—');
  });

  it('详情原始日志优先样本，没有样本时退回聚合行', () => {
    expect(aggregateDetailRows({ samples: [{ _msg: 'hit' }], query_result: { count__msg: 1 } })).toEqual([
      { _msg: 'hit' },
    ]);
    expect(aggregateDetailRows({ samples: [], query_result: { count__msg: 1 } })).toEqual([{ count__msg: 1 }]);
    expect(aggregateDetailRows({ no_data: true })).toEqual([]);
  });

  it('无数据文案带上一窗条数', () => {
    expect(
      aggregateNoDataMessage(
        { no_data: true, count: 0, baseline: { values: { count__msg: 6 } } },
        t,
      ),
    ).toBe('本窗无日志，上一窗 6 条');
    expect(aggregateNoDataMessage({ count: 3 }, t)).toBeNull();
  });
});
