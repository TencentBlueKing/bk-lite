import React from 'react';
import { cleanup, configure, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TicketWorkbench } from './ticket-workbench';
const tableProps = vi.hoisted(() => ({ current: {} as { columns: { key: string }[]; pagination: { pageSizeOptions: number[]; onChange: (page: number, size: number) => void } } }));
const api = vi.hoisted(() => ({ ready: true, searchUsers: vi.fn(), searchTicketTags: vi.fn(), listTickets: vi.fn(), centerSettings: vi.fn(), saveTicketColumns: vi.fn(), saveTicketGroup: vi.fn(), deleteTicketGroup: vi.fn(), batchOptions: vi.fn(), batchTickets: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/link', () => ({ default: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }));
vi.mock('@/components/custom-table', () => ({ default: (props: { columns: { key: string }[]; pagination: { pageSizeOptions: number[]; onChange: (page: number, size: number) => void }; rowSelection: { onChange: (keys: number[]) => void }; dataSource: { id: number; title: string }[] }) => { tableProps.current = props; const { rowSelection, dataSource } = props; return <div>{dataSource.map(item => <button key={item.id} onClick={() => rowSelection.onChange([item.id])}>{item.title}</button>)}</div>; } }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });
// 列配置加载后还会触发防抖查询，给并行运行时的真实异步渲染留出时间。
configure({ asyncUtilTimeout: 3000 });
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(window.matchMedia).mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) as unknown as MediaQueryList);
  api.searchUsers.mockResolvedValue({ items: [{ username: 'owner', display_name: '测试提单人' }], count: 1 });
  api.searchTicketTags.mockResolvedValue({ items: [{ name: '数据库' }] });
  api.centerSettings.mockResolvedValue({ columns: ['sn', 'title'], views: [] });
  api.listTickets.mockResolvedValue({ count: 1, items: [{ id: 1, sn: 'REQ1', title: '测试工单' }], can_operate: true });
  api.saveTicketColumns.mockResolvedValue({ columns: ['sn', 'title', 'status', 'creator', 'node', 'created_at'] });
  api.batchOptions.mockResolvedValue({ actions: ['follow', 'unfollow'], reason: '' });
  api.batchTickets.mockResolvedValue({ items: [{ id: 1, ok: false, error: '当前节点不支持' }] });
});
it('读取个人列并按需查询，切换历史分组清空选择', async () => {
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '测试工单' }));
  await screen.findByText('已选 1 项');
  await waitFor(() => expect(api.listTickets).toHaveBeenCalledWith(expect.objectContaining({ fields: 'sn,title' })));
  fireEvent.click(screen.getByRole('tab', { name: '我的历史' }));
  await waitFor(() => expect(api.listTickets).toHaveBeenCalledWith(expect.objectContaining({ tab: 'history' })));
  expect(screen.queryByText('已选 1 项')).toBeNull();
});
it('恢复默认列保存到服务端', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.click(screen.getByRole('button', { name: /展示字段/ }));
  fireEvent.click(await screen.findByRole('button', { name: '恢复默认' }));
  await waitFor(() => expect(api.saveTicketColumns).toHaveBeenCalledWith(null));
});
it('批量操作先确认并显示每单失败原因', async () => {
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '测试工单' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '批量处理' }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: '批量处理' }));
  expect(api.batchTickets).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole('button', { name: '确认执行' }));
  await screen.findByText('当前节点不支持');
  expect(api.batchTickets).toHaveBeenCalledWith([1], 'follow', '');
});
it('保存筛选分组后切回仍使用相同条件', async () => {
  api.saveTicketGroup.mockResolvedValue({ id: 5, name: '我的数据库', filters: { q: '数据库', tab: 'all' } });
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.change(screen.getByRole('textbox', { name: '工单关键词' }), { target: { value: '数据库' } });
  fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  fireEvent.click(screen.getByRole('button', { name: '保存为分组' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '分组名称' }), { target: { value: '我的数据库' } });
  fireEvent.click(screen.getByRole('button', { name: '保存分组' }));
  await waitFor(() => expect(api.saveTicketGroup).toHaveBeenCalledWith('我的数据库', expect.objectContaining({ q: '数据库' })));
  await screen.findByRole('tab', { name: /我的数据库/ });
  fireEvent.click(screen.getByRole('tab', { name: '我的待办' }));
  fireEvent.click(screen.getByRole('tab', { name: /我的数据库/ }));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ q: '数据库', tab: 'all' })));
});
it('配置加载失败可重试且不覆盖个人配置', async () => {
  api.centerSettings.mockRejectedValueOnce(new Error('读取配置失败'));
  render(<TicketWorkbench />);
  await screen.findByText('读取配置失败');
  expect(api.listTickets).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await screen.findByRole('button', { name: '测试工单' });
});
it('删除其他分组不会切换当前选中分组', async () => {
  api.centerSettings.mockResolvedValue({ columns: ['sn', 'title'], views: [{ id: 3, name: '临时分组', filters: { tab: 'all' } }] });
  api.deleteTicketGroup.mockResolvedValue({});
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.click(screen.getByRole('tab', { name: '我的历史' }));
  fireEvent.click(screen.getByRole('button', { name: '删除分组 临时分组' }));
  fireEvent.click(await screen.findByRole('button', { name: /OK|确\s*定/ }));
  await waitFor(() => expect(screen.queryByRole('tab', { name: /临时分组/ })).toBeNull());
  expect(screen.getByRole('tab', { name: '我的历史' }).getAttribute('aria-selected')).toBe('true');
});

it('通过用户组件和标签下拉选择筛选条件', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.click(screen.getByRole('button', { name: '更多筛选' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '筛选提单人' }));
  fireEvent.click(await screen.findByText('测试提单人 (owner)'));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '筛选标签' }));
  fireEvent.click(await screen.findByText('数据库', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ creator: 'owner', tag: '数据库' })));
});

it('批量处理入口常驻，未勾选时不可执行', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  expect((screen.getByRole('button', { name: '批量处理' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '测试工单' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '批量处理' }) as HTMLButtonElement).disabled).toBe(false));
});

it('混选节点仅显示服务端允许操作并提示原因', async () => {
  api.batchOptions.mockResolvedValue({ actions: ['follow', 'unfollow'], reason: '请选择相同节点' });
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '测试工单' }));
  await screen.findByText('请选择相同节点');
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '批量操作类型' }));
  expect(screen.queryByText('审批通过')).toBeNull();
  expect(api.batchOptions).toHaveBeenCalledWith([1]);
});

it('支持四档分页，切换条数回到首页并清空勾选', async () => {
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '测试工单' }));
  expect(tableProps.current.pagination.pageSizeOptions).toEqual([10, 20, 50, 100]);
  const { act } = await import('@testing-library/react');
  act(() => tableProps.current.pagination.onChange(2, 20));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 20 })));
  act(() => tableProps.current.pagination.onChange(2, 100));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 100 })));
  expect(screen.queryByText('已选 1 项')).toBeNull();
});

it('分组使用加号入口，操作搜索栏不展示重复统计', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  expect(screen.queryByText(/共.*张工单/)).toBeNull();
  expect(screen.getByRole('button', { name: '保存为分组' }).textContent).toBe('');
  expect(screen.getByRole('button', { name: '更多筛选' })).toBeTruthy();
});

it('字段设置不占独立空白列', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  expect(tableProps.current.columns.map(column => column.key)).toEqual(['sn', 'title']);
  fireEvent.click(screen.getByRole('button', { name: '展示字段' }));
  await screen.findByText('个性化展示字段');
});

it('新增分组带入未查询条件，保存后立即按弹窗条件刷新', async () => {
  api.saveTicketGroup.mockImplementation(async (name, filters) => ({ id: 8, name, filters }));
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.change(screen.getByRole('textbox', { name: '工单关键词' }), { target: { value: '未应用条件' } });
  fireEvent.click(screen.getByRole('button', { name: '保存为分组' }));
  expect((await screen.findByRole('textbox', { name: '分组关键词' }) as HTMLInputElement).value).toBe('未应用条件');
  fireEvent.change(screen.getByRole('textbox', { name: '分组关键词' }), { target: { value: '数据库' } });
  fireEvent.change(screen.getByRole('textbox', { name: '分组名称' }), { target: { value: '数据库分组' } });
  fireEvent.click(screen.getByRole('button', { name: '保存分组' }));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ q: '数据库', page: 1 })));
  expect(api.saveTicketGroup).toHaveBeenCalledWith('数据库分组', expect.objectContaining({ q: '数据库' }));
  fireEvent.click(screen.getByRole('button', { name: /重\s*置/ }));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ q: '数据库' })));
});
