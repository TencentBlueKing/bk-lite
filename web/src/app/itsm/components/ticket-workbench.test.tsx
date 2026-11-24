import { renderItsm as render } from '../test-utils';
import React from 'react';
import { act, cleanup, configure, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TicketWorkbench } from './ticket-workbench';
const tableProps = vi.hoisted(() => ({ current: {} as { columns: { key: string }[]; pagination: { pageSizeOptions: number[]; onChange: (page: number, size: number) => void } } }));
const api = vi.hoisted(() => ({ ready: true, searchUsers: vi.fn(), searchTicketTags: vi.fn(), ticketFilterWorkflows: vi.fn(), ticketFilterFields: vi.fn(), ticketExportFields: vi.fn(), exportTickets: vi.fn(), listTicketExports: vi.fn(), downloadTicketExport: vi.fn(), retryTicketExport: vi.fn(), listTickets: vi.fn(), centerSettings: vi.fn(), saveTicketColumns: vi.fn(), saveTicketGroup: vi.fn(), deleteTicketGroup: vi.fn(), batchOptions: vi.fn(), batchTickets: vi.fn(), portal: vi.fn(), toggleFavorite: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/link', () => ({ default: ({ children, href, onNavigate }: { children: React.ReactNode; href: string; onNavigate?: () => void }) => <a href={href} onClick={event => { event.preventDefault(); onNavigate?.(); }}>{children}</a> }));
vi.mock('@/components/custom-table', () => ({ default: (props: { columns: { key: string }[]; pagination: { pageSizeOptions: number[]; onChange: (page: number, size: number) => void }; rowSelection?: { onChange: (keys: number[]) => void }; dataSource: { id: number; title: string }[] }) => { const { rowSelection, dataSource } = props; if (!rowSelection) return <div>{dataSource.length} 条记录</div>; tableProps.current = props; return <div className="ant-table-body">{dataSource.map(item => <button key={item.id} onClick={() => rowSelection.onChange([item.id])}>{item.title}</button>)}</div>; } }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })) });
// 列配置加载后还会触发防抖查询，给并行运行时的真实异步渲染留出时间。
configure({ asyncUtilTimeout: 3000 });
afterEach(() => {
  cleanup();
  window.history.replaceState(null, '');
  window.sessionStorage.clear();
});
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(window.matchMedia).mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) as unknown as MediaQueryList);
  api.searchUsers.mockResolvedValue({ items: [{ username: 'owner', display_name: '测试提单人' }], count: 1 });
  api.ticketFilterWorkflows.mockResolvedValue({ workflows: [{ id: 4, name: "金额申请" }] });
  api.ticketFilterFields.mockResolvedValue({ workflow: { id: 4, name: "金额申请" }, fields: [{ key: "amount", label: "申请金额", type: "number", options: [] }] });
  api.ticketExportFields.mockImplementation(async ({ workflow_id }) => ({
    groups: [{ key: 'basic', label: '工单信息', columns: [{ key: 'sn', label: '单号' }, { key: 'service', label: '服务' }] }],
    default_columns: ['sn'],
    ...(workflow_id ? { workflow: { id: 4, name: '金额申请' }, fields: [{ key: 'people', type: 'multiUser', label: '联系人' }] }
    : { workflows: [{ id: 4, name: '金额申请' }] }),
  }));
  api.searchTicketTags.mockResolvedValue({ items: [{ name: '数据库' }] });
  api.centerSettings.mockResolvedValue({ columns: ['sn', 'title'], views: [] });
  api.listTickets.mockResolvedValue({ count: 1, items: [{ id: 1, sn: 'REQ1', title: '测试工单' }], can_operate: true });
  api.saveTicketColumns.mockResolvedValue({ columns: ['sn', 'title', 'status', 'creator', 'node', 'created_at'] });
  api.listTicketExports.mockResolvedValue({ count: 0, items: [] });
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

it('在分组中按流程配置动态条件并回查', async () => {
  api.saveTicketGroup.mockImplementation(async (name, filters) => ({ id: 9, name, filters }));
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  fireEvent.click(screen.getByRole('button', { name: '保存为分组' }));
  fireEvent.change(await screen.findByRole('textbox', { name: '分组名称' }), { target: { value: '金额筛选' } });
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '筛选流程' }));
  fireEvent.click(await screen.findByText('金额申请', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(await screen.findByRole('button', { name: '添加表单条件' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '表单字段 1' }));
  fireEvent.click(await screen.findByText('申请金额', { selector: '.ant-select-item-option-content' }));
  fireEvent.change(screen.getByRole('spinbutton', { name: '条件值 1' }), { target: { value: '200' } });
  fireEvent.click(screen.getByRole('button', { name: '保存分组' }));
  await waitFor(() => expect(api.saveTicketGroup).toHaveBeenCalledWith('金额筛选', expect.objectContaining({
    workflow_id: '4', form_filters: [{ key: 'amount', operator: 'eq', value: 200 }],
  })));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({
    workflow_id: '4', form_filters: [{ key: 'amount', operator: 'eq', value: 200 }],
  })));
});

it('仅向具备导出权限的账号显示导出入口', async () => {
  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  expect(screen.queryByRole('button', { name: '导出' })).toBeNull();
  api.listTickets.mockResolvedValue({ items: [{ id: 1, title: '测试工单' }], count: 1, can_export: true });
  fireEvent.click(screen.getByRole('button', { name: '刷新列表' }));
  await screen.findByRole('button', { name: '导出' });
});

it('快速提单按权限显示，打开后可筛选目录、搜索、收藏和重用服务', async () => {
  const computer = { id: 21, name: '电脑申请', description: '办公电脑', catalog_id: 2, version_id: 15 };
  const network = { id: 22, name: '网络申请', workflow_name: '网络接入审核', catalog_id: null, version_id: 17 };
  api.portal.mockResolvedValue({
    can_apply: true,
    catalogs: [{ id: 1, name: '办公服务', parent_id: null }, { id: 2, name: '设备服务', parent_id: 1 }],
    services: [computer, network],
    favorites: [],
    recents: [network],
    hots: [],
  });
  api.toggleFavorite.mockResolvedValue({ favorite: true });

  render(<TicketWorkbench />);
  await screen.findByRole('button', { name: '测试工单' });
  expect(screen.queryByRole('button', { name: '快速提单' })).toBeNull();
  api.listTickets.mockResolvedValue({ items: [{ id: 1, title: '测试工单' }], count: 1, can_apply: true });
  fireEvent.click(screen.getByRole('button', { name: '刷新列表' }));
  const quickSubmit = await screen.findByRole('button', { name: '快速提单' });
  expect(api.portal).not.toHaveBeenCalled();
  fireEvent.click(quickSubmit);

  const drawer = within(await screen.findByRole('dialog'));
  expect(drawer.getByText('快速提单')).toBeTruthy();
  await drawer.findByRole('link', { name: '电脑申请' });
  fireEvent.mouseDown(drawer.getByRole('combobox', { name: '服务目录筛选' }));
  fireEvent.click(await screen.findByText('办公服务', { selector: '.ant-select-tree-title' }));
  expect(drawer.getByRole('link', { name: '电脑申请' }).getAttribute('href')).toBe('/itsm/tickets/new?service_id=21&from=tickets');
  expect(drawer.queryByRole('link', { name: '网络申请' })).toBeNull();

  fireEvent.click(drawer.getByRole('button', { name: '收藏电脑申请' }));
  await drawer.findByRole('button', { name: '取消收藏电脑申请' });
  expect(api.toggleFavorite).toHaveBeenCalledWith(21);
  fireEvent.click(drawer.getByRole('tab', { name: '我的收藏' }));
  expect(drawer.getByRole('link', { name: '电脑申请' })).toBeTruthy();
  api.toggleFavorite.mockResolvedValueOnce({ favorite: false });
  fireEvent.click(drawer.getByRole('button', { name: '取消收藏电脑申请' }));
  await drawer.findByText('暂无收藏的服务');
  fireEvent.click(drawer.getByRole('tab', { name: '最近使用' }));
  expect(drawer.queryByRole('link', { name: '电脑申请' })).toBeNull();
  const search = drawer.getByRole('textbox', { name: '搜索服务' });
  fireEvent.change(search, { target: { value: '不存在' } });
  expect(drawer.queryByRole('link', { name: '网络申请' })).toBeNull();
  fireEvent.change(search, { target: { value: '接入审核' } });
  expect(drawer.getByRole('link', { name: '网络申请' }).getAttribute('href')).toBe('/itsm/tickets/new?service_id=22&from=tickets');
});

it('快速提单的服务加载失败后可以重试，并遵循当前提单权限', async () => {
  api.listTickets.mockResolvedValue({ items: [], count: 0, can_apply: true });
  api.portal.mockRejectedValueOnce(new Error('服务暂时不可用')).mockResolvedValue({
    can_apply: false, services: [{ id: 21, name: '电脑申请' }], catalogs: [], favorites: [], recents: [], hots: [],
  });
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '快速提单' }));
  const drawer = within(await screen.findByRole('dialog'));
  await drawer.findByText('服务暂时不可用');
  fireEvent.click(drawer.getByRole('button', { name: /重\s*试/ }));
  await drawer.findByText('你没有提单权限');
  expect(drawer.queryByRole('link', { name: '电脑申请' })).toBeNull();
});

it('提交后台导出后打开导出记录并保留当前分组范围', async () => {
  api.exportTickets.mockResolvedValue({ id: 7, status: 'pending' });
  api.listTickets.mockResolvedValue({ items: [{ id: 1, title: '测试工单' }], count: 1, can_export: true });
  render(<TicketWorkbench initialTab="following" />);
  fireEvent.click(await screen.findByRole('button', { name: '导出' }));
  const submit = await screen.findByRole<HTMLButtonElement>('button', { name: '提交导出' });
  await waitFor(() => expect(submit.disabled).toBe(false));
  fireEvent.click(submit);
  await waitFor(() => expect(api.exportTickets).toHaveBeenCalledWith(expect.objectContaining({ tab: 'following' }), [], undefined, { columns: ['sn'] }));
  await screen.findByText('导出记录', { selector: '.ant-drawer-title span' });
  await waitFor(() => expect(api.listTicketExports).toHaveBeenCalledWith(1, 20));
});

it('在导出时选择系统字段和表单字段，保留原列表筛选', async () => {
  api.exportTickets.mockResolvedValue({ id: 7, status: 'pending' });
  api.listTickets.mockResolvedValue({ items: [{ id: 1, title: '测试工单' }], count: 1, can_export: true });
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '导出' }));
  expect((await screen.findByRole('checkbox', { name: '单号' }) as HTMLInputElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox', { name: '服务' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '导出表单流程' }));
  fireEvent.click(await screen.findByText('金额申请', { selector: '.ant-select-item-option-content' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '导出表单字段' }));
  fireEvent.click(await screen.findByText('联系人', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(screen.getByRole('button', { name: '提交导出' }));
  await waitFor(() => expect(api.exportTickets).toHaveBeenCalledWith(expect.objectContaining({ workflow_id: '' }), ['people'], undefined,
    { columns: ['sn', 'service'], form_workflow_id: '4' }));
});

it('提供批量审批所需的意见后才允许执行', async () => {
  api.batchOptions.mockResolvedValue({ actions: ['approve'], required_opinion_actions: ['approve'], reason: '' });
  render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('button', { name: '测试工单' }));
  const open = screen.getByRole('button', { name: '批量处理' });
  await waitFor(() => expect(open).toHaveProperty('disabled', false));
  fireEvent.click(open);
  const confirm = await screen.findByRole('button', { name: '确认执行' });
  expect(confirm).toHaveProperty('disabled', true);
  const opinion = screen.getByRole('textbox', { name: '批量操作意见' });
  fireEvent.change(opinion, { target: { value: '   ' } });
  expect(confirm).toHaveProperty('disabled', true);
  fireEvent.change(opinion, { target: { value: '  批量核验  ' } });
  fireEvent.click(confirm);
  await waitFor(() => expect(api.batchTickets).toHaveBeenCalledWith([1], 'approve', '批量核验'));
});

it('从快速提单返回工单中心时还原筛选、分组、分页与表格滚动', async () => {
  api.listTickets.mockResolvedValue({ items: [{ id: 1, sn: 'REQ1', title: '测试工单' }], count: 100, can_apply: true });
  api.portal.mockResolvedValue({
    can_apply: true, services: [{ id: 21, name: '电脑申请' }], catalogs: [], favorites: [], recents: [], hots: [],
  });
  const list = render(<TicketWorkbench />);
  fireEvent.click(await screen.findByRole('tab', { name: '我的历史' }));
  fireEvent.change(screen.getByRole('textbox', { name: '工单关键词' }), { target: { value: '返程筛选' } });
  fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  act(() => tableProps.current.pagination.onChange(2, 20));
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, q: '返程筛选' })));
  const table = list.container.querySelector('.ant-table-body')!;
  table.scrollTop = 92;
  fireEvent.click(await screen.findByRole('button', { name: '快速提单' }));
  fireEvent.click(await screen.findByRole('link', { name: '电脑申请' }));
  list.unmount();
  window.history.pushState(null, '');
  api.listTickets.mockClear();

  const restored = render(<TicketWorkbench restoreView />);
  await waitFor(() => expect(api.listTickets).toHaveBeenLastCalledWith(expect.objectContaining({ tab: 'history', q: '返程筛选', page: 2 })));
  expect(screen.getByRole('textbox', { name: '工单关键词' })).toHaveProperty('value', '返程筛选');
  await waitFor(() => expect(restored.container.querySelector('.ant-table-body')?.scrollTop).toBe(92));
});

it('英文快速提单先显示与目录同结构的加载状态再显示搜索', async () => {
  api.listTickets.mockResolvedValue({ items: [], count: 0, can_apply: true });
  const portal = { can_apply: true, services: [], catalogs: [], favorites: [], recents: [], hots: [] };
  let complete: (value: typeof portal) => void;
  api.portal.mockImplementation(() => new Promise<typeof portal>(resolve => { complete = resolve; }));
  render(<TicketWorkbench />, { locale: 'en' });
  fireEvent.click(await screen.findByRole('button', { name: 'Quick request' }));
  const dialog = within(await screen.findByRole('dialog'));
  expect(dialog.getByRole('status', { name: 'Loading services' })).toBeTruthy();
  expect(dialog.queryByRole('textbox', { name: 'Search services' })).toBeNull();
  await act(async () => complete(portal));
  await dialog.findByRole('textbox', { name: 'Search services' });
  expect(dialog.getByRole('tab', { name: 'All services' })).toBeTruthy();
  expect(dialog.getByRole('combobox', { name: 'Filter by service catalog' })).toBeTruthy();
  expect(dialog.queryByRole('status', { name: 'Loading services' })).toBeNull();
});
