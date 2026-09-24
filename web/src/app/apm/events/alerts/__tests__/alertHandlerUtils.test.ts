import { describe, expect, it } from 'vitest';
import {
  canClaimOrAssignAlert,
  canCloseAlert,
  canReassignAlert,
  formatAlertHandlers,
  hasAlertHandlers,
  isHandlerLifecycleEvent
} from '../alertHandlerUtils';

describe('APM 告警处理人操作', () => {
  it('空处理人的活跃告警可认领分派，有处理人或非活跃不可', () => {
    expect(hasAlertHandlers([])).toBe(false);
    expect(canClaimOrAssignAlert('active', [])).toBe(true);
    expect(canClaimOrAssignAlert('active', [7])).toBe(false);
    expect(canClaimOrAssignAlert('closed', [])).toBe(false);
  });

  it('当前处理人的活跃告警可转派，空单或非处理人不可', () => {
    expect(canReassignAlert('active', [7], { id: 7, username: 'bob' })).toBe(true);
    expect(canReassignAlert('active', [7], { id: 8, username: 'alice' })).toBe(false);
    expect(canReassignAlert('active', [], { id: 7, username: 'bob' })).toBe(false);
    expect(isHandlerLifecycleEvent('reassigned')).toBe(true);
    expect(isHandlerLifecycleEvent('triggered')).toBe(false);
  });

  it('空处理人或当前处理人可以关闭，其他处理人的告警不可关闭', () => {
    expect(canCloseAlert([], { id: 7, username: 'bob' })).toBe(true);
    expect(canCloseAlert([7], { id: 7, username: 'bob' })).toBe(true);
    expect(canCloseAlert(['bob'], { id: 8, username: 'bob' })).toBe(true);
    expect(canCloseAlert([8], { id: 7, username: 'bob' })).toBe(false);
  });

  it('优先用 handlers_display', () => {
    expect(formatAlertHandlers([7], ['处理人甲(bob)'])).toBe('处理人甲(bob)');
    expect(formatAlertHandlers([7], [])).toBe('7');
    expect(formatAlertHandlers([], [])).toBe('--');
  });
});
