import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { NodeSettings } from './node-settings';
import type { CanvasNodeData } from '../constants/demo-flow';
const listWorkflowHandlerGroupOptions = vi.hoisted(() => vi.fn().mockResolvedValue({ items: [{ id: 7, name: '服务台' }] }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, listWorkflowHandlerGroupOptions }) }));
vi.mock('./user-selector', () => ({
  UserSelector: ({ ariaLabel, onChange }: { ariaLabel?: string; onChange: (value: string[]) => void }) => (
    ariaLabel ? <button onClick={() => onChange(['alice'])}>{ariaLabel}</button> : <span>用户选择器</span>
  ),
}));
vi.mock('./form-renderer',()=>({FormRenderer:({fieldPerm}:{fieldPerm:Record<string,string>})=><div data-testid="preview">{JSON.stringify(fieldPerm)}</div>}));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
const fields=[{key:'section',label:'申请信息',type:'section',children:[{key:'title',label:'申请标题',type:'input'}]}];
const data:CanvasNodeData={label:'审批',nodeType:'approval',assignees:[],orSign:false};
it('节点配置分处理人操作和字段，并显示字段分组', async()=>{
  render(<NodeSettings data={data} fields={fields} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'配置节点'}));
  expect(await screen.findByText('用户选择器')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab',{name:'字段配置'}));
  expect(await screen.findByText('申请信息')).toBeTruthy();
  expect(screen.getByRole('combobox',{name:'申请信息状态'})).toBeTruthy();
});
it('节点预览使用配置的权限，审批节点不提供提交按钮',async()=>{
  render(<NodeSettings data={{...data,fieldPerm:{title:'read'},actions:['approve','reject']}} fields={fields} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'预览该节点'}));
  const dialog=await screen.findByRole('dialog');
  expect(within(dialog).getByTestId('preview').textContent).toContain('"title":"read"');
  expect(within(dialog).queryByRole('button',{name:/提\s*交/})).toBeNull();
  expect(within(dialog).getByRole('button',{name:/同\s*意/})).toBeTruthy();
});
it('取消最后一个操作仍提交空操作列表',async()=>{
  const change=vi.fn();
  render(<NodeSettings data={{...data,actions:['approve']}} fields={fields} onChange={change} />);
  fireEvent.click(screen.getByRole('button',{name:'配置节点'}));
  fireEvent.click(await screen.findByRole('tab',{name:'操作按钮'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'同意'}));
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'应用到流程草稿'}));
  await waitFor(()=>expect(change).toHaveBeenCalledWith(expect.objectContaining({actions:[]})));
});
it('转交启用时才显示范围，指定人员后才应用配置', async () => {
  const change = vi.fn();
  render(<NodeSettings data={{ ...data, actions: ['approve'] }} fields={fields} onChange={change} />);
  fireEvent.click(screen.getByRole('button', { name: '配置节点' }));
  fireEvent.click(await screen.findByRole('tab', { name: '操作按钮' }));
  expect(screen.queryByRole('group', { name: '转交范围' })).toBeNull();
  fireEvent.click(screen.getByRole('checkbox', { name: '转交' }));
  expect(screen.getByRole('radio', { name: '本组织不限' })).toHaveProperty('checked', true);
  expect(listWorkflowHandlerGroupOptions).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('radio', { name: '指定人员' }));
  const apply = screen.getByRole('button', { name: '应用到流程草稿' });
  expect(screen.getByText('请至少选择一名可接收转交的人员')).toBeTruthy();
  expect(apply).toHaveProperty('disabled', true);
  fireEvent.click(screen.getByRole('button', { name: '可接收转交的人员' }));
  fireEvent.click(apply);
  await waitFor(() => expect(change).toHaveBeenCalledWith(expect.objectContaining({
    actions: expect.arrayContaining(['approve', 'transfer']),
    transferScope: { type: 'users', users: ['alice'] },
  })));
});
it('指定处理组时才读取组名，应用保存组 ID', async () => {
  const change = vi.fn();
  render(<NodeSettings data={{ ...data, actions: ['transfer'] }} fields={fields} onChange={change} />);
  fireEvent.click(screen.getByRole('button', { name: '配置节点' }));
  fireEvent.click(await screen.findByRole('tab', { name: '操作按钮' }));
  fireEvent.click(screen.getByRole('radio', { name: '指定处理组' }));
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '可接收转交的处理组' }));
  fireEvent.click(await screen.findByText('服务台'));
  fireEvent.click(screen.getByRole('button', { name: '应用到流程草稿' }));
  await waitFor(() => expect(change).toHaveBeenCalledWith(expect.objectContaining({
    transferScope: { type: 'handler_groups', group_ids: [7] },
  })));
});
it('旧的缺项转交配置可在抽屉里修正', async () => {
  const change = vi.fn();
  const node: CanvasNodeData = { ...data, actions: ['transfer'], transferScope: { type: 'handler_groups' } as CanvasNodeData['transferScope'] };
  render(<NodeSettings data={node} fields={fields} onChange={change} />);
  fireEvent.click(screen.getByRole('button', { name: '配置节点' }));
  fireEvent.click(await screen.findByRole('tab', { name: '操作按钮' }));
  expect(screen.getByText('请至少选择一个可接收转交的处理组')).toBeTruthy();
  const apply = screen.getByRole('button', { name: '应用到流程草稿' });
  expect(apply).toHaveProperty('disabled', true);
  fireEvent.click(screen.getByRole('radio', { name: '本组织不限' }));
  fireEvent.click(apply);
  await waitFor(() => expect(change).toHaveBeenCalledWith(expect.objectContaining({ transferScope: null })));
});
