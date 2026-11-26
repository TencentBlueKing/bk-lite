import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import ScriptLibrary from '../script-library/page';
import PlaybookLibrary from '../playbook-library/page';

const api = vi.hoisted(() => ({
  getScriptList: vi.fn(),
  getPlaybookList: vi.fn(),
  getScriptSelectionIds: vi.fn(),
  getPlaybookSelectionIds: vi.fn(),
  batchDeleteScripts: vi.fn(),
  batchDeletePlaybook: vi.fn(),
  exportScripts: vi.fn(),
}));
const permissions = new Set<string>();
let group = 1;
vi.mock('@/app/job/api', () => ({ default: () => api }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/utils/request', () => ({ default: () => ({ isLoading: false }) }));
vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ selectedGroup: { id: group }, userId: 'admin', flatGroups: [] }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: (keys: string[]) => keys.some(key => permissions.has(key)) }),
}));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _fallback?: string, values?: { count?: number }) =>
      values?.count === undefined ? key : key + ' ' + values.count,
  }),
}));
vi.mock('@/components/script-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
vi.mock('@/components/markdown', () => ({ default: () => null }));
vi.mock('@/app/job/components/template-version-drawer', () => ({ default: () => null }));
vi.mock('@/components/operate-modal', async importOriginal => {
  const { default: OperateModal } = await importOriginal<typeof import('@/components/operate-modal')>();
  return { default: (props: React.ComponentProps<typeof OperateModal>) => props.open ? <OperateModal {...props} /> : null };
});

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  window.matchMedia = query => ({
    matches: false, media: query, onchange: null, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  });
});
beforeEach(() => {
  vi.resetAllMocks();
  group = 1;
  permissions.clear();
  permissions.add('View');
  const page = { items: [{ id: 7, name: 'deploy-web', team_name: ['Operations'] }], count: 1 };
  api.getScriptList.mockResolvedValue(page);
  api.getPlaybookList.mockResolvedValue(page);
});
afterEach(cleanup);

const batchButton = () => screen.getByRole('button', { name: 'common.batchOperation' });
const findAction = (name: string) => screen.findByRole('menuitem', { name });

async function selectItem(name = 'deploy-web') {
  const row = (await screen.findByText(name)).closest('tr');
  if (!row) throw new Error('Missing library row');
  fireEvent.click(within(row).getByRole('checkbox'));
}

describe('模板库批量操作', () => {
  it('将脚本包导入导出移入菜单，未选择时仍可导入', async () => {
    permissions.add('Add');
    render(<ScriptLibrary />);
    await screen.findByText('deploy-web');
    expect(batchButton().compareDocumentPosition(screen.getByRole('button', { name: /common.new/ })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('button', { name: /job.batch(Import|Export)Scripts/ })).toBeNull();
    fireEvent.click(batchButton());
    expect((await findAction('job.batchExportScripts')).getAttribute('aria-disabled')).toBe('true');
    expect((await findAction('job.targetOrganizations.title')).getAttribute('aria-disabled')).toBe('true');
    expect((await findAction('common.batchDelete')).getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(await findAction('job.batchImportScripts'));
    expect(await screen.findByRole('dialog', { name: /job.importScriptsTitle/ })).toBeTruthy();
  });

  it('导出跨页选中的全部脚本且使用已生效的搜索条件', async () => {
    api.getScriptList.mockResolvedValue({ items: [{ id: 7, name: 'deploy-web', team_name: [] }], count: 21 });
    const ids = Array.from({ length: 21 }, (_, index) => index + 1);
    api.getScriptSelectionIds.mockResolvedValue({ ids });
    api.exportScripts.mockRejectedValue(new Error('offline'));
    render(<ScriptLibrary />);
    await screen.findByText('deploy-web');
    expect(batchButton()).toHaveProperty('disabled', true);
    const search = screen.getByPlaceholderText('common.search');
    fireEvent.change(search, { target: { value: 'deploy' } });
    fireEvent.keyDown(search, { key: 'Enter', code: 'Enter', keyCode: 13 });
    await waitFor(() => expect(api.getScriptList).toHaveBeenCalledWith({ page: 1, page_size: 20, name: 'deploy' }));
    await screen.findByText('deploy-web');
    fireEvent.change(search, { target: { value: 'unapplied' } });
    fireEvent.click(screen.getByRole('button', { name: 'job.targetOrganizations.selectionOptions' }));
    fireEvent.click(await findAction('job.targetOrganizations.selectAll 21'));
    await waitFor(() => expect(batchButton()).toHaveProperty('disabled', false));
    expect(api.getScriptSelectionIds.mock.calls).toEqual([[{ name: 'deploy' }]]);
    fireEvent.click(batchButton());
    expect((await findAction('job.batchImportScripts')).getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(await findAction('job.batchExportScripts'));
    expect(api.exportScripts.mock.calls).toEqual([[ids]]);
  });

  it.each([
    { name: '脚本', Page: ScriptLibrary, deleteItems: api.batchDeleteScripts, confirm: 'job.batchDeleteScriptsConfirm 1' },
    { name: 'Playbook', Page: PlaybookLibrary, deleteItems: api.batchDeletePlaybook, confirm: 'job.batchDeletePlaybooksConfirm 1' },
  ])('$name 可以调整组织和确认删除，取消后保留勾选', async ({ Page, deleteItems, confirm }) => {
    permissions.add('Edit');
    permissions.add('Delete');
    deleteItems.mockResolvedValue({ deleted_count: 1 });
    render(<Page />);
    expect(batchButton()).toHaveProperty('disabled', true);
    await selectItem();
    expect(screen.queryByText('job.targetOrganizations.selected 1')).toBeNull();
    fireEvent.click(batchButton());
    fireEvent.click(await findAction('job.targetOrganizations.title'));
    let dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/job.targetOrganizations.selected 1/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.cancel' }));
    fireEvent.click(batchButton());
    fireEvent.click(await findAction('common.batchDelete'));
    dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(confirm)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'common.cancel' }));
    expect(deleteItems).not.toHaveBeenCalled();
    fireEvent.click(batchButton());
    fireEvent.click(await findAction('common.batchDelete'));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'common.delete' }));
    await waitFor(() => expect(batchButton()).toHaveProperty('disabled', true));
    expect(deleteItems.mock.calls).toEqual([[[7]]]);
  });

  it('切换组织后丢弃旧组织未完成的全选请求', async () => {
    permissions.add('Edit');
    api.getPlaybookList.mockResolvedValue({ items: [{ id: 7, name: 'deploy-web', team_name: [] }], count: 21 });
    let resolveIds!: (value: { ids: number[] }) => void;
    api.getPlaybookSelectionIds.mockReturnValue(new Promise(resolve => { resolveIds = resolve; }));
    const page = render(<PlaybookLibrary />);
    await screen.findByText('deploy-web');
    fireEvent.click(screen.getByRole('button', { name: 'job.targetOrganizations.selectionOptions' }));
    fireEvent.click(await findAction('job.targetOrganizations.selectAll 21'));
    group = 2;
    api.getPlaybookList.mockResolvedValue({ items: [{ id: 8, name: 'deploy-db', team_name: [] }], count: 1 });
    page.rerender(<PlaybookLibrary />);
    await screen.findByText('deploy-db');
    await act(async () => resolveIds({ ids: [7] }));
    expect(batchButton()).toHaveProperty('disabled', true);
  });
});
