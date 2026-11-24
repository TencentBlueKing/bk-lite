import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ChangePage from './page';
import DutyPage from '../duty/page';

const api = vi.hoisted(() => ({ ready: true, listResources: vi.fn(), createResource: vi.fn(), updateResource: vi.fn(), deleteResource: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('../../components/user-selector', () => ({
  UserSelector: ({ ariaLabel, value, onChange }: { ariaLabel: string; value: string[]; onChange: (value: string[]) => void }) => (
    <input aria-label={ariaLabel} value={value.join(',')} onChange={event => onChange(event.target.value ? event.target.value.split(',') : [])} />
  ),
}));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  api.createResource.mockResolvedValue({ id: 2 });
  api.updateResource.mockResolvedValue({ id: 1 });
});

const mutable = { can_add: true, can_edit: true, can_delete: true };
const save = () => fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));

it('变更窗口保存带时区的时间范围，逆序输入留在弹窗', async () => {
  api.listResources.mockResolvedValue({ items: [], ...mutable });
  render(<IntlProvider locale="zh-CN"><ChangePage /></IntlProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '新建变更窗口' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '  例行维护  ' } });
  fireEvent.change(screen.getByLabelText('开始时间'), { target: { value: '2026-12-01T10:00' } });
  fireEvent.change(screen.getByLabelText('结束时间'), { target: { value: '2026-12-01T09:00' } });
  save();
  expect((await screen.findByRole('alert')).textContent).toContain('结束时间须晚于开始时间');
  expect(api.createResource).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText('结束时间'), { target: { value: '2026-12-01T11:00' } });
  save();
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith('changes', {
    name: '例行维护', start_at: new Date('2026-12-01T10:00').toISOString(), end_at: new Date('2026-12-01T11:00').toISOString(),
  }));
});

it('值班管理可以编辑日期和人员，列表按值班日期搜索', async () => {
  api.listResources.mockResolvedValue({ items: [{ id: 1, name: '白班', day: '2026-12-01', members: ['alice'] }], ...mutable });
  render(<IntlProvider locale="zh-CN"><DutyPage /></IntlProvider>);
  await screen.findByText('alice');
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '2026-12-02' } });
  expect(screen.queryByText('alice')).toBeNull();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '2026-12-01' } });
  fireEvent.click(screen.getByRole('button', { name: '白班' }));
  fireEvent.change(screen.getByLabelText('值班日期'), { target: { value: '2026-12-02' } });
  fireEvent.change(screen.getByRole('textbox', { name: '值班人员' }), { target: { value: 'alice,bob' } });
  save();
  await waitFor(() => expect(api.updateResource).toHaveBeenCalledWith('duties', 1, { name: '白班', day: '2026-12-02', members: ['alice', 'bob'] }));
});

it('只读值班角色只能查看排班和人员', async () => {
  api.listResources.mockResolvedValue({ items: [{ id: 1, name: '只读排班', day: '2026-12-01', members: ['alice'] }], can_add: false, can_edit: false, can_delete: false });
  render(<IntlProvider locale="zh-CN"><DutyPage /></IntlProvider>);
  await screen.findByText('只读排班');
  expect(screen.getByText('alice')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /^新建/ })).toBeNull();
  expect(screen.queryByRole('button', { name: '编辑' })).toBeNull();
  expect(screen.queryByRole('button', { name: '更多操作' })).toBeNull();
});
