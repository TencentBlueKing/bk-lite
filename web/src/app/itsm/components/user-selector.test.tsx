import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UserSelector } from './user-selector';
const searchUsers = vi.hoisted(() => vi.fn().mockResolvedValue({ items: [{ username: 'alice', display_name: 'Alice' }], count: 1 }));
const searchTransferCandidates = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, searchUsers, searchTransferCandidates }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/components/user-avatar', () => ({ default: () => null }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('隐藏或未展开的多个用户选择器不预加载，展开后按需查询', async () => {
  render(<><UserSelector ariaLabel="委托人" /><UserSelector ariaLabel="代理人" /></>);
  expect(searchUsers).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '委托人' }));
  await screen.findByText('Alice (alice)');
  expect(searchUsers).toHaveBeenCalledExactlyOnceWith('', 1);
  fireEvent.change(screen.getByRole('combobox', { name: '委托人' }), { target: { value: 'ali' } });
  await waitFor(() => expect(searchUsers).toHaveBeenLastCalledWith('ali', 1));
});
it('已有值仍显示，禁用选择器不请求候选用户', () => {
  render(<UserSelector disabled value={['alice']} />);
  expect(screen.getByText('alice')).toBeTruthy();
  expect(searchUsers).not.toHaveBeenCalled();
});
it('展开转交人员选择器时，只查询当前工单和任务的候选人', async () => {
  searchTransferCandidates.mockResolvedValue({ items: [{ username: 'bob', display_name: 'Bob' }], count: 1 });
  render(<UserSelector ariaLabel="接收人" transfer={{ ticketId: 12, taskId: 34 }} />);
  expect(searchTransferCandidates).not.toHaveBeenCalled();
  const select = screen.getByRole('combobox', { name: '接收人' });
  fireEvent.mouseDown(select);
  await screen.findByText('Bob (bob)');
  expect(searchTransferCandidates).toHaveBeenCalledExactlyOnceWith(12, 34, '', 1);
  fireEvent.change(select, { target: { value: 'bo' } });
  await waitFor(() => expect(searchTransferCandidates).toHaveBeenLastCalledWith(12, 34, 'bo', 1));
  expect(searchUsers).not.toHaveBeenCalled();
});
it('区分转交候选为空与查询失败', async () => {
  searchTransferCandidates.mockResolvedValueOnce({ items: [], count: 0 }).mockRejectedValueOnce(new Error('网络错误'));
  render(<UserSelector ariaLabel="接收人" transfer={{ ticketId: 12, taskId: 34 }} />);
  const select = screen.getByRole('combobox', { name: '接收人' });
  fireEvent.mouseDown(select);
  expect(await screen.findByText('没有可转交的人员')).toBeTruthy();
  fireEvent.change(select, { target: { value: 'bo' } });
  expect(await screen.findByText('接收人加载失败，请重新搜索')).toBeTruthy();
});

it('已选人员不计入候选分页，滚动到末尾继续加载', async () => {
  const items = Array.from({ length: 11 }, (_, index) => ({
    username: `candidate-${index + 1}`,
    display_name: '',
  }));
  searchUsers.mockResolvedValueOnce({ items: items.slice(0, 10), count: 11 })
    .mockResolvedValueOnce({ items: items.slice(10), count: 11 });
  render(<UserSelector ariaLabel="指定人员" value={['selected']} />);
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '指定人员' }));
  const row = await screen.findByText('candidate-1');
  const list = row.closest('.rc-virtual-list-holder');
  if (!list) throw new Error('候选列表未渲染');
  fireEvent.scroll(list);
  await waitFor(() => expect(searchUsers).toHaveBeenLastCalledWith('', 2));
});
