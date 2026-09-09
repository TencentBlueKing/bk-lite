import { describe, expect, it } from 'vitest';
import {
  canClaimOrAssignAlert,
  formatAlertHandlers,
  hasAlertHandlers
} from '../alertHandlerUtils';

describe('APM 告警处理人操作', () => {
  it('空处理人的活跃告警可认领分派，有处理人或非活跃不可', () => {
    expect(hasAlertHandlers([])).toBe(false);
    expect(canClaimOrAssignAlert('active', [])).toBe(true);
    expect(canClaimOrAssignAlert('active', [7])).toBe(false);
    expect(canClaimOrAssignAlert('closed', [])).toBe(false);
  });

  it('优先用 handlers_display', () => {
    expect(formatAlertHandlers([7], ['处理人甲(bob)'])).toBe('处理人甲(bob)');
    expect(formatAlertHandlers([7], [])).toBe('7');
    expect(formatAlertHandlers([], [])).toBe('--');
  });
});
