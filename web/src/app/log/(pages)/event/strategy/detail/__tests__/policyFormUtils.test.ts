import { describe, expect, it } from 'vitest';
import { pruneNoticeUsers, seedNoticeUsersFromHandlers } from '../policyFormUtils';

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
