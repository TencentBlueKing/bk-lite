import { describe, expect, it } from 'vitest';

import { buildSessionsListQuery, type SessionsListQueryInput } from '@/app/rum/sessions/lib/sessions-query';

const base: SessionsListQueryInput = {
  range: '24h',
  orderBy: 'impact',
  pageNo: 2,
  pageSize: 20,
  traffic: 'visitors',
  application: 'storefront',
  sessionId: '',
  userId: '',
  hasError: false,
  hasReplay: false,
  route: '',
};

describe('buildSessionsListQuery', () => {
  it('非空用户 ID 写入查询参数 userId', () => {
    const query = buildSessionsListQuery({ ...base, userId: '  user-42  ' });

    expect(query.userId).toBe('user-42');
  });

  it('空白用户 ID 不带 userId', () => {
    expect(buildSessionsListQuery({ ...base, userId: '' })).not.toHaveProperty('userId');
    expect(buildSessionsListQuery({ ...base, userId: '   ' })).not.toHaveProperty('userId');
  });

  it('会话 ID 仍写入 sessionId，且不会抄到 userId', () => {
    const query = buildSessionsListQuery({
      ...base,
      sessionId: '  sess-9  ',
      userId: '',
    });

    expect(query.sessionId).toBe('sess-9');
    expect(query).not.toHaveProperty('userId');
  });
});
