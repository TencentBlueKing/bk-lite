import React from 'react';
import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Page from './page';
const api = vi.hoisted(() => ({ ready: true, listWorkflows: vi.fn(), listWorkflowVersions: vi.fn(), enableWorkflowVersion: vi.fn(), importWorkflow: vi.fn(), duplicateWorkflow: vi.fn(), push: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key === "itsm.design.copyFlow" ? "复制为新流程" : key }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  api.listWorkflows.mockResolvedValue({ items: [{ id: 1, name: '采购流程', key: 'purchase', current_version_id: 99, current_version_no: 2 }], can_add: true, can_edit: true, can_publish: true });
  api.listWorkflowVersions.mockResolvedValue({ items: [{ id: 100, version_no: 3, is_published: false, is_current: false, ticket_count: 0 }, {id:99,version_no:2,is_published:true,is_current:true,ticket_count:4}, {id:98,version_no:1,is_published:true,is_current:false,ticket_count:2}] });
});
it('导入只有全局入口，操作使用有名称的图标按钮，展示业务版本号', async () => {
  render(<Page />); await screen.findByText('采购流程');
  expect(screen.getAllByRole('button',{name:'导入'})).toHaveLength(1);
  expect(screen.queryByText('导入为新流程')).toBeNull();
  expect(screen.getByText('V2')).toBeTruthy();
  expect(screen.getByRole('button',{name:'设计'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'更多操作'}));
  expect(await screen.findByRole('menuitem',{name:'export 导出'})).toBeTruthy();
});
it('版本弹窗区分草稿与历史，切换后刷新当前状态', async () => {
  api.enableWorkflowVersion.mockImplementation(async () => { api.listWorkflowVersions.mockResolvedValue({items:[{id:98,version_no:1,is_published:true,is_current:true,ticket_count:2}]}); });
  render(<Page />); fireEvent.click(await screen.findByRole('button',{name:'版本管理'}));
  const dialog = await screen.findByRole('dialog');
  expect(await within(dialog).findByText('草稿')).toBeTruthy();
  expect(within(dialog).getAllByRole('button',{name:'启用此版本'})).toHaveLength(1);
  fireEvent.click(within(dialog).getByRole('button',{name:'启用此版本'}));
  fireEvent.click(await screen.findByText('确认启用'));
  await within(dialog).findByText('当前版本');
  expect(api.enableWorkflowVersion).toHaveBeenCalledWith(1,98);
});
it('只读用户不显示新增、导入和设计操作', async () => {
  api.listWorkflows.mockResolvedValue({items:[{id:1,name:'只读流程',key:'read'}],can_add:false,can_edit:false,can_publish:false});
  render(<Page />);await screen.findByText('只读流程');
  expect(screen.queryByRole('button',{name:'导入'})).toBeNull();
  expect(screen.queryByRole('button',{name:'设计'})).toBeNull();
});
it('发布状态按当前启用版本分组，与关键词共同筛选并回到首页', async () => {
  api.listWorkflows.mockResolvedValue({items:[
    ...Array.from({length:21},(_,i)=>({id:i+1,name:`采购流程${i+1}`,key:`purchase_${i+1}`,current_version_id:99,current_version_no:2})),
    {id:22,name:'草稿流程',key:'draft',current_version_id:null},
  ],can_add:false,can_edit:false});
  render(<Page />); await screen.findByText('采购流程1');
  fireEvent.click(screen.getByTitle('2'));
  expect(screen.getByText('草稿流程')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'已发布'}));
  expect(screen.getByText('采购流程1')).toBeTruthy();
  expect(screen.queryByText('草稿流程')).toBeNull();
  fireEvent.change(screen.getByRole('searchbox',{name:'搜索流程'}),{target:{value:'draft'}});
  expect(screen.queryByText('采购流程1')).toBeNull();
  fireEvent.click(screen.getByRole('tab',{name:'未发布'}));
  expect(screen.getByText('草稿流程')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'新建流程'})).toBeNull();
});

it.each([[true,true,3,true],[true,false,3,false],[false,true,3,false],[true,true,null,false]])(
  '复制入口遵循新增、编辑权限及发布状态 %s/%s/%s', async (add,edit,version,visible) => {
    api.listWorkflows.mockResolvedValue({can_add:add,can_edit:edit,items:[{id:1,name:'采购流程',key:'purchase',current_version_no:1,published_version_no:version}]});
    api.duplicateWorkflow.mockResolvedValue({id:17});
    render(<Page />);
    fireEvent.click(await screen.findByRole('button',{name:'更多操作'}));
    await screen.findByRole('menuitem',{name:/导出/});
    const item = screen.queryByRole('menuitem',{name:/复制为新流程/});
    if (!visible) { expect(item).toBeNull(); return; }
    fireEvent.click(item!);
    await waitFor(() => expect(api.push).toHaveBeenCalledWith('/itsm/workflow/designer/17'));
    expect(api.duplicateWorkflow).toHaveBeenCalledWith(1,3);
  }
);
