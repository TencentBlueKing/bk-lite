import { describe, expect, it } from 'vitest';
import { pruneNoticeUsers, seedNoticeUsersFromHandlers } from '../strategyDetailUtils';

describe('策略处理人候选', () => {
  it('组织变更后剔除越界处理人', () => {
    expect(
      pruneNoticeUsers([1, 2, 'alice'], [
        { id: 1, username: 'bob' },
        { id: 9, username: 'alice' },
      ])
    ).toEqual([1, 'alice']);
  });

  it('通知人为空且处理人非空时带入处理人，已有通知人或空处理人不补', () => {
    expect(seedNoticeUsersFromHandlers([], [7, 8])).toEqual([7, 8]);
    expect(seedNoticeUsersFromHandlers([3], [7, 8])).toBeNull();
    expect(seedNoticeUsersFromHandlers([], [])).toBeNull();
  });
});
