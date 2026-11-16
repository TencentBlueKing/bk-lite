import React from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { App } from 'antd';
import type { FormInstance } from 'antd';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useServiceDraft } from './use-service-draft';
const api = vi.hoisted(() => ({ ready: true, portal: vi.fn(), ticketForm: vi.fn(), loadDrafts: vi.fn(), saveDraft: vi.fn(), createTicket: vi.fn(), useService: vi.fn() }));
const router = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
const form = { setFieldsValue: vi.fn(), validateFields: vi.fn(), getFieldsValue: vi.fn() };
const wrapper = ({ children }: { children: React.ReactNode }) => <App>{children}</App>;
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  api.portal.mockResolvedValue({ can_apply: true, services: [{ id: 1, name: '金额申请', version_id: 2 }] });
  api.ticketForm.mockResolvedValue({ schema: { fields: [{ key: 'title', required: true }] }, field_perm: { secret: 'read' }, creator: 'owner', workflow_name: '流程', nodes: [], edges: [] });
  api.loadDrafts.mockResolvedValue({ items: { '1': { title: '已保存的草稿' } } });
  api.saveDraft.mockResolvedValue({}); api.useService.mockResolvedValue({}); api.createTicket.mockResolvedValue({ id: 90 });
  form.validateFields.mockResolvedValue({ title: '申请', amount: 30 }); form.getFieldsValue.mockReturnValue({ title: '' });
});
it('打开详情新建态读取服务草稿但不创建空单', async () => {
  const { result } = renderHook(() => useServiceDraft(1, form as unknown as FormInstance), { wrapper });
  await waitFor(() => expect(result.current.ticket?.title).toBe('金额申请'));
  expect(api.ticketForm).toHaveBeenCalledWith(2, 1);
  expect(result.current.ticket?.form_data).toEqual({ title: '已保存的草稿' });
  expect(api.createTicket).not.toHaveBeenCalled();
  await act(() => result.current.save(false));
  expect(api.saveDraft).toHaveBeenCalledWith({ service_id: 1, form_data: { title: '' } });
  expect(form.validateFields).not.toHaveBeenCalled();
});
it('提交校验后创建并跳转真实详情，重复提交不重复建单', async () => {
  const { result } = renderHook(() => useServiceDraft(1, form as unknown as FormInstance), { wrapper });
  await waitFor(() => expect(result.current.ticket).not.toBeNull());
  await act(() => result.current.save(true));
  expect(api.createTicket).toHaveBeenCalledWith({ service_id: 1, workflow_version_id: 2, form_data: { title: '申请', amount: 30 } });
  expect(router.replace).toHaveBeenCalledWith('/itsm/tickets/90');
  await act(() => result.current.save(true));
  expect(api.createTicket).toHaveBeenCalledTimes(1);
});
it('必填项不通过不能创建工单', async () => {
  form.validateFields.mockRejectedValue({ errorFields: ['title'] });
  const { result } = renderHook(() => useServiceDraft(1, form as unknown as FormInstance), { wrapper });
  await waitFor(() => expect(result.current.ticket).not.toBeNull());
  await act(() => result.current.save(true));
  expect(api.createTicket).not.toHaveBeenCalled();
});
it('不可见服务拒绝读取表单及创建', async () => {
  api.portal.mockResolvedValue({ services: [] });
  const { result } = renderHook(() => useServiceDraft(1, form as unknown as FormInstance), { wrapper });
  await waitFor(() => expect(result.current.error).toContain('没有申请权限'));
  expect(api.ticketForm).not.toHaveBeenCalled();
  expect(api.createTicket).not.toHaveBeenCalled();
});
