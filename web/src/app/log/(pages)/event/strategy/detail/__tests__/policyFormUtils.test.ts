import { describe, expect, it } from 'vitest';
import { StrategyFields } from '@/app/log/types/event';
import {
  buildStrategyPayload,
  hasIncompleteCondition,
  normalizeCondition,
  readPolicyNoData,
  pruneNoticeUsers,
  seedNoticeUsersFromHandlers,
} from '../policyFormUtils';

describe('日志策略处理人候选', () => {
  it('组织变更后剔除越界处理人', () => {
    expect(
      pruneNoticeUsers([1, 2], [{ id: 1, username: 'bob' }])
    ).toEqual([1]);
  });

  it('通知人为空且处理人非空时带入处理人，用户已填则不覆盖', () => {
    expect(seedNoticeUsersFromHandlers([], [11])).toEqual([11]);
    expect(seedNoticeUsersFromHandlers([9], [11])).toBeNull();
  });
});

describe('聚合条件函数', () => {
  it('透传 count_rate 与 count_delta，字段保持 _msg', () => {
    const payload = buildStrategyPayload(
      {
        alert_type: 'aggregate',
        query: 'level:error',
        group_by: ['service'],
        show_fields: ['message'],
        schedule: { type: 'min', value: 5 },
        period: { type: 'min', value: 5 },
      } as StrategyFields,
      {
        unit: 'min',
        periodUnit: 'min',
        channelList: [],
        conditions: [
          { func: 'count_rate', field: '_msg', op: '>', value: '0.5' },
          { func: 'count_delta', field: '_msg', op: '>', value: '50' },
        ],
        term: 'and',
        isEdit: false,
      }
    );

    expect(payload.alert_condition?.rule?.conditions).toEqual([
      { func: 'count_rate', field: '_msg', op: '>', value: '0.5' },
      { func: 'count_delta', field: '_msg', op: '>', value: '50' },
    ]);
  });

  it('速率和变化量不要求字段，计数仍要求字段', () => {
    expect(
      hasIncompleteCondition([{ func: 'count_rate', field: null, op: '>', value: '0.5' }])
    ).toBe(false);
    expect(
      hasIncompleteCondition([{ func: 'count_delta', field: '', op: '<', value: '-100' }])
    ).toBe(false);
    expect(
      hasIncompleteCondition([{ func: 'count', field: null, op: '>', value: '1' }])
    ).toBe(true);
  });

  it('透传 compare、params、no_data 和 trigger_count', () => {
    const payload = buildStrategyPayload(
      {
        alert_type: 'aggregate',
        query: 'level:error',
        group_by: ['service'],
        show_fields: ['message'],
        schedule: { type: 'min', value: 5 },
        period: { type: 'min', value: 5 },
        trigger_count: 3,
        no_data: { enabled: true, level: 'warning' },
      } as StrategyFields,
      {
        unit: 'min',
        periodUnit: 'min',
        channelList: [],
        conditions: [
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '50',
            compare: { kind: 'percent', to: 'offset_24h' },
            params: { quantile: 0.95 },
          },
        ],
        term: 'and',
        isEdit: false,
      }
    );

    expect(payload.alert_condition?.rule?.conditions).toEqual([
      {
        func: 'count',
        field: '_msg',
        op: '>',
        value: '50',
        compare: { kind: 'percent', to: 'offset_24h' },
        params: { quantile: 0.95 },
      },
    ]);
    expect(payload.alert_condition?.rule?.trigger_count).toBe(3);
    expect(payload.alert_condition?.no_data).toEqual({ enabled: true, level: 'warning' });
  });

  it('count_delta 读入显示为计数、变化量和上一窗', () => {
    expect(
      normalizeCondition({ func: 'count_delta', field: 'host', op: '>', value: '50' })
    ).toEqual({
      func: 'count',
      field: '_msg',
      op: '>',
      value: '50',
      compare: { kind: 'delta', to: 'previous_window' },
      params: {},
    });
  });

  it('变化率缺对照、分位缺分位、占比缺分子筛选时视为未完成', () => {
    expect(
      hasIncompleteCondition([
        { func: 'count', field: '_msg', op: '>', value: '50', compare: { kind: 'percent' } },
      ])
    ).toBe(true);
    expect(
      hasIncompleteCondition([
        { func: 'quantile', field: 'duration', op: '>', value: '1', params: {} },
      ])
    ).toBe(true);
    expect(
      hasIncompleteCondition([
        { func: 'ratio', field: '_msg', op: '>', value: '5', params: { filter: '' } },
      ])
    ).toBe(true);
    expect(
      hasIncompleteCondition([
        {
          func: 'count',
          field: '_msg',
          op: '>',
          value: '50',
          compare: { kind: 'delta', to: 'previous_window' },
        },
      ])
    ).toBe(false);
  });

  it('读入时回填无数据开关，缺省关闭', () => {
    expect(readPolicyNoData({ no_data: { enabled: true, level: 'warning' } })).toEqual({
      enabled: true,
      level: 'warning',
    });
    expect(readPolicyNoData({})).toEqual({ enabled: false });
    expect(readPolicyNoData({ no_data: { enabled: false } })).toEqual({ enabled: false });
  });
});
