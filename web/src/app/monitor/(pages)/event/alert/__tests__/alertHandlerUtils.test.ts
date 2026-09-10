import { describe, expect, it } from 'vitest';
import {
  canClaimOrAssignAlert,
  formatAlertHandlers,
  hasAlertHandlers
} from '../alertHandlerUtils';

describe('监控告警处理人操作', () => {
  it('空处理人的活跃告警可认领分派，有处理人或非活跃不可', () => {
    expect(hasAlertHandlers([])).toBe(false);
    expect(canClaimOrAssignAlert('new', [])).toBe(true);
    expect(canClaimOrAssignAlert('new', [7])).toBe(false);
    expect(canClaimOrAssignAlert('closed', [])).toBe(false);
  });

  it('优先用 handlers_display，否则回退到用户列表映射', () => {
    expect(formatAlertHandlers([7], ['处理人甲(bob)'], [])).toBe('处理人甲(bob)');
    expect(
      formatAlertHandlers([7], [], [{ id: 7, username: 'bob', display_name: '处理人甲' }])
    ).toBe('处理人甲(bob)');
    expect(formatAlertHandlers([], [], [])).toBe('--');
  });
});
