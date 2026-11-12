'use client';

import React from 'react';
import { Button, Input, InputNumber } from 'antd';
import type { FormFieldSchema } from '../types';

export function TableField({ field, value = [], onChange, disabled = false }: {
  field: FormFieldSchema;
  value?: Array<Record<string, unknown>>;
  onChange?: (value: Array<Record<string, unknown>>) => void;
  disabled?: boolean;
}) {
  const columns = field.children?.length ? field.children.map((child) => ({ key: child.key, label: child.label, type: child.type }))
    : String(field.props?.columns || '名称:name\n数量:quantity:number').split('\n').filter(Boolean).map((line) => {
      const [label, key = label, type = 'input'] = line.split(':');
      return { key: key.trim(), label: label.trim(), type };
    });
  const rows = Array.isArray(value) ? value : [];
  const update = (index: number, key: string, next: unknown) => onChange?.(rows.map((row, i) => i === index ? { ...row, [key]: next } : row));
  return <div className="overflow-x-auto rounded border border-[var(--color-border)] p-2">
    <table className="w-full text-left text-sm">
      <thead><tr>{columns.map((column) => <th key={column.key} className="p-2">{column.label}</th>)}{!disabled && <th>操作</th>}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>
        {columns.map((column) => <td key={column.key} className="p-1">
          {column.type === 'number'
            ? <InputNumber aria-label={`${column.label} ${index + 1}`} disabled={disabled} value={typeof row[column.key] === 'number' ? row[column.key] as number : null} onChange={(next) => update(index, column.key, next)} />
            : <Input aria-label={`${column.label} ${index + 1}`} disabled={disabled} value={String(row[column.key] ?? '')} onChange={(event) => update(index, column.key, event.target.value)} />}
        </td>)}
        {!disabled && <td><Button type="link" danger onClick={() => onChange?.(rows.filter((_, i) => i !== index))}>删除行</Button></td>}
      </tr>)}</tbody>
    </table>
    {!rows.length && <div className="p-2 text-[var(--color-text-3)]">暂无数据</div>}
    {!disabled && <Button size="small" disabled={rows.length >= 100} onClick={() => onChange?.([...rows, Object.fromEntries(columns.map((column) => [column.key, '']))])}>添加行</Button>}
  </div>;
}

export function SignatureField({ value, onChange, disabled }: { value?: string; onChange?: (value: string) => void; disabled?: boolean }) {
  return <Input aria-label="签名" maxLength={100} placeholder="请输入签名姓名" value={value} disabled={disabled} onChange={(event) => onChange?.(event.target.value)} />;
}
