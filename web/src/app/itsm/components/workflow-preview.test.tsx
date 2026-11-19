import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { WorkflowPreview } from './workflow-preview';
import type { DesignNode } from '../constants/demo-flow';
vi.mock('./form-renderer',()=>({FormRenderer:({fieldPerm}: {fieldPerm:Record<string,string>})=><div data-testid="permissions">{JSON.stringify(fieldPerm)}</div>}));
Object.defineProperty(window,'matchMedia',{writable:true,value:()=>({matches:false,addListener:vi.fn(),removeListener:vi.fn()})});
afterEach(cleanup);
it('默认预览提单节点，切换节点使用对应字段权限和按钮',()=>{
  render(<WorkflowPreview schema={{version:1,fields:[]}} design={{nodes:[{id:'s',type:'submit',name:'申请',field_perm:{amount:'edit'},actions:['submit']},{id:'a',type:'approval',name:'审批',field_perm:{amount:'read'},actions:['approve']}],edges:[]}} />);
  expect(screen.getByTestId('permissions').textContent).toContain('edit');
  fireEvent.click(screen.getByRole('button',{name:'预览审批'}));
  expect(screen.getByTestId('permissions').textContent).toContain('read');
  expect(screen.getByText('同意')).toBeTruthy();
  expect(screen.getByText('仅预览配置，不会创建工单或执行流程。')).toBeTruthy();
});
it('手动触发显示人工确认表单，子流程提交由引擎执行',()=>{
  render(<WorkflowPreview schema={{version:1,fields:[]}} design={{nodes:[{id:'m',type:'manual_trigger',name:'手动触发',field_perm:{amount:'read'},actions:['submit']},{id:'c',type:'subprocess_submit',name:'提交子流程'}],edges:[]}} />);
  expect(screen.getByTestId('permissions').textContent).toContain('read');
  fireEvent.click(screen.getByRole('button',{name:'预览提交子流程'}));
  expect(screen.queryByTestId('permissions')).toBeNull();
});

it('切换节点时预览该节点的处理意见要求', () => {
  render(<WorkflowPreview schema={{ version: 1, fields: [] }} design={{ nodes: [
    { id: 's', type: 'submit', name: '申请', actions: ['submit'] },
    { id: 'a', type: 'approval', name: '审批', actions: ['approve'], required_opinion_actions: ['approve'] },
  ], edges: [] }} />);
  expect(screen.queryByText('同意前需填写处理意见。')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '预览审批' }));
  expect(screen.getByText('同意前需填写处理意见。')).toBeTruthy();
});

it('按保存的顺序预览已启用按钮和自定义名称', () => {
  render(<WorkflowPreview schema={{ version: 1, fields: [] }} design={{ nodes: [{
    id: 'a', type: 'approval', name: '审批', actions: ['approve', 'reject'], required_opinion_actions: ['approve'],
    action_display: [{ action: 'reject', label: '不予受理' }, { action: 'return', label: '不可见的操作' }, { action: 'approve', label: '批准申请' }],
  }], edges: [] }} />);
  expect(screen.getByLabelText('节点操作预览').textContent).toBe('不予受理批准申请');
  expect(screen.getByText('批准申请前需填写处理意见。')).toBeTruthy();
});

it.each([{}, [null, { action: 'approve', label: 123 }]])('可预览含未校验展示配置的导入草稿 %#', actionDisplay => {
  render(<WorkflowPreview schema={{ version: 1, fields: [] }} design={{ nodes: [{
    id: 'a', type: 'approval', name: '审批', action_display: actionDisplay as DesignNode['action_display'],
  }], edges: [] }} />);
  expect(screen.getByLabelText('节点操作预览').textContent).toBe('同意拒绝');
});
