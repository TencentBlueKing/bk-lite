import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TableField, SignatureField } from './structured-fields';

describe('结构化字段', () => {
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
  it('签名可填写并回传持久化值', () => {
    const onChange = vi.fn();
    render(<SignatureField onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('签名'), { target: { value: '张三' } });
    expect(onChange).toHaveBeenCalledWith('张三');
  });
});
