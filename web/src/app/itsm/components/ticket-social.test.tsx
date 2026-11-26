import React from 'react';
import { App } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { CopyTicketNumber, TicketHeaderSocial, TicketRelations } from './ticket-social';
const api = vi.hoisted(() => ({ ready: true, searchTicketTags: vi.fn(), listFollowers: vi.fn(), listTags: vi.fn(), listRelations: vi.fn(), listTickets: vi.fn(), toggleFollow: vi.fn(), addTag: vi.fn(), removeTag: vi.fn(), addRelation: vi.fn(), removeRelation: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/link', () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  api.searchTicketTags.mockResolvedValue({ items: [] });
  api.listFollowers.mockResolvedValue({ items: [], following: false });
  api.listTags.mockResolvedValue({ items: [{ id: 4, name: '数据库' }], can_manage: false });
  api.listRelations.mockResolvedValue({ items: [{ id: 2, related_id: 3, related_sn: 'REQ3', related_title: '数据库问题', relation_type: 'related', can_remove: false }], can_manage: false });
  api.listTickets.mockResolvedValue({ items: [] });
});
it('只读用户能看标签和关联但不能修改', async () => {
  render(<><TicketHeaderSocial ticketId={1} /><TicketRelations ticketId={1} /></>);
  await screen.findByText('数据库');
  expect(await screen.findByRole('link', { name: /REQ3/ })).toBeTruthy();
  expect(screen.queryByLabelText('标签名称')).toBeNull();
  expect(screen.queryByRole('button', { name: '解除关联' })).toBeNull();
  expect(screen.queryByLabelText('搜索关联工单')).toBeNull();
});
it('关注提交明确状态并刷新按钮', async () => {
  api.toggleFollow.mockImplementation(async () => { api.listFollowers.mockResolvedValue({ items: ['我'], following: true }); });
  render(<TicketHeaderSocial ticketId={1} />);
  fireEvent.click(await screen.findByRole('button', { name: /关注工单/ }));
  await screen.findByRole('button', { name: /取消关注/ });
  expect(api.toggleFollow).toHaveBeenCalledWith(1, true);
});
it('移除标签必须确认', async () => {
  api.listTags.mockResolvedValue({ items: [{ id: 4, name: '数据库' }], can_manage: true });
  render(<TicketHeaderSocial ticketId={1} />);
  fireEvent.click(await screen.findByRole('button', { name: '移除标签 数据库' }));
  expect(api.removeTag).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole('button', { name: /OK|确\s*定/ }));
  await waitFor(() => expect(api.removeTag).toHaveBeenCalledWith(1, 4));
});
it('搜索请求当前工单的可关联候选', async () => {
  api.listRelations.mockResolvedValue({ items: [], can_manage: true });
  render(<TicketRelations ticketId={8} />);
  fireEvent.click(await screen.findByRole('button',{name:'添加关联单'}));
  await screen.findByRole('combobox', { name: '搜索关联工单' });
  await waitFor(() => expect(api.listTickets).toHaveBeenCalledWith(expect.objectContaining({ relation_for: 8, page_size: 20 })), { timeout: 2000 });
});

it('部分单号搜索展示名称与单号，选定后才可关联', async () => {
  api.listRelations.mockResolvedValue({ items: [], can_manage: true });
  api.listTickets.mockResolvedValue({ items: [{ id: 9, sn: 'REQ202611130009', title: '数据库扩容申请' }] });
  render(<TicketRelations ticketId={8} />);
  fireEvent.click(await screen.findByRole('button',{name:'添加关联单'}));
  const input = await screen.findByRole('combobox', { name: '搜索关联工单' });
  expect((screen.getByRole('button', { name: '建立关联' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(input, { target: { value: '130009' } });
  await waitFor(() => expect(api.listTickets).toHaveBeenCalledWith(expect.objectContaining({ q: '130009', relation_for: 8 })));
  fireEvent.mouseDown(input);
  fireEvent.click(await screen.findByText('数据库扩容申请', { exact: true }));
  fireEvent.click(screen.getByRole('button', { name: '建立关联' }));
  await waitFor(() => expect(api.addRelation).toHaveBeenCalledWith(8, 9));
});
it('顶部标签按钮展开输入并添加标签', async () => {
  api.listTags.mockResolvedValue({ items: [], can_manage: true });
  render(<TicketHeaderSocial ticketId={1} />);
  expect(screen.queryByLabelText('标签名称')).toBeNull();
  fireEvent.click(await screen.findByRole('button', { name: '标签' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '标签名称' }), { target: { value: '重点工单' } });
  fireEvent.click(screen.getByRole('button', { name: /添\s*加/ }));
  await waitFor(() => expect(api.addTag).toHaveBeenCalledWith(1, '重点工单', '#1677ff'));
});

it('复制完整工单号', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
  render(<App><CopyTicketNumber sn="REQ202611130001" /></App>);
  fireEvent.click(screen.getByRole('button', { name: '复制单号' }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith('REQ202611130001'));
});

it('三个快捷图标无可见文字，新标签使用选中配色', async () => {
  api.listTags.mockResolvedValue({ items: [], can_manage: true });
  render(<TicketHeaderSocial ticketId={1} sn="REQ1" />);
  const group = await screen.findByRole('group', { name: '工单快捷操作' });
  expect(group.textContent).toBe('');
  fireEvent.click(screen.getByRole('button', { name: '标签' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '标签名称' }), { target: { value: '紫色标签' } });
  fireEvent.click(screen.getByRole('button', { name: '配色 #722ed1' }));
  fireEvent.click(screen.getByRole('button', { name: /添\s*加/ }));
  await waitFor(() => expect(api.addTag).toHaveBeenCalledWith(1, '紫色标签', '#722ed1'));
});
