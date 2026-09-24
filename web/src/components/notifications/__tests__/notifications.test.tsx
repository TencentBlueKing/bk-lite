import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { vi } from 'vitest';

import Notifications from '..';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  del: vi.fn(),
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/utils/request', () => ({
  default: () => ({ get: mocks.get, post: mocks.post, del: mocks.del }),
  isSilentRequestError: () => false,
}));
vi.mock('@/context/client', () => ({ useClientData: () => ({ clientData: [{ name: 'workflow-orchestration', display_name: '编排中心', icon: 'workflow-icon', is_build_in: true }] }) }));
vi.mock('@/hooks/useLocalizedTime', () => ({ useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value }) }));
vi.mock('@/utils/sessionExpiry', () => ({ isSessionExpiredState: () => false }));
vi.mock('@/components/icon', () => ({ default: () => <span data-testid="notification-icon" /> }));

describe('顶部通知', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })),
    });
  });

  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    mocks.del.mockReset();
    mocks.push.mockReset();
    mocks.post.mockResolvedValue({});
    mocks.get.mockImplementation((url: string) => {
      if (url.includes('/unread_count/')) return Promise.resolve({ count: 1 });
      return Promise.resolve({
        count: 1,
        items: [{
          id: 1,
          notification_time: '2026-09-15T01:00:00Z',
          app_module: 'workflow-orchestration',
          content: '待审批：发布确认',
          is_read: false,
          target_url: '/workflow-orchestration/executions?scope=mine',
        }],
      });
    });
  });

  it('保留原通知样式和两个分类，展示应用名并跳转待我审批页签', async () => {
    render(<IntlProvider locale="zh-CN" messages={{
      'common.notification': '通知',
      'common.unreadNotifications': '未读通知',
      'common.allNotifications': '所有通知',
      'common.markAllAsRead': '全部已读',
    }}><Notifications /></IntlProvider>);

    fireEvent.click(screen.getByLabelText('通知'));

    expect(await screen.findByRole('tab', { name: /未读通知/ })).not.toBeNull();
    expect(screen.getByRole('tab', { name: '所有通知' })).not.toBeNull();
    expect(screen.queryByRole('tab', { name: /待办/ })).toBeNull();
    expect(screen.getByText('编排中心')).not.toBeNull();
    expect(screen.queryByText('workflow-orchestration')).toBeNull();
    const notificationContent = await screen.findByText('待审批：发布确认');
    const notificationCard = notificationContent.closest('.group');
    expect(notificationCard?.className).toContain('border-[var(--color-border)]');
    expect(notificationCard?.className).toContain('py-3');
    expect(notificationCard?.className).not.toContain('first:pt-0');
    fireEvent.click(notificationContent);

    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/console_mgmt/notifications/1/mark_as_read/'));
    expect(mocks.push).toHaveBeenCalledWith('/workflow-orchestration/executions?scope=mine');
  });
});
