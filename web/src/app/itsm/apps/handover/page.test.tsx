import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';

const api = vi.hoisted(() => ({
  ready: true,
  listHandovers: vi.fn(),
  searchHandoverCandidates: vi.fn(),
  createHandover: vi.fn(),
  retryHandover: vi.fn(),
  listResources: vi.fn().mockResolvedValue({ items: [] }),
}));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../../components/user-selector', () => ({
  UserSelector: ({ id, ariaLabel, value, onChange }: {
    id: string;
    ariaLabel: string;
    value: string[];
    onChange: (users: string[]) => void;
  }) => <input id={id} aria-label={ariaLabel} value={value[0] || ''} onChange={event => onChange([event.target.value])} />,
}));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });

const record = { id: 3, from_user: 'alice', to_user: 'bob', ticket_ids: [11, 12, 13], created_at: '2026-11-19T08:00:00Z' };
const results = [
  { ticket_id: 11, task_id: 101, status: 'succeeded', message: '' },
  { ticket_id: 12, task_id: 102, status: 'failed', message: '暂时无法转交' },
  { ticket_id: 13, task_id: 103, status: 'unconfirmed', message: '需要人工核对' },
];
beforeEach(() => {
  api.listHandovers.mockResolvedValue({ items: [], can_add: true, can_retry: true });
  api.searchHandoverCandidates.mockResolvedValue({ items: [], count: 0 });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('翻页和搜索候选时保留已选工单，提交后分别显示成功、失败和待核对', async () => {
  api.searchHandoverCandidates
    .mockResolvedValueOnce({ items: [{ id: 11, sn: 'REQ0011', title: '待交请求' }], count: 21 })
    .mockResolvedValueOnce({ items: [{ id: 12, sn: 'REQ0012', title: '次页请求' }], count: 21 })
    .mockResolvedValueOnce({ items: [{ id: 13, sn: 'REQ0013', title: '另一请求' }], count: 1 });
  api.createHandover.mockResolvedValue({ ...record, results });
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建交接' }));
  expect(api.searchHandoverCandidates).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('交出人'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('接收人'), { target: { value: 'bob' } });
  expect(await screen.findByRole('button', { name: '确认交接' })).toHaveProperty('disabled', true);
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0011' }));
  fireEvent.click(screen.getByTitle('2'));
  await waitFor(() => expect(api.searchHandoverCandidates).toHaveBeenLastCalledWith('alice', '', 2));
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0012' }));
  const search = screen.getByRole('searchbox', { name: '搜索待办工单' });
  fireEvent.change(search, { target: { value: '另一' } });
  fireEvent.keyDown(search, { key: 'Enter', code: 'Enter', charCode: 13 });
  await waitFor(() => expect(api.searchHandoverCandidates).toHaveBeenLastCalledWith('alice', '另一', 1));
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0013' }));
  expect(screen.getByText('已选 3 张工单')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '确认交接' }));
  await waitFor(() => expect(api.createHandover).toHaveBeenCalledWith({ from_user: 'alice', to_user: 'bob', ticket_ids: [11, 12, 13] }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('交接结果')).toBeTruthy();
  expect(within(dialog).getByText('成功')).toBeTruthy();
  expect(within(dialog).getByText('失败')).toBeTruthy();
  expect(within(dialog).getByText('待核对')).toBeTruthy();
  expect(within(dialog).getByText('需要人工核对')).toBeTruthy();
});

it('只有重试权限时可按原编号重试失败项，待核对项始终保留', async () => {
  api.listHandovers.mockResolvedValue({ items: [{ ...record, results }], can_add: false, can_retry: true });
  api.retryHandover.mockResolvedValue({ ...record, results: [{ ...results[1], status: 'succeeded' }, results[2]] });
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '查看交接结果' }));
  expect(screen.queryByRole('button', { name: '新建交接' })).toBeNull();
  fireEvent.click(await screen.findByRole('button', { name: '重试失败或待处理项' }));
  await waitFor(() => expect(api.retryHandover).toHaveBeenCalledExactlyOnceWith(3));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).queryByRole('button', { name: '重试失败或待处理项' })).toBeNull();
  expect(within(dialog).getByText('待核对')).toBeTruthy();
});

it('只读用户可以看旧记录和结果，但没有新建或重试入口', async () => {
  api.listHandovers.mockResolvedValue({ items: [record, { ...record, id: 4, results }], can_add: false, can_retry: false });
  render(<Page />);
  const actions = await screen.findAllByRole('button', { name: '查看交接结果' });
  expect(screen.queryByRole('button', { name: '新建交接' })).toBeNull();
  fireEvent.click(actions[0]);
  expect(await screen.findByText('历史记录无逐项结果')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '关闭结果' }));
  fireEvent.click(actions[1]);
  expect(await screen.findByText('需要人工核对')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '重试失败或待处理项' })).toBeNull();
});

it('跨页选中超过 50 张时禁止提交，取消最后一张后可确认', async () => {
  const candidates = Array.from({ length: 51 }, (_, index) => ({ id: index + 1, sn: `REQ${index + 1}`, title: '待交请求' }));
  api.searchHandoverCandidates.mockImplementation((_source, _q, page: number) =>
    Promise.resolve({ items: candidates.slice((page - 1) * 20, page * 20), count: candidates.length }));
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建交接' }));
  fireEvent.change(screen.getByLabelText('交出人'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('接收人'), { target: { value: 'bob' } });
  for (const page of [1, 2, 3]) {
    if (page > 1) fireEvent.click(screen.getByTitle(String(page)));
    await screen.findByRole('checkbox', { name: `选择 REQ${(page - 1) * 20 + 1}` });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all' }));
  }
  const confirm = screen.getByRole('button', { name: '确认交接' });
  expect(screen.getByText('一次最多交接 50 张工单，请减少已选工单')).toBeTruthy();
  expect(confirm).toHaveProperty('disabled', true);
  fireEvent.click(confirm);
  expect(api.createHandover).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('checkbox', { name: '选择 REQ51' }));
  expect(confirm).toHaveProperty('disabled', false);
});

it('批量交接把填写的处理意见一并提交', async () => {
  api.searchHandoverCandidates.mockResolvedValue({ items: [{ id: 11, sn: 'REQ0011', title: '待交请求' }], count: 1 });
  api.createHandover.mockResolvedValue({ ...record, results });
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建交接' }));
  fireEvent.change(screen.getByLabelText('交出人'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('接收人'), { target: { value: 'bob' } });
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0011' }));
  fireEvent.change(screen.getByLabelText('处理意见'), { target: { value: '  转交原因  ' } });
  fireEvent.click(screen.getByRole('button', { name: '确认交接' }));
  await waitFor(() => expect(api.createHandover).toHaveBeenCalledExactlyOnceWith({
    from_user: 'alice',
    to_user: 'bob',
    ticket_ids: [11],
    opinion: '转交原因',
  }));
});

it('跨页选择需要意见的工单时禁止空白提交，取消该工单后恢复选填', async () => {
  api.searchHandoverCandidates.mockImplementation((_source, _q, page: number) => Promise.resolve({
    items: page === 1
      ? [{ id: 11, sn: 'REQ0011', title: '需要意见', requires_opinion: true }]
      : [{ id: 12, sn: 'REQ0012', title: '意见可选' }],
    count: 21,
  }));
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建交接' }));
  fireEvent.change(screen.getByLabelText('交出人'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByLabelText('接收人'), { target: { value: 'bob' } });
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0011' }));
  fireEvent.click(screen.getByTitle('2'));
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0012' }));
  const input = screen.getByLabelText('处理意见');
  const confirm = screen.getByRole('button', { name: '确认交接' });
  expect(input).toHaveProperty('required', true);
  fireEvent.change(input, { target: { value: '   ' } });
  expect(confirm).toHaveProperty('disabled', true);
  fireEvent.click(screen.getByTitle('1'));
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择 REQ0011' }));
  expect(input).toHaveProperty('required', false);
  expect(confirm).toHaveProperty('disabled', false);
});
