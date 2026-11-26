import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import TargetPage from '../page';

const api = vi.hoisted(() => ({
  getTargetList: vi.fn(),
  getTargetSelectionIds: vi.fn(),
  batchDeleteTargets: vi.fn(),
}));
const permissions = new Set<string>();
const success = vi.hoisted(() => vi.fn());
vi.mock('antd', async (importOriginal) => ({
  ...await importOriginal<typeof import('antd')>(),
  message: { success },
}));
vi.mock('@/app/job/api', () => ({ default: () => api }));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ selectedGroup: { id: 1 }, userId: 'admin', flatGroups: [] }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: (keys: string[]) => keys.some(key => permissions.has(key)) }),
}));
vi.mock('@/utils/request', () => ({ default: () => ({ isLoading: false }) }));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _fallback?: string, values?: { count?: number }) =>
      values?.count === undefined ? key : key + ' ' + values.count,
  }),
}));
vi.mock('@/app/node-manager/api/useCloudRegionApi', () => ({
  default: () => ({ getCloudList: async () => [] }),
}));
vi.mock('@/components/operate-modal', async importOriginal => {
  const { default: OperateModal } = await importOriginal<typeof import('@/components/operate-modal')>();
  return { default: (props: React.ComponentProps<typeof OperateModal>) => props.open ? <OperateModal {...props} /> : null };
});
vi.mock('@/components/credential-picker', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  window.matchMedia = query => ({
    matches: false, media: query, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  });
});
beforeEach(() => {
  vi.resetAllMocks();
  permissions.clear();
  permissions.add('Delete');
  api.getTargetList.mockResolvedValue({
    items: [{ id: 21, name: 'worker-21', team: [1], team_name: ['Default'] }],
    count: 1,
  });
  api.getTargetSelectionIds.mockResolvedValue({ ids: [21, 31, 41] });
});
afterEach(cleanup);

async function selectRow() {
  const host = await screen.findByText('worker-21');
  const row = host.closest('tr');
  if (!row) throw new Error('Target row not found');
  fireEvent.click(within(row).getByRole('checkbox'));
}

function menuButton() {
  return screen.getByRole('button', { name: 'common.batchOperation' });
}

async function selectMenuItem(name: string) {
  fireEvent.click(menuButton());
  fireEvent.click(await screen.findByRole('menuitem', { name }));
}

describe('目标管理批量操作', () => {
  it('未选时禁用右上角下拉，勾选后可从新建左侧进入组织调整', async () => {
    permissions.delete('Delete');
    permissions.add('Edit');
    render(<TargetPage />);
    expect(menuButton()).toHaveProperty('disabled', true);
    const create = screen.getByRole('button', { name: /common\.new/ });
    expect(menuButton().compareDocumentPosition(create) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await selectRow();
    expect(menuButton()).toHaveProperty('disabled', false);
    expect(screen.queryByText('job.targetOrganizations.selected 1')).toBeNull();
    expect(screen.queryByRole('button', { name: 'job.targetOrganizations.selectionOptions' })).toBeNull();
    fireEvent.click(menuButton());
    expect((await screen.findByRole('menuitem', { name: 'common.batchDelete' })).getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(screen.getByRole('menuitem', { name: 'job.targetOrganizations.title' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/job\.targetOrganizations\.selected 1/)).toBeTruthy();
  });

  it('仅有删除权限可跨页选择，取消保留勾选，确认只提交所选 ID 并反馈服务端实删数量', async () => {
    api.getTargetList.mockResolvedValue({
      items: [{ id: 21, name: 'worker-21', team: [1], team_name: ['Default'] }],
      count: 21,
    });
    api.getTargetSelectionIds.mockResolvedValue({ ids: Array.from({ length: 21 }, (_, index) => index + 1) });
    api.batchDeleteTargets.mockResolvedValue({ deleted_count: 2 });
    render(<TargetPage />);
    await selectRow();
    fireEvent.click(screen.getByRole('button', { name: 'job.targetOrganizations.selectionOptions' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'job.targetOrganizations.selectAll 21' }));
    await waitFor(() => expect(menuButton()).toHaveProperty('disabled', false));
    fireEvent.click(menuButton());
    expect((await screen.findByRole('menuitem', { name: 'job.targetOrganizations.title' })).getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(screen.getByRole('menuitem', { name: 'common.batchDelete' }));
    const confirm = await screen.findByRole('dialog');
    expect(within(confirm).getByText('job.batchDeleteTargetsConfirm 21')).toBeTruthy();
    fireEvent.click(within(confirm).getByRole('button', { name: 'common.cancel' }));
    expect(api.batchDeleteTargets).not.toHaveBeenCalled();
    expect(menuButton()).toHaveProperty('disabled', false);
    await selectMenuItem('common.batchDelete');
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(success).toHaveBeenCalledWith('job.batchDeleteTargetsSuccess 2'));
    expect(api.batchDeleteTargets.mock.calls).toEqual([[Array.from({ length: 21 }, (_, index) => index + 1)]]);
    expect(menuButton()).toHaveProperty('disabled', true);
    expect(api.getTargetList).toHaveBeenCalledTimes(2);
  });

  it('发起跨页全选后手动取消勾选，迟到的筛选结果不覆盖新选择', async () => {
    api.getTargetList.mockResolvedValue({
      items: [{ id: 21, name: 'worker-21', team: [1], team_name: ['Default'] }],
      count: 21,
    });
    let finishRequest!: (data: { ids: number[] }) => void;
    api.getTargetSelectionIds.mockReturnValueOnce(new Promise(resolve => { finishRequest = resolve; }));
    render(<TargetPage />);
    await selectRow();
    fireEvent.click(screen.getByRole('button', { name: 'job.targetOrganizations.selectionOptions' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'job.targetOrganizations.selectAll 21' }));
    await waitFor(() => expect(api.getTargetSelectionIds).toHaveBeenCalledOnce());
    await selectRow();
    await act(async () => finishRequest({ ids: [21, 31, 41] }));
    expect(menuButton()).toHaveProperty('disabled', true);
  });

  it('删除失败后保留确认范围并允许重试', async () => {
    api.batchDeleteTargets.mockRejectedValueOnce(new Error('request failed')).mockResolvedValueOnce({ deleted_count: 1 });
    render(<TargetPage />);
    await selectRow();
    await selectMenuItem('common.batchDelete');
    const confirm = await screen.findByRole('dialog');
    const submit = within(confirm).getByRole('button', { name: 'common.delete' });
    fireEvent.click(submit);
    await waitFor(() => expect(api.batchDeleteTargets).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(within(confirm).getByRole('button', { name: 'common.cancel' })).toHaveProperty('disabled', false));
    fireEvent.click(submit);
    await waitFor(() => expect(success).toHaveBeenCalledWith('job.batchDeleteTargetsSuccess 1'));
    expect(api.batchDeleteTargets.mock.calls).toEqual([[[21]], [[21]]]);
  });
});
