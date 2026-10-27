import { describe, expect, it } from 'vitest';
import { StrategyFields } from '@/app/log/types/event';
import {
  buildStrategyPayload,
  hasIncompleteCondition,
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
});
