import { describe, expect, it } from 'vitest';
import { StrategyFields } from '@/app/log/types/event';
import {
  aggregateTemplateVariables,
  buildStrategyPayload,
  getDefaultShowFields,
  hasBackfillGap,
  hasIncompleteCondition,
  hasNonNumericThreshold,
  isNumericCompare,
  normalizeCondition,
  readPolicyTriggerCount,
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

describe('告警名称变量', () => {
  it('按条件序号给出占比键，变化量给出对照键', () => {
    expect(
      aggregateTemplateVariables([
        { func: 'count', field: '_msg', compare: { kind: 'percent', to: 'previous_window' } },
        { func: 'count_uniq', field: 'host_name' },
        { func: 'ratio', field: '_msg', params: { filter: 'message:ERR' } },
        { func: 'count_delta', field: '_msg' },
      ])
    ).toEqual([
      '${count}',
      '${baseline_count__msg}',
      '${count_uniq_host_name}',
      '${ratio_2}',
      '${count_delta}',
      '${previous_count}',
    ]);
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

  it('透传 compare、params 和 trigger_count，不写 no_data', () => {
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
    expect(payload.alert_condition?.no_data).toBeUndefined();
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

  it('固定 7 天对照读成可改的天数', () => {
    expect(
      normalizeCondition({
        func: 'sum',
        field: 'bytes',
        op: '>',
        value: '1',
        compare: { kind: 'percent', to: 'offset_7d' },
      })
    ).toEqual({
      func: 'sum',
      field: 'bytes',
      op: '>',
      value: '1',
      compare: { kind: 'percent', to: 'offset_days', offset: 7 },
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

  it('读入时回填连续满足次数，缺省和越界都是 1', () => {
    expect(readPolicyTriggerCount({ rule: { mode: 'and', conditions: [], trigger_count: 3 } })).toBe(3);
    expect(readPolicyTriggerCount({})).toBe(1);
    expect(readPolicyTriggerCount({ rule: { mode: 'and', conditions: [], trigger_count: 6 } })).toBe(1);
  });

  it('关键字策略也写入连续满足次数', () => {
    const payload = buildStrategyPayload(
      {
        alert_type: 'keyword',
        query: 'error',
        trigger_count: 2,
        schedule: 5,
        period: 5,
      } as StrategyFields,
      {
        unit: 'min',
        periodUnit: 'min',
        channelList: [],
        conditions: [],
        term: 'and',
        isEdit: false,
      }
    );
    expect(payload.alert_condition?.rule?.trigger_count).toBe(2);
  });

  it('数值比较只认数值函数和非当前值', () => {
    expect(isNumericCompare('count', 'absolute')).toBe(false);
    expect(isNumericCompare('count', 'percent')).toBe(true);
    expect(isNumericCompare('count_rate', 'absolute')).toBe(true);
  });

  it('数值比较的非数字阈值会被标出，当前值文本和负数不会', () => {
    expect(
      hasNonNumericThreshold([
        {
          func: 'count',
          field: '_msg',
          op: '>',
          value: 'abc',
          compare: { kind: 'percent', to: 'previous_window' },
        },
      ])
    ).toBe(true);
    expect(
      hasNonNumericThreshold([{ func: 'count', field: '_msg', op: '=', value: 'error' }])
    ).toBe(false);
    expect(
      hasNonNumericThreshold([
        {
          func: 'count',
          field: '_msg',
          op: '>',
          value: '-30',
          compare: { kind: 'percent', to: 'previous_window' },
        },
      ])
    ).toBe(false);
  });

  it('检测频率超过周期补扫上限时才提示缺口', () => {
    expect(hasBackfillGap(1, 'day', 5, 'min')).toBe(true);
    expect(hasBackfillGap(5, 'min', 5, 'min')).toBe(false);
    expect(hasBackfillGap(1, 'hour', 5, 'min')).toBe(true);
    expect(hasBackfillGap(50, 'min', 5, 'min')).toBe(false);
  });

  it('展示字段把 timestamp 和 message 固定在前面', () => {
    expect(getDefaultShowFields(['level', 'message'])).toEqual(['timestamp', 'message', 'level']);
  });
});
