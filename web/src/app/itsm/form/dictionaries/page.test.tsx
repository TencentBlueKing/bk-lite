import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';
const api = vi.hoisted(() => ({ ready: true, listDictionaries: vi.fn(), listDictionaryItems: vi.fn(), createDictionaryItem: vi.fn() }));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/itsm/components/itsm-list-table', () => ({ default: ({ dataSource, columns }: { dataSource: { id: number; name?: string; data?: Record<string, unknown> }[]; columns: { key: string; dataIndex?: string; render?: (v: unknown, row: unknown) => React.ReactNode }[] }) => <div role="table">{dataSource.map(row => <div key={row.id}>{columns.map(col => <span key={col.key}>{col.render ? col.render(undefined, row) : row.name}</span>)}</div>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  api.listDictionaries.mockResolvedValue({ items: [{id:1,name:'测试字典',key:'demo'}],can_edit:true,can_add:true });
  api.listDictionaryItems.mockResolvedValue({items:[{id:2,key:'a',label:'甲',order:0,is_enabled:true}],can_edit:true});
});
it('全局导入使用简洁文案', async () => {
  render(<Page />);
  expect(await screen.findByRole('button',{name:/导\s*入/})).toBeTruthy();
  expect(screen.queryByText('导入为新字典')).toBeNull();
});
it('弹窗管理字典项，编辑保留标识', async () => {
  render(<Page />);
  fireEvent.click(await screen.findByRole('button',{name:'itsm.admin.items'}));
  fireEvent.click(await screen.findByRole('button',{name:/编\s*辑/}));
  const input = screen.getByRole('textbox',{name:'字典项标识'}) as HTMLInputElement;
  expect(input.disabled).toBe(true);
  fireEvent.change(screen.getByRole('textbox',{name:'字典项名称'}),{target:{value:'乙'}});
  fireEvent.click(screen.getByRole('button',{name:/保\s*存/}));
  await waitFor(()=>expect(api.createDictionaryItem).toHaveBeenCalledWith(1,{id:2,key:'a',label:'乙',order:0,is_enabled:true}));
});
it('只读用户可打开字典项但不能修改', async () => {
  api.listDictionaryItems.mockResolvedValue({items:[],can_edit:false});
  render(<Page />);
  fireEvent.click(await screen.findByRole('button',{name:'itsm.admin.items'}));
  const dialog=await screen.findByRole('dialog');
  expect(within(dialog).queryByRole('button',{name:'新增字典项'})).toBeNull();
});
