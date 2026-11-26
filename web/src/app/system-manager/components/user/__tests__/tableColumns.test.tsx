import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createUserTableColumns } from '../tableColumns';
import type { UserDataType } from '@/app/system-manager/types/user';

vi.mock('antd', () => {
  const Container = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    Button: Container,
    Popconfirm: Container,
    Tooltip: Container,
    Menu: Object.assign(Container, { Item: Container }),
    Dropdown: ({ children, overlay }: { children?: React.ReactNode; overlay?: React.ReactNode }) => (
      <div>{children}<div data-testid="role-overflow">{overlay}</div></div>
    ),
  };
});
vi.mock('@/components/permission', () => ({ default: () => null }));
vi.mock('@/components/ellipsis-with-tooltip', () => ({ default: () => null }));
vi.mock('@/components/icon', () => ({ default: () => null }));

const translate = (key: string, fallback?: string, values?: { app: string }) => {
  const templates: Record<string, string> = {
    'system.role.moduleAdminName': '{app}管理员',
    'system.role.moduleAuditorName': '{app}审计员',
  };
  return (templates[key] || fallback || key).replace('{app}', values?.app || '');
};

function renderRoles(roles: UserDataType['roles'], groupRoles: string[] = []) {
  const columns = createUserTableColumns({
    t: translate,
    appIconMap: new Map(),
    appDisplayNameMap: new Map([
      ['cmdb', '配置平台'], ['monitor', '监控中心'], ['custom-app', '真实自定义应用'],
    ]),
    onOpenDetail: vi.fn(), onEditUser: vi.fn(), onOpenPasswordModal: vi.fn(),
    onDeleteUser: vi.fn(), onChangeUserStatus: vi.fn(), convertToLocalizedTime: vi.fn(),
  });
  const column = columns.find((item) => 'dataIndex' in item && item.dataIndex === 'roles');
  if (!column || !('render' in column) || !column.render) throw new Error('Missing roles column');
  const user: UserDataType = {
    key: '1', username: 'module-user', email: '', display_name: '', groups: [],
    roles, group_role_list: groupRoles,
  };
  const cell = column.render(undefined, user, 0);
  if (!React.isValidElement(cell)) throw new Error('Missing roles cell');
  render(cell);
}

afterEach(cleanup);

describe('user role labels', () => {
  it('formats visible module roles with app display names but preserves ordinary roles', () => {
    renderRoles([
      { id: '1', name: 'cmdb@@module_admin' },
      { id: '2', name: 'cmdb@@normal' },
      { id: '3', name: 'monitor@@module_auditor' },
    ]);
    expect(screen.getByText('配置平台管理员, normal')).toBeTruthy();
    expect(screen.getByText('监控中心审计员')).toBeTruthy();
    expect(screen.queryByText(/module_admin|module_auditor/)).toBeNull();
  });

  it('formats the encoded string roles returned by the user-list API', () => {
    const payload = JSON.parse('{"roles":["cmdb@@module_admin","cmdb@@normal","monitor@@module_auditor"]}');
    renderRoles(payload.roles);
    expect(screen.getByText('配置平台管理员, normal')).toBeTruthy();
    expect(screen.getByText('监控中心审计员')).toBeTruthy();
    expect(screen.queryByText(/module_admin|module_auditor/)).toBeNull();
  });

  it('uses the same formatting in the overflow menu, including inherited roles', () => {
    renderRoles([
      { id: '1', name: 'cmdb@@normal' },
      { id: '2', name: 'monitor@@normal' },
      { id: '3', name: 'custom-app@@module_admin' },
    ], ['custom-app@@module_auditor']);
    const overflow = within(screen.getByTestId('role-overflow'));
    expect(overflow.getByText('真实自定义应用管理员')).toBeTruthy();
    expect(overflow.getByText('真实自定义应用审计员')).toBeTruthy();
    expect(screen.queryByText(/module_admin|module_auditor/)).toBeNull();
  });
});
