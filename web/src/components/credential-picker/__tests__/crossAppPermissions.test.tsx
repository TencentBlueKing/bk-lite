import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import CredentialPicker from '../index';

const request = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/utils/request', () => ({ default: () => request }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next-auth/react', () => ({ useSession: () => ({ status: 'authenticated', data: { user: { name: 'test' } } }) }));
vi.mock('next/navigation', () => ({ usePathname: () => '/cmdb/assetManage/autoDiscovery/collection' }));
vi.mock('@/context/permissions', () => ({ usePermissions: () => ({ permissions: {
  '/cmdb/assetManage/autoDiscovery/collection': ['View', 'Add'],
} }) }));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({
    matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }) });
});
beforeEach(() => {
  request.get.mockReset();
});
afterEach(cleanup);

it.each([
  { operations: ['View', 'Add'], add: true, view: true },
  { operations: ['View'], add: false, view: true },
  { operations: [], add: false, view: false },
])('CMDB 中凭据入口读取系统管理授权 $operations', async ({ operations, add, view }) => {
  request.get.mockImplementation(async (url: string) => {
    if (url === '/core/api/get_user_menus/') return [{ name: 'system', children: [{ name: 'credential', operation: operations }] }];
    return [];
  });
  render(<CredentialPicker category="database" type="platform_api" />);
  fireEvent.mouseDown(screen.getByRole('combobox'));
  await waitFor(() => expect(request.get).toHaveBeenCalledWith('/core/api/get_user_menus/', { params: { name: 'system-manager' } }));
  await waitFor(() => expect((screen.getByRole('button', { name: /system.credential.addCredential/ }) as HTMLButtonElement).disabled).toBe(!add));
  expect(Boolean(screen.queryByRole('button', { name: 'system.credential.openVault' }))).toBe(view);
});

it('系统权限查询失败时不借用 CMDB 新增权限，已有凭据仍可选择', async () => {
  request.get.mockImplementation(async (url: string) => {
    if (url === '/core/api/get_user_menus/') throw new Error('permission unavailable');
    if (url === '/system_mgmt/credential_type/selectable/') return [{ key: 'platform_api', categories: ['database'], fields: [] }];
    if (url === '/system_mgmt/credential/selectable/') return [{ credential_id: 'test-ref', name: '测试凭据', type: 'platform_api', fields: {} }];
    return [];
  });
  render(<CredentialPicker category="database" type="platform_api" />);
  fireEvent.mouseDown(screen.getByRole('combobox'));
  expect(await screen.findByText('测试凭据')).toBeTruthy();
  expect((screen.getByRole('button', { name: /system.credential.addCredential/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('button', { name: 'system.credential.openVault' })).toBeNull();
});
