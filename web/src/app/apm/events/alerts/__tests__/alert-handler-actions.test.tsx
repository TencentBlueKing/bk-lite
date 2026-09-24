import React from 'react';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import type { ApmAlert } from '@/app/apm/types';
import AlertHandlerActions from '../alert-handler-actions';

const { permissionState } = vi.hoisted(() => ({
  permissionState: {
    path: undefined as string | undefined,
    granted: ['Operate'] as string[],
  },
}));

const api = {
  closeAlert: vi.fn(),
  claimAlert: vi.fn(),
  assignAlert: vi.fn(),
  reassignAlert: vi.fn(),
  getNotificationRecipients: vi.fn(),
};

vi.mock('@/app/apm/api', () => ({ default: () => api }));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ userId: '7', username: 'apm-user' }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  default: (permissionPath?: string) => {
    permissionState.path = permissionPath;
    return {
      hasPermission: (required: string[]) =>
        required.some((item) => permissionState.granted.includes(item)),
    };
  },
}));

const alert: ApmAlert = {
  id: 'a1',
  external_id: 'alert-1',
  title: 'checkout 错误率升高',
  policy_id: 'p1',
  policy_name: '错误率',
  service_id: 's1',
  service_namespace: 'shop',
  service_name: 'checkout',
  environment: 'production',
  endpoint: 'POST /checkout',
  version: 'v2',
  metric_type: 'error_rate',
  severity: 'error',
  status: 'active',
  notification_status: 'delivered',
  current_value: '0.2',
  operator: 'sre.wang',
  started_at: '2026-08-14T02:00:00Z',
  ended_at: null,
  last_event_at: '2026-08-14T02:00:00Z',
  event_count: 1,
  events: [],
  organizations: [10],
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  permissionState.path = undefined;
  permissionState.granted = ['Operate'];
  api.closeAlert.mockResolvedValue(undefined);
  api.claimAlert.mockResolvedValue(undefined);
  api.assignAlert.mockResolvedValue(undefined);
  api.reassignAlert.mockResolvedValue(undefined);
  api.getNotificationRecipients.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const renderActions = () =>
  renderWithApmIntl(
    <AlertHandlerActions alert={alert} closeText="关闭" onSuccess={vi.fn()} />,
  );

describe('APM 告警写操作权限', () => {
  it('有 policies-Operate 时仍显示认领、分派和关闭，且可认领', async () => {
    const user = userEvent.setup();
    renderActions();

    expect(await screen.findByRole('button', { name: '认领' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '分派' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '关闭' })).not.toBeNull();
    expect(permissionState.path).toBe('/apm/events/policies');

    await user.click(screen.getByRole('button', { name: '认领' }));
    await user.click(await screen.findByRole('button', { name: /^确\s*定$/ }));
    await waitFor(() => expect(api.claimAlert).toHaveBeenCalledWith('a1'));
    expect(screen.queryByRole('button', { name: '转派' })).toBeNull();
  });

  it('当前处理人的活跃告警展示转派和关闭，不展示认领和分派', async () => {
    renderWithApmIntl(
      <AlertHandlerActions
        alert={{ ...alert, handlers: [7], handlers_display: ['Bob(bob)'] }}
        closeText="关闭"
        onSuccess={vi.fn()}
      />,
    );

    expect(await screen.findByRole('button', { name: '转派' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '关闭' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: '认领' })).toBeNull();
    expect(screen.queryByRole('button', { name: '分派' })).toBeNull();
  });

  it('不是当前处理人时不展示关闭', async () => {
    renderWithApmIntl(
      <AlertHandlerActions
        alert={{ ...alert, handlers: [8], handlers_display: ['Alice(alice)'] }}
        closeText="关闭"
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: '关闭' })).toBeNull();
    expect(screen.queryByRole('button', { name: '转派' })).toBeNull();
  });

  it('仅 events-View 时按钮不可点且不调用 claimAlert/assignAlert/closeAlert', async () => {
    permissionState.granted = ['View'];
    const user = userEvent.setup();
    renderActions();

    const claim = await screen.findByRole('button', { name: '认领' });
    const assign = screen.getByRole('button', { name: '分派' });
    const close = screen.getByRole('button', { name: '关闭' });
    expect(permissionState.path).toBe('/apm/events/policies');

    await expect(user.click(claim)).rejects.toThrow(/pointer-events/i);
    await expect(user.click(assign)).rejects.toThrow(/pointer-events/i);
    await expect(user.click(close)).rejects.toThrow(/pointer-events/i);

    expect(api.claimAlert).not.toHaveBeenCalled();
    expect(api.assignAlert).not.toHaveBeenCalled();
    expect(api.reassignAlert).not.toHaveBeenCalled();
    expect(api.closeAlert).not.toHaveBeenCalled();
    expect(api.getNotificationRecipients).not.toHaveBeenCalled();

    const denied = claim.closest('[style*="not-allowed"]');
    expect(denied).not.toBeNull();
    await user.hover(denied!);
    expect(await screen.findByRole('tooltip', { name: '无权限' })).not.toBeNull();
  });
});
