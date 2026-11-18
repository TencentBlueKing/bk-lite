import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ResourceBoard } from './resource-board';
const api = vi.hoisted(() => ({ ready: true, listResources: vi.fn(), createResource: vi.fn(), updateResource: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/components/custom-table', () => ({ default: ({ dataSource }: { dataSource: {name:string}[] }) => <div>{dataSource.map(row => <p key={row.name}>{row.name}</p>)}</div> }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  api.listResources.mockResolvedValue({items:[{id:1,name:'已有业务对象',key:'old'}]});
  api.createResource.mockResolvedValue({id:2});
});
it('公共新建打开独立表单，取消不写入，保存使用原业务接口', async () => {
  render(<ResourceBoard title="业务对象" kind="biz_objects" fields={['name','key']} />);
  await screen.findByText('已有业务对象');
  fireEvent.click(screen.getByRole('button',{name:'新建',exact:true}));
  fireEvent.change(screen.getByRole('textbox',{name:'名称'}),{target:{value:'测试对象'}});
  fireEvent.click(screen.getByRole('button',{name:/Cancel|取\s*消/}));
  expect(api.createResource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'新建',exact:true}));
  fireEvent.change(screen.getByRole('textbox',{name:'名称'}),{target:{value:'[Review] 新对象'}});
  fireEvent.change(screen.getByRole('textbox',{name:'标识'}),{target:{value:'new'}});
  fireEvent.click(screen.getByRole('button',{name:/保\s*存/}));
  await waitFor(()=>expect(api.createResource).toHaveBeenCalledWith('biz_objects',{name:'[Review] 新对象',key:'new'}));
});
it('应用列表搜索过滤且无配置的操作不会出现', async () => {
  render(<ResourceBoard title="业务对象" kind="biz_objects" fields={['name','key']} />);
  await screen.findByText('已有业务对象');
  fireEvent.change(screen.getByRole('searchbox',{name:'搜索业务对象'}),{target:{value:'不存在'}});
  expect(screen.queryByText('已有业务对象')).toBeNull();
  expect(screen.queryByRole('button',{name:'编辑'})).toBeNull();
});
