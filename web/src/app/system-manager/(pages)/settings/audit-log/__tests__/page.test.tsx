import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import AuditLogPage from '../page';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/system-manager/components/security/operationLogs', () => ({
  default: () => <div>operation-panel</div>,
}));

vi.mock('@/app/system-manager/components/security/loginLogs', () => ({
  default: () => <div>login-panel</div>,
}));

vi.mock('@/app/system-manager/components/security/openapiCallLogs', () => ({
  default: () => <div>openapi-panel</div>,
}));

afterEach(() => {
  cleanup();
});

describe('AuditLogPage', () => {
  it('shows API call logs as the third audit tab', () => {
    render(<AuditLogPage />);
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabs).toEqual([
      'system.security.operationLogs',
      'system.security.loginLogs',
      'system.security.apiCallLogs',
    ]);
  });
});
