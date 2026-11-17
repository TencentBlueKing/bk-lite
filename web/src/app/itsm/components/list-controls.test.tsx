import React from 'react';
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ItsmRowActions, ItsmListToolbar } from './list-controls';
vi.mock('@/components/more-actions-dropdown', () => ({ default: ({ items }: { items: Array<{key:string;label:React.ReactNode;disabled?:boolean;onClick?:()=>void;confirm?:{title:React.ReactNode}}> }) => <div aria-label="更多操作">{items.map(item => <button key={item.key} disabled={item.disabled} onClick={item.onClick}>{item.label}{item.confirm && <span>需确认</span>}</button>)}</div> }));
afterEach(cleanup);
it('仅展示获授权操作，最多两个常用图标，危险操作进入更多并保留确认', () => {
  const edit = vi.fn(); const remove = vi.fn();
  render(<ItsmRowActions items={[
    {key:'edit',label:'编辑',kind:'edit',onClick:edit},
    {key:'preview',label:'预览',kind:'view'},
    {key:'export',label:'导出',kind:'export'},
    {key:'delete',label:'删除',kind:'delete',danger:true,disabled:true,onClick:remove,confirm:{title:'确定删除？'}},
    {key:'hidden',label:'发布',kind:'publish',hidden:true},
  ]}/>);
  fireEvent.click(screen.getByRole('button',{name:'编辑'})); expect(edit).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button',{name:'发布'})).toBeNull();
  expect(screen.getByLabelText('更多操作').textContent).toContain('导出');
  fireEvent.click(screen.getByRole('button',{name:'删除需确认'})); expect(remove).not.toHaveBeenCalled();
});
it('普通列表搜索与公共操作成组靠右，搜索在操作之前', () => {
  const change = vi.fn();
  render(<ItsmListToolbar search={{value:'',onChange:change,placeholder:'搜索名称'}} actions={<button>新建</button>}/>);
  fireEvent.change(screen.getByPlaceholderText('搜索名称'),{target:{value:'金额'}});
  expect(change).toHaveBeenCalledWith('金额');
  expect(screen.getByRole('button',{name:'新建'})).toBeTruthy();
  expect(screen.getByPlaceholderText('搜索名称').compareDocumentPosition(screen.getByRole('button',{name:'新建'})) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
it('有分组时分组居前，搜索与公共操作居后', () => {
  render(<ItsmListToolbar leading={<button>全部</button>} search={{value:'',onChange:vi.fn()}} actions={<button>新建</button>} />);
  expect(screen.getByRole('button',{name:'全部'}).compareDocumentPosition(screen.getByRole('searchbox')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole('searchbox').compareDocumentPosition(screen.getByRole('button',{name:'新建'})) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
