import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';
const api = vi.hoisted(() => ({ ready: true, listDataTables: vi.fn(), listDataRows: vi.fn(), deleteDataRows: vi.fn(), getDataTable: vi.fn(), saveDataTable: vi.fn(), saveDataRow: vi.fn(), createDataTable: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/itsm/components/itsm-list-table', () => ({ default: ({ dataSource, columns }: { dataSource: { id: number; name?: string; data?: Record<string, unknown> }[]; columns: { key: string; dataIndex?: string; render?: (v: unknown, row: unknown) => React.ReactNode }[] }) => <div role="table">{dataSource.map(row => <div key={row.id}>{columns.map(col => <span key={col.key}>{col.render ? col.render(undefined, row) : row.name}</span>)}</div>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  api.listDataTables.mockResolvedValue({ items: [{ id: 1, name: '设备表', key: 'assets' }] });
  api.listDataRows.mockResolvedValue({ items: [{ id: 1, data: { name: '服务器一' } }], can_edit: false });
});
it('点击数据立即打开弹窗，并允许只读查看', async () => {
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: 'itsm.admin.data' }));
  const dialog = await screen.findByRole('dialog');
  expect(await within(dialog).findByText('服务器一')).toBeTruthy();
  expect(within(dialog).queryByRole('button', { name: 'itsm.common.delete' })).toBeNull();
});
it('加载失败保留弹窗并可重试', async () => {
  api.listDataRows.mockRejectedValueOnce(new Error('读取失败'));
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: 'itsm.admin.data' }));
  expect(await within(await screen.findByRole('dialog')).findByText('读取失败')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  expect(await screen.findByText('服务器一')).toBeTruthy();
});
it('关闭弹窗后未完成的请求不能重新打开弹窗', async () => {
  let finish!: (value: unknown) => void;
  api.listDataRows.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: 'itsm.admin.data' }));
  await screen.findByRole('dialog');
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  await waitFor(() => { finish({ items: [{ id: 1, data: { name: '延迟数据' } }], can_edit: true }); });
  expect(screen.queryByText('延迟数据')).toBeNull();
});
it('全局导入只有一个入口，行内只展示数据、字段和导出', async () => {
  api.listDataTables.mockResolvedValue({ items: [{ id: 1, name: '设备表', key: 'assets' }], can_add: true, can_edit: true });
  render(<Page />);
  expect(await screen.findByRole('button', { name: /导\s*入/ })).toBeTruthy();
  expect(screen.queryByText('导入为新表')).toBeNull();
  expect(screen.getByRole('button', { name: '字段配置' })).toBeTruthy();
});

it('新增与编辑数据提交类型化值，并使用字段显示名称', async () => {
  api.listDataRows.mockResolvedValue({ items: [{id:1,data:{amount:12}}], fields:[{key:'amount',label:'金额',type:'number'}],can_edit:true });
  api.saveDataRow.mockResolvedValue({id:2});
  render(<Page />);
  fireEvent.click(await screen.findByRole('button',{name:'itsm.admin.data'}));
  fireEvent.click(await screen.findByRole('button',{name:'新增数据'}));
  fireEvent.change(screen.getByRole('spinbutton',{name:'金额'}),{target:{value:'25'}});
  fireEvent.click(screen.getByRole('button',{name:/确\s*定|OK/}));
  await waitFor(()=>expect(api.saveDataRow).toHaveBeenCalledWith(1,{amount:25},undefined));
  fireEvent.click(await screen.findByRole('button',{name:/编\s*辑/}));
  fireEvent.change(screen.getByRole('spinbutton',{name:'金额'}),{target:{value:'30'}});
  fireEvent.click(screen.getByRole('button',{name:/确\s*定|OK/}));
  await waitFor(()=>expect(api.saveDataRow).toHaveBeenCalledWith(1,{amount:30},1));
});
