import { describe, expect, it } from 'vitest';
import {
  aggregateNoDataMessage,
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
