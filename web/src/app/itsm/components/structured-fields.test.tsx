import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TableField, SignatureField } from './structured-fields';

describe('结构化字段', () => {
  it('填写前按字段和节点权限标识必填列，只读模式隐藏标识', () => {
    const field = { key: 'items', type: 'table', label: '明细', children: [
      { key: 'name', type: 'input', label: '名称', required: true },
      { key: 'owner', type: 'user', label: '负责人' },
      { key: 'memo', type: 'input', label: '备注' },
      { key: 'code', type: 'input', label: '编号', required: true },
    ] };
    const props = { field, fieldPerm: { owner: 'required', code: 'read' } };
    const view = render(<TableField {...props} />);
    expect(screen.getAllByTitle('必填').map(mark => mark.closest('th')?.textContent)).toEqual(['*名称', '*负责人']);
    expect(screen.queryByRole('alert')).toBeNull();
    view.rerender(<TableField {...props} disabled />);
    expect(screen.queryByTitle('必填')).toBeNull();
  });
  it('查看指定行只展示可见字段，保留零值、多行文本和选项名称', async () => {
    const field = {key:'rows', label:'虚拟机', type:'table', children:[
      {key:'cpu', label:'核数', type:'number'},
      {key:'note', label:'备注', type:'textarea'},
      {key:'pool', label:'资源池', type:'select', source:{type:'static',options:[{label:'生产池',value:'prod'}]}},
      {key:'users',label:'负责人',type:'multiselect'},
      {key:'secret',label:'内部字段',type:'input'}
    ]};
    render(<TableField disabled field={field} fieldPerm={{secret:'hidden'}} value={[{cpu:4}, {cpu:0,note:'第一段\n第二段',pool:'prod',users:['admin','reviewer'],secret:'隐藏内容'}]} />);
    fireEvent.click(screen.getByRole('button', {name:'查看第 2 行'}));
    const panel = within(await screen.findByRole('dialog'));
    expect(panel.getByText('0')).toBeTruthy();
    expect(panel.getByText('第一段 第二段')).toBeTruthy();
    expect(panel.getByText('生产池')).toBeTruthy();
    expect(panel.queryByText('隐藏内容')).toBeNull();
    expect(panel.getByText('admin')).toBeTruthy();
    expect(panel.getByText('reviewer')).toBeTruthy();
    expect(panel.getByRole('button', {name:/关\s*闭/})).toBeTruthy();
  });
  it('空子表单只展示已设计的字段', () => {
    render(<TableField field={{ key: 'items', type: 'table', label: '明细', children: [] }} />);
    expect(screen.queryByRole('columnheader', { name: '名称' })).toBeNull();
  });
  it('表格添加行并把值传回表单', () => {
    const onChange = vi.fn();
    render(<TableField field={{ key: 'items', type: 'table', label: '明细', props: { columns: '名称:name\n数量:qty:number' } }} onChange={onChange} />);
    fireEvent.click(screen.getByText('添加行'));
    expect(onChange).toHaveBeenCalledWith([{ name: '', qty: '' }]);
  });
  it('只读表格展示保存的数据且不能增加行', () => {
    render(<TableField disabled field={{ key: 'items', type: 'table', label: '明细', props: { columns: '名称:name' } }} value={[{ name: '主机A' }]} />);
    expect(screen.getByDisplayValue('主机A')).toBeTruthy();
    expect(screen.queryByText('添加行')).toBeNull();
  });
  it('在当前行下方插入空行或复制可见列，保留零值并清除原行签名', () => {
    const onChange = vi.fn();
    const rows = [{ name: 'A', qty: 0, _itsm_row_ref: 'signed' }, { name: 'B', qty: 2 }];
    render(<TableField field={{ key: 'items', type: 'table', label: '明细', props: { columns: '名称:name\n数量:qty:number' } }} value={rows} onChange={onChange} />);
    fireEvent.click(screen.getAllByRole('button', { name: '复制行' })[0]);
    expect(onChange).toHaveBeenCalledWith([rows[0], { name: 'A', qty: 0 }, rows[1]]);
  });
  it('签名可填写并回传持久化值', () => {
    const onChange = vi.fn();
    render(<SignatureField onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('签名'), { target: { value: '张三' } });
    expect(onChange).toHaveBeenCalledWith('张三');
  });
});
