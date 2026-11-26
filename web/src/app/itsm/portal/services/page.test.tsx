import React from 'react';
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { renderItsm } from '../../test-utils';
import ServiceManagePage from './page';

const api = vi.hoisted(() => ({
  ready: true, portal: vi.fn(), listCatalogs: vi.fn(), listWorkflows: vi.fn(),
  listWorkflowHandlerGroupOptions: vi.fn(), listServices: vi.fn(), createService: vi.fn(),
}));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
const preset = { id: 1, name: '事件管理', workflow_id: 3, is_enabled: false, requires_handler_group: true, handler_group: null, visibility: 'restricted', visible_groups: [6] };
const catalog = { items: [preset], eligible_handler_groups: [{ id: 7, name: '事件响应组' }], requires_handler_group_workflow_ids: [3] };
beforeEach(() => {
  vi.resetAllMocks();
  api.portal.mockResolvedValue({ can_manage: true });
  api.listServices.mockResolvedValue(catalog);
  api.listCatalogs.mockResolvedValue({ items: [] });
  api.listWorkflows.mockResolvedValue({ items: [{ id: 3, name: '事件受理流程', current_version_id: 12 }] });
  api.createService.mockResolvedValue({ id: 1 });
  api.listWorkflowHandlerGroupOptions.mockResolvedValue({ items: [{ id: 6, name: '申请人范围' }] });
});
it('启用服务从有效处理组选取办理人，保留独立的服务可见组', async () => {
  renderItsm(<ServiceManagePage />);
  fireEvent.click(await screen.findByRole('switch', { name: '启用事件管理' }));
  expect(api.createService).not.toHaveBeenCalled();
  const drawer = await screen.findByRole('dialog');
  const save = within(drawer).getByRole('button', { name: /保\s*存/ });
  expect(save).toHaveProperty('disabled', true);
  fireEvent.mouseDown(within(drawer).getByRole('combobox', { name: '服务处理组' }));
  fireEvent.click(await screen.findByText('事件响应组'));
  fireEvent.click(save);
  await waitFor(() => expect(api.createService).toHaveBeenCalledWith(expect.objectContaining({
    id: 1, handler_group: 7, is_enabled: true, visible_groups: [6],
  })));
});
it('没有有效处理组时显示配置路径，普通流程仍可直接启用', async () => {
  api.listServices.mockResolvedValue({ ...catalog, eligible_handler_groups: [], items: [preset,
    { id: 2, name: '通用申请', workflow_id: 4, is_enabled: false, requires_handler_group: false },
  ] });
  renderItsm(<ServiceManagePage />);
  fireEvent.click(await screen.findByRole('switch', { name: '启用通用申请' }));
  await waitFor(() => expect(api.createService).toHaveBeenCalledWith({ id: 2, is_enabled: true }));
  fireEvent.click(screen.getByRole('switch', { name: '启用事件管理' }));
  const drawer = await screen.findByRole('dialog');
  expect(within(drawer).getByText(/设置.*处理组.*有效成员/)).toBeTruthy();
  expect(within(drawer).getByRole('button', { name: /保\s*存/ })).toHaveProperty('disabled', true);
});
it('切换到使用服务处理组的流程后，允许停用保存但禁止无组启用', async () => {
  api.listServices.mockResolvedValue({ ...catalog, items: [{
    id: 2, name: '通用申请', workflow_id: 4, is_enabled: true, requires_handler_group: false, handler_group: null,
  }] });
  api.listWorkflows.mockResolvedValue({ items: [
    { id: 3, name: '事件受理流程', current_version_id: 12 }, { id: 4, name: '通用流程', current_version_id: 13 },
  ] });
  renderItsm(<ServiceManagePage />);
  fireEvent.click(await screen.findByRole('button', { name: '通用申请' }));
  const drawer = await screen.findByRole('dialog');
  expect(within(drawer).queryByRole('combobox', { name: '服务处理组' })).toBeNull();
  fireEvent.mouseDown(within(drawer).getByRole('combobox', { name: '流程' }));
  fireEvent.click(await screen.findByText('事件受理流程'));
  const save = within(drawer).getByRole('button', { name: /保\s*存/ });
  expect(save).toHaveProperty('disabled', true);
  fireEvent.click(within(drawer).getByRole('switch', { name: '启用' }));
  fireEvent.click(save);
  await waitFor(() => expect(api.createService).toHaveBeenCalledWith(expect.objectContaining({
    id: 2, workflow_id: 3, handler_group: null, is_enabled: false,
  })));
});
