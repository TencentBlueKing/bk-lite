import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import UserDetailDrawer from '../UserDetailDrawer';

const mockGetUserDetail = vi.fn();
const mockT = (
  key: string,
  defaultMessage?: string,
  params?: Record<string, string | number>,
) => {
  const template = defaultMessage || key;
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value == null ? match : String(value);
  });
};

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: mockT,
  }),
}));

vi.mock('@/app/system-manager/api/user', () => ({
  useUserApi: () => ({
    getUserDetail: mockGetUserDetail,
  }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: [{ name: 'cmdb', display_name: '配置平台' }],
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (val: string) => `loc_${val}`,
  }),
}));

describe('UserDetailDrawer', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  const mockPayload = {
    username: 'daniel',
    display_name: 'Daniel Wu',
    email: 'daniel@example.com',
    phone: '13812345678',
    status: 'normal',
    sync_source: 1,
    sync_source_name: 'AD-corp',
    last_login: '2026-10-23T10:00:00Z',
    temporary_pwd: false,
    employment_status: 'employed',
    job_level: 'P5',
    employee_no: 'EMP-001',
    job_title: 'DevOps',
    manager: 2,
    manager_display_name: 'Manager Li',
    manager_username: 'li_manager',
    groups: [
      {
        id: 101,
        name: 'Default',
        is_virtual: false,
        sync_source: null,
        data_rules: [
          { id: 1, name: '主机资源查看范围', app: 'cmdb' },
        ],
      },
      {
        id: 102,
        name: 'SyncedGroup',
        sync_source: 1,
        data_rules: [],
      },
    ],
    effective_roles: [
      {
        id: 201,
        name: 'admin',
        app: 'cmdb',
        sources: [
          { kind: 'direct' },
          { kind: 'group', group_id: 101, group_name: 'Default' },
        ],
      },
    ],
  };

  it('shows a layout skeleton while the detail request is pending', () => {
    mockGetUserDetail.mockReturnValue(new Promise(() => undefined));
    render(
      <UserDetailDrawer
        open={true}
        userId="1"
        onClose={vi.fn()}
      />
    );
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByText('Daniel Wu')).toBeNull();
  });

  it('renders user details matching card sections and allows toggling mask and group collapse', async () => {
    mockGetUserDetail.mockResolvedValue(mockPayload);

    render(
      <UserDetailDrawer
        open={true}
        userId="1"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Daniel Wu').length).toBeGreaterThanOrEqual(1);
    });

    // 状态徽章与来源
    expect(screen.getAllByText(/AD-corp/).length).toBeGreaterThanOrEqual(1);

    // 默认脱敏检查
    expect(screen.queryByText('dan***@example.com')).not.toBeNull();
    expect(screen.queryByText('138****5678')).not.toBeNull();

    // 点击眼睛切换查看明文
    const buttons = screen.getAllByRole('button');
    const eyeButtons = buttons.filter((btn) => btn.querySelector('.anticon-eye'));
    expect(eyeButtons.length).toBeGreaterThanOrEqual(1);

    expect(eyeButtons[0].getAttribute('aria-label')).toBe('system.user.detail.showSecret');
    fireEvent.click(eyeButtons[0]);
    expect(screen.queryByText('daniel@example.com')).not.toBeNull();

    // 第一个组织默认展开，显示其数据权限
    const groupButton = screen.getByRole('button', { name: /Default/ });
    expect(groupButton.getAttribute('aria-expanded')).toBe('true');
    expect(screen.queryByText('主机资源查看范围')).not.toBeNull();

    // 点击第一个组织头部进行收起
    fireEvent.click(groupButton);
    expect(groupButton.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('主机资源查看范围')).toBeNull();

    // 角色信息展示，组织继承标出具体组织
    expect(screen.queryByText('admin')).not.toBeNull();
    expect(screen.queryByText('Inherited from Default')).not.toBeNull();
  });
});
