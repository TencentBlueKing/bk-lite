'use client';

import React, { cloneElement, type ReactElement, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { basicFieldControl, dateItemProps } from './basic-field-control';
import { matches } from './form-conditions';
import { fetchDependencies, ScopedFetchControl, type FetchContext } from './field-fetch-control';
import dynamic from 'next/dynamic';
import { ItsmModal } from './interaction-surfaces';
import { TableOptionCell } from './table-option-cell';
import { Button, Form, Input, Tag, Tooltip } from 'antd';
import { CopyOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { FormChoice, FormFieldSchema } from '../types';

export function isRequiredColumn(column: FormFieldSchema, permissions: Record<string, string>) {
  const mode = permissions[column.key] || permissions['*'] || 'edit';
  return (column.required === true || mode === 'required') && !['read', 'readonly', 'hidden'].includes(mode)
    && !['hidden', 'readonly', 'disabled'].includes(column.state || '');
}

const MarkdownRenderer = dynamic(() => import('@/components/markdown'));
const multiValueTypes = new Set(['multiselect', 'multiCascade', 'checkbox', 'user', 'multiUser']);

type RowLabels = Record<string, FormChoice[]>;

function cellLabels(column: FormFieldSchema, row: Record<string, unknown>, labels: RowLabels) {
  function findLabel(value: unknown, options: FormChoice[], parent = ''): string | undefined {
    for (const option of options) {
      const path = parent && column.showCascadePath !== false ? parent + ' / ' + option.label : option.label;
      if (option.value === value) return path;
      if (option.children) {
        const found = findLabel(value, option.children, path);
        if (found !== undefined) return found;
      }
    }
  }
  const raw = row[column.key];
  const values = Array.isArray(raw) ? raw : [raw];
  const options = [...(labels[column.key] || []), ...(column.source?.options || [])];
  return values.filter(value => value != null && value !== '').map(value =>
    findLabel(value, options) ?? String(value)
  );
}

function displayCell(column: FormFieldSchema, row: Record<string, unknown>, labels: RowLabels) {
  return cellLabels(column, row, labels).join(column.type === 'dateRange' ? ' 至 ' : '、') || '—';
}

function RowDetailValue({ column, row, labels }: { column: FormFieldSchema; row: Record<string, unknown>; labels: RowLabels }) {
  const parts = cellLabels(column, row, labels);
  if (!parts.length) return <span className="text-[var(--color-text-3)]">—</span>;
  if (column.type === 'richtext') return <div className="max-w-full overflow-x-auto"><MarkdownRenderer content={parts[0]} /></div>;
  if (multiValueTypes.has(column.type)) {
    return <div className="flex flex-wrap gap-1">{parts.map((part, index) => (
      <Tag key={index} bordered={false} className="m-0 max-w-full whitespace-normal [overflow-wrap:anywhere]">{part}</Tag>
    ))}</div>;
  }
  return <span className="whitespace-pre-wrap tabular-nums">{parts.join(column.type === 'dateRange' ? ' 至 ' : '、')}</span>;
}

export function TableField({ field, value = [], onChange, disabled = false, context, fieldPerm = {} }: {
  field: FormFieldSchema;
  context?: FetchContext;
  fieldPerm?: Record<string, string>;
  value?: Array<Record<string, unknown>>;
  onChange?: (value: Array<Record<string, unknown>>) => void;
  disabled?: boolean;
}) {
  const { errors } = Form.Item.useStatus();
  const form = Form.useFormInstance();
  const touched = useRef(new Map<number, Set<string>>());
  const configured: FormFieldSchema[] = field.children && (field.children.length || !field.props?.columns) ? field.children
    : String(field.props?.columns || '名称:name\n数量:quantity:number').split('\n').filter(Boolean).map((line) => {
      const [label, key = label, type = 'input'] = line.split(':');
      return { key: key.trim(), label: label.trim(), type };
    });
  const permission = (column: FormFieldSchema) => fieldPerm[column.key] || fieldPerm['*'];
  const columns = configured.filter(column => column.state !== 'hidden' && permission(column) !== 'hidden');
  const rows = Array.isArray(value) ? value : [];
  // 同一轮渲染中多个异步选项可能同时写入，下一列必须接着上一列的结果更新。
  const validatedRows = useRef(value);
  useEffect(() => {
    const changed = validatedRows.current !== value;
    validatedRows.current = value;
    if (changed && errors?.length && form) void form.validateFields([field.key]).catch(() => {});
  }, [value, errors, form, field.key]);
  const latestRows = useRef(rows);
  useLayoutEffect(() => { latestRows.current = rows; }, [rows]);
  const [viewKey, setViewKey] = useState<number | null>(null);
  const viewTrigger = useRef<HTMLElement | null>(null);
  const liveLabels = useRef(new Map<number, RowLabels>());
  const nextKey = useRef(0);
  const rowKeys = useRef<number[]>([]);
  const keys = rows.map((_, i) => rowKeys.current[i] ?? (rowKeys.current[i] = ++nextKey.current));
  const viewIndex = viewKey === null ? -1 : keys.indexOf(viewKey);
  const labelsAt = (index: number): RowLabels => ({
    ...(rows[index]?._field_labels as RowLabels | undefined),
    ...liveLabels.current.get(keys[index]),
  });
  const changeRows = (next: typeof rows) => {
    latestRows.current = next;
    onChange?.(next);
  };
  const configuredLimit = Number(field.props?.maxRows);
  const maxRows = Number.isInteger(configuredLimit) && configuredLimit > 0 ? Math.min(configuredLimit, 100) : 100;
  const insert = (index: number, copy = false) => {
    const current = latestRows.current;
    if (current.length >= maxRows) return;
    const added = Object.fromEntries(columns.map(column => {
      const cell = copy ? current[index]?.[column.key] : column.default;
      return [column.key, cell == null ? '' : structuredClone(cell)];
    }));
    if (copy) {
      const source = current[index];
      for (const key of ['_field_receipts', '_field_labels']) if (source?.[key]) added[key] = structuredClone(source[key]);
    }
    const key = ++nextKey.current;
    if (copy) liveLabels.current.set(key, { ...labelsAt(index) });
    rowKeys.current.splice(index + 1, 0, key);
    changeRows([...current.slice(0, index + 1), added, ...current.slice(index + 1)]);
  };
  const remove = (index: number) => {
    liveLabels.current.delete(keys[index]);
    touched.current.delete(keys[index]);
    rowKeys.current.splice(index, 1);
    changeRows(latestRows.current.filter((_, i) => i !== index));
  };
  const update = (rowKey: number, key: string, next: unknown) => {
    const index = rowKeys.current.indexOf(rowKey);
    const current = latestRows.current;
    if (!current[index] || Object.is(current[index][key], next)) return;
    const changed = { ...current[index], [key]: next };
    for (const column of columns) {
      if (!column.fetch || !fetchDependencies(column.fetch).includes(key)) continue;
      if (column.fetch.mode === 'options' || column.fetch.enforce) delete changed[column.key];
      for (const name of ['_field_receipts', '_field_labels']) {
        if (!changed[name]) continue;
        const metadata = { ...changed[name] as Record<string, unknown> };
        delete metadata[column.key];
        changed[name] = metadata;
      }
    }
    changeRows(current.map((row, i) => i === index ? changed : row));
  };
  return <div className="overflow-x-auto">
    <table className="w-full border-collapse text-left text-sm [&_td]:border [&_td]:border-solid [&_td]:border-[var(--color-border-2)] [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-solid [&_th]:border-[var(--color-border-2)] [&_th]:bg-[var(--color-fill-2)] [&_th]:px-3 [&_th]:py-2 [&_th]:font-medium">
      <thead><tr>{columns.map(column => {
        const required = !disabled && isRequiredColumn(column, fieldPerm)
          && (!column.visibleWhen || rows.some(row => matches(column.visibleWhen, row)));
        return <th key={column.key} scope="col" aria-description={required ? '必填' : undefined}>
          {required && <span aria-hidden="true" title="必填" className="mr-1 text-[var(--color-fail)]">*</span>}{column.label}
        </th>;
      })}<th scope="col" className="sticky right-0 z-10">操作</th></tr></thead>
      <tbody>{rows.map((row, index) => <tr key={keys[index]}>
        {columns.map((column) => {
          if (!matches(column.visibleWhen, row)) return <td key={column.key} />;
          const locked = disabled || ['readonly', 'read'].includes(permission(column)) || ['readonly', 'disabled'].includes(column.state || '');
          const path = field.key + '.' + column.key;
          const rowKey = keys[index];
          const read = () => latestRows.current[rowKeys.current.indexOf(rowKey)] || {};
          const set = (key: string, next: unknown) => update(rowKey, key, next);
          const label = column.label + ' ' + (index + 1);
          const raw = row[column.key];
          const date = dateItemProps(column);
          const cellValue = date.getValueProps ? date.getValueProps(raw).value : raw === '' ? undefined : raw;
          const edit = (next: unknown) => {
            const fields = touched.current.get(rowKey) || new Set<string>();
            fields.add(column.key);
            touched.current.set(rowKey, fields);
            const input = next && typeof next === 'object' && 'target' in next ? (next.target as HTMLInputElement).value : next;
            set(column.key, date.normalize ? date.normalize(input) : input);
          };
          const cell = cloneElement(basicFieldControl(column, locked) as ReactElement<Record<string, unknown>>, {
            value: cellValue, onChange: edit,
            ...(column.type === 'user' || column.type === 'multiUser' ? { ariaLabel: label } : { 'aria-label': label }),
          });
          const deps = fetchDependencies(column.fetch);
          let control = cell;
          if (!locked && column.fetch && context) {
            control = <ScopedFetchControl field={column} path={path} context={context} value={cellValue} onChange={edit}
              depKey={JSON.stringify(deps.map(key => row[key] ?? null))}
              store={{
                getFieldValue: key => key === '_field_labels' ? labelsAt(rowKeys.current.indexOf(rowKey)) : read()[key], setFieldValue: set,
                rememberOptions: options => liveLabels.current.set(rowKey, { ...liveLabels.current.get(rowKey), [column.key]: options }),
                isFieldTouched: key => Boolean(touched.current.get(rowKey)?.has(key)),
                requestValues: () => ({ [field.key]: [Object.fromEntries(Object.entries(read()).filter(([key]) => !['_field_receipts', '_field_labels'].includes(key)))] }),
              }}>{cell}</ScopedFetchControl>;
          } else if (locked && (column.type === 'select' || column.fetch?.mode === 'options')) {
            control = <span>{displayCell(column, row, labelsAt(index))}</span>;
          } else if (column.type === 'select') {
            control = <TableOptionCell column={column} row={row} index={index} onChange={choice => edit(choice.value)} />;
          }
          const invalid = !locked && Boolean(errors?.length) && isRequiredColumn(column, fieldPerm)
            && (raw == null || raw === '' || (Array.isArray(raw) && !raw.length));
          const showValueTip = locked || (column.fetch?.mode === 'value' && column.fetch.enforce);
          return <td key={column.key} className={column.type === 'richtext' ? 'min-w-96' : 'min-w-36'}>
            <Form.Item noStyle validateStatus={invalid ? 'error' : ''}>
              {showValueTip ? <Tooltip trigger={['hover', 'focus']} title={<span className="block max-h-[50vh] overflow-y-auto whitespace-pre-wrap [overflow-wrap:anywhere]">{displayCell(column, row, labelsAt(index))}</span>}>
                <div tabIndex={0} aria-label={label} className="rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]">
                  <div className={locked ? 'pointer-events-none' : undefined}>{control}</div>
                </div>
              </Tooltip> : control}
            </Form.Item>
            {invalid && <div role="alert" className="text-xs text-[var(--color-fail)]">请填写{column.label}</div>}
          </td>;
        })}
        <td className="sticky right-0 z-10 w-px whitespace-nowrap bg-[var(--color-bg)]">
          <Button disabled={false} aria-label={`查看第 ${index + 1} 行`} type="link" size="small" onClick={event => { viewTrigger.current = event.currentTarget; setViewKey(keys[index]); }}>查看</Button>
          {!disabled && <>
            <Tooltip title="在下方添加行"><Button aria-label="添加行" type="text" size="small" icon={<PlusOutlined />} disabled={rows.length >= maxRows} onClick={() => insert(index)} /></Tooltip>
            <Tooltip title="复制到下方"><Button aria-label="复制行" type="text" size="small" icon={<CopyOutlined />} disabled={rows.length >= maxRows} onClick={() => insert(index, true)} /></Tooltip>
            <Tooltip title="删除行"><Button aria-label="删除行" type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => remove(index)} /></Tooltip>
          </>}
        </td>
      </tr>)}
        {!rows.length && <tr><td colSpan={columns.length + 1} className="text-center text-[var(--color-text-3)]">暂无数据</td></tr>}
      </tbody>
    </table>
    <ItsmModal
      open={viewIndex >= 0} destroyOnHidden centered width={800}
      title={field.label} subTitle={viewIndex >= 0 ? `第 ${viewIndex + 1} 行` : undefined}
      onCancel={() => setViewKey(null)} afterClose={() => viewTrigger.current?.focus({ preventScroll: true })}
      footer={<Button disabled={false} onClick={() => setViewKey(null)}>关闭</Button>}
    >
      {viewIndex >= 0 && <dl className="m-0 grid grid-cols-1 gap-2 py-1 sm:grid-cols-2">
        {columns.filter(column => matches(column.visibleWhen, rows[viewIndex])).map(column => (
          <div key={column.key} className={`grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] overflow-hidden rounded-md border border-[var(--color-border-2)] ${['textarea', 'richtext'].includes(column.type) ? 'sm:col-span-2' : ''}`}>
            <dt className="flex items-start border-r border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-3 py-2 text-sm font-medium leading-6 text-[var(--color-text-2)] [overflow-wrap:anywhere]">{column.label}</dt>
            <dd className="m-0 min-w-0 px-3 py-2 text-sm leading-6 text-[var(--color-text-1)] [overflow-wrap:anywhere]">
              <RowDetailValue column={column} row={rows[viewIndex]} labels={labelsAt(viewIndex)} />
            </dd>
          </div>
        ))}
      </dl>}
    </ItsmModal>
    {!disabled && !rows.length && <Button className="mt-2" size="small" icon={<PlusOutlined />} onClick={() => insert(-1)}>添加行</Button>}
  </div>;
}

export function SignatureField({ value, onChange, disabled }: { value?: string; onChange?: (value: string) => void; disabled?: boolean }) {
  return <Input aria-label="签名" maxLength={100} placeholder="请输入签名姓名" value={value} disabled={disabled} onChange={(event) => onChange?.(event.target.value)} />;
}
