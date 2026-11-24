import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConfigProvider } from 'antd';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import HandlerGroupsPage from './page';

const api = vi.hoisted(() => ({
  ready: true,
  listHandlerGroups: vi.fn(),
  createHandlerGroup: vi.fn().mockResolvedValue({ id: 1 }),
}));

vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('../../components/user-selector', () => ({ UserSelector: () => <div /> }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

beforeAll(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }));
});

describe('处理组负责人', () => {
  it('重命名处理组时保留已选负责人', async () => {
    api.listHandlerGroups.mockResolvedValue({ can_edit: true, items: [{ id: 1, name: '网络组', members: ['one', 'two'], leaders: ['two'] }] });
    render(<ConfigProvider theme={{ token: { motion: false } }}><HandlerGroupsPage /></ConfigProvider>);
    fireEvent.click(await screen.findByText('网络组'));
    fireEvent.change(screen.getByPlaceholderText('itsm.admin.groupName'), { target: { value: '运维组' } });
    fireEvent.click(screen.getByRole('button', { name: /^(保\s*存)$/i }));
    await waitFor(() => expect(api.createHandlerGroup).toHaveBeenCalledWith({ id: 1, name: '运维组', members: ['one', 'two'], leaders: ['two'] }));
  });

  it('只读人员只能查看处理组', async () => {
    api.listHandlerGroups.mockResolvedValue({ can_edit: false, items: [{ id: 1, name: '网络组', members: ['one', 'two'], leaders: ['two'] }] });
    render(<HandlerGroupsPage />);
    expect(await screen.findByText('网络组')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /新\s*建/ })).toBeNull();
  });
});
