import { describe, expect, it } from 'vitest';
import {
  canClaimOrAssignAlert,
  canCloseAlert,
  canReassignAlert,
  formatAlertHandlers,
  hasAlertHandlers,
  isLogHitEvent
} from '../alertHandlerUtils';

describe('日志告警处理人操作', () => {
  it('空处理人的活跃告警可认领分派，有处理人或非活跃不可', () => {
    expect(hasAlertHandlers([])).toBe(false);
    expect(canClaimOrAssignAlert('new', [])).toBe(true);
    expect(canClaimOrAssignAlert('new', [7])).toBe(false);
    expect(canClaimOrAssignAlert('closed', [])).toBe(false);
  });

  it('当前处理人的活跃告警可转派，空单或非处理人不可', () => {
    expect(canReassignAlert('new', [7], { id: 7, username: 'bob' })).toBe(true);
    expect(canReassignAlert('new', [7], { id: 8, username: 'alice' })).toBe(false);
    expect(canReassignAlert('new', [], { id: 7, username: 'bob' })).toBe(false);
  });

  it('空处理人或当前处理人可以关闭，其他处理人的告警不可关闭', () => {
    expect(canCloseAlert([], { id: 7, username: 'bob' })).toBe(true);
    expect(canCloseAlert([7], { id: 7, username: 'bob' })).toBe(true);
    expect(canCloseAlert(['bob'], { id: 8, username: 'bob' })).toBe(true);
    expect(canCloseAlert([8], { id: 7, username: 'bob' })).toBe(false);
  });

  it('优先用 handlers_display，否则回退到用户列表映射', () => {
    expect(formatAlertHandlers([7], ['处理人甲(bob)'], [])).toBe('处理人甲(bob)');
    expect(
      formatAlertHandlers([7], [], [{ id: 7, username: 'bob', display_name: '处理人甲' }])
    ).toBe('处理人甲(bob)');
    expect(formatAlertHandlers([], [], [])).toBe('--');
  });

  it('空 action 才是命中，认领/分派/转派/关闭不是命中', () => {
    expect(isLogHitEvent({})).toBe(true);
    expect(isLogHitEvent({ action: '' })).toBe(true);
    expect(isLogHitEvent({ action: 'claimed' })).toBe(false);
    expect(isLogHitEvent({ action: 'assigned' })).toBe(false);
    expect(isLogHitEvent({ action: 'reassigned' })).toBe(false);
    expect(isLogHitEvent({ action: 'closed' })).toBe(false);
  });
});
