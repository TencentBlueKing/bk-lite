import { describe, expect, it } from 'vitest';
import { StrategyFields } from '@/app/log/types/event';
import {
  aggregateTemplateVariables,
  buildStrategyPayload,
  getDefaultShowFields,
  hasBackfillGap,
  hasIncompleteCondition,
  hasMismatchedLevelSets,
  hasNonNumericThreshold,
  hasThresholdOrderError,
  isNumericCompare,
  normalizeCondition,
  readPolicyMinHits,
  readPolicyRecoverAfter,
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

  it('关键字策略写入命中条数，不写连续次数和自动恢复', () => {
    const payload = buildStrategyPayload(
      {
        alert_type: 'keyword',
        query: 'error',
        trigger_count: 2,
        recover_after: 3,
        recover_enabled: true,
        min_hits: 4,
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
    expect(payload.alert_condition?.rule?.min_hits).toBe(4);
    expect(payload.alert_condition?.rule?.trigger_count).toBeUndefined();
    expect(payload.alert_condition?.rule?.recover_after).toBeUndefined();
    expect(readPolicyMinHits({ rule: { mode: 'and', conditions: [], min_hits: 4 } })).toBe(4);
    expect(readPolicyMinHits({})).toBe(1);
  });

  it('聚合策略按开关写入自动恢复周期', () => {
    const enabled = buildStrategyPayload(
      {
        alert_type: 'aggregate',
        query: 'error',
        trigger_count: 2,
        recover_enabled: true,
        recover_after: 3,
        schedule: 5,
        period: 5,
      } as StrategyFields,
      {
        unit: 'min',
        periodUnit: 'min',
        channelList: [],
        conditions: [{ func: 'count', field: '_msg', op: '>', value: '1' }],
        term: 'and',
        isEdit: false,
      }
    );
    expect(enabled.alert_condition?.rule?.recover_after).toBe(3);
    expect(enabled.alert_condition?.rule?.min_hits).toBeUndefined();
    const disabled = buildStrategyPayload(
      {
        alert_type: 'aggregate',
        query: 'error',
        recover_enabled: false,
        recover_after: 3,
        schedule: 5,
        period: 5,
      } as StrategyFields,
      {
        unit: 'min',
        periodUnit: 'min',
        channelList: [],
        conditions: [{ func: 'count', field: '_msg', op: '>', value: '1' }],
        term: 'and',
        isEdit: false,
      }
    );
    expect(disabled.alert_condition?.rule?.recover_after).toBeNull();
    expect(readPolicyRecoverAfter({ rule: { mode: 'and', conditions: [], recover_after: 3 } })).toBe(3);
    expect(readPolicyRecoverAfter({})).toBeNull();
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

  it('传入策略级别时把旧单阈值收成一档，不传则保持原样', () => {
    expect(
      normalizeCondition({ func: 'count', field: '_msg', op: '>', value: '10' }, 'error')
    ).toEqual({
      func: 'count',
      field: '_msg',
      op: '>',
      value: '10',
      compare: { kind: 'absolute' },
      params: {},
      thresholds: [{ level: 'error', value: '10' }],
    });
    expect(
      normalizeCondition({ func: 'count', field: '_msg', op: '>', value: '10' })
    ).toEqual({
      func: 'count',
      field: '_msg',
      op: '>',
      value: '10',
      compare: { kind: 'absolute' },
      params: {},
    });
  });

  it('阶梯按级别单调，and 的级别集合必须一致', () => {
    const descending = {
      func: 'count',
      field: '_msg',
      op: '>',
      value: '50',
      thresholds: [
        { level: 'warning', value: '50' },
        { level: 'error', value: '10' },
      ],
    };
    expect(hasThresholdOrderError([descending])).toBe(true);
    expect(hasThresholdOrderError([{
      ...descending,
      op: '<',
      thresholds: [
        { level: 'warning', value: '50' },
        { level: 'error', value: '10' },
      ],
    }])).toBe(false);
    const warningOnly = {
      func: 'count',
      field: '_msg',
      op: '>',
      value: '10',
      thresholds: [{ level: 'warning', value: '10' }],
    };
    const withCritical = {
      func: 'count',
      field: 'service',
      op: '>',
      value: '10',
      thresholds: [
        { level: 'warning', value: '10' },
        { level: 'critical', value: '30' },
      ],
    };
    expect(hasMismatchedLevelSets([warningOnly, withCritical], 'and')).toBe(true);
    expect(hasMismatchedLevelSets([warningOnly, withCritical], 'or')).toBe(false);
    expect(hasNonNumericThreshold([{ func: 'count', field: '_msg', op: '>', value: 'abc' }])).toBe(false);
  });

  it('保存时按最轻档镜像 value，并推导最高启用级别', () => {
    const payload = buildStrategyPayload(
      {
        alert_type: 'aggregate',
        alert_level: 'warning',
        query: 'level:error',
        schedule: 5,
        period: 5,
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
            value: '10',
            thresholds: [
              { level: 'critical', value: '200' },
              { level: 'warning', value: '10' },
            ],
          },
        ],
        term: 'or',
        isEdit: false,
      }
    );
    expect(payload.alert_level).toBe('critical');
    expect(payload.alert_condition?.rule?.conditions).toEqual([
      {
        func: 'count',
        field: '_msg',
        op: '>',
        value: '10',
        thresholds: [
          { level: 'warning', value: '10' },
          { level: 'critical', value: '200' },
        ],
      },
    ]);
  });
});
