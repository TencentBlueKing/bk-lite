import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { FormFieldSchema } from '../types';
import { FormRenderer } from './form-renderer';

vi.mock('@/app/opspilot/components/ai-editor', () => ({ default: () => null }));
vi.mock('@/components/group-tree-select', () => ({ default: () => null }));
const fetchField = vi.hoisted(() => vi.fn());
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ fetchField, ready: true }) }));
const column = (key: string, label: string, dependencies: string[] = []): FormFieldSchema => ({
  key, label, required: true, type: 'select', fetch: { source: 'integration', mode: 'options', dependencies },
});
const table = { key: 'requests', type: 'table', label: '批量申请', required: true, props:{maxRows:2}, children: [
  column('size_id', '配置'), column('storage_class', '存储类型'), column('storage_gib', '存储容量', ['storage_class']),
] };
const [flavor, policy, capacity] = table.children;
flavor.source = { type: 'static', options: [{ value: 'small', label: '2 核 4 GiB' }, { value: 'large', label: '4 核 8 GiB' }] };
policy.source = { type: 'static', options: [{ value: 'standard', label: '普通盘' }, { value: 'fast', label: '快速盘' }] };
capacity.source = { type: 'static', options: [{ value: 20, label: '20 GiB' }, { value: 40, label: '40 GiB' }] };
const initial = { requests: [{ size_id: 'small', storage_class: 'standard', storage_gib: 20 }, { size_id: 'large', storage_class: 'fast', storage_gib: 40 }] };
beforeEach(() => {
  fetchField.mockReset();
  Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {} }) });
});
it('展示工单快照中的目录名称和容量，只读时不查询目录', () => {
  render(<FormRenderer schema={{ version: 1, fields: [table] }} initialValues={initial} readOnly fetchContext={{ticket_id: 3}} onSubmit={vi.fn()} />);
  for (const text of ['2 核 4 GiB', '4 核 8 GiB', '普通盘', '快速盘', '20 GiB', '40 GiB']) expect(screen.getByText(text)).toBeTruthy();
  expect(fetchField).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: '添加行' })).toBeNull();
});
it('逐行请求选项，切换策略清除同一行旧容量，提交保留数字和行顺序', async () => {
  fetchField.mockImplementation(async ({ field }) => ({ options: field.endsWith('storage_class') ? [{value:'fast',label:'高性能盘'}] : [{value:0,label:'不添加数据盘'}] }));
  const submit = vi.fn();
  render(<FormRenderer schema={{ version: 1, fields: [table] }} initialValues={initial} fetchContext={{ service_id: 7 }} onSubmit={submit} />);
  for (const action of screen.getAllByRole('button', {name:/^(添加行|复制行)$/})) expect((action as HTMLButtonElement).disabled).toBe(true);
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'存储类型 1'}));
  fireEvent.click(await screen.findByText('高性能盘', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await waitFor(() => expect(screen.getByText(/第 1 行.*存储容量/)).toBeTruthy());
  expect(submit).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'存储容量 1'}));
  fireEvent.click(await screen.findByText('不添加数据盘'));
  expect(fetchField).toHaveBeenCalledWith(expect.objectContaining({service_id:7, field:'requests.storage_gib',values:{requests:[expect.objectContaining({storage_class:'fast'})]}}));
  fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith({requests:[expect.objectContaining({size_id:'small',storage_class:'fast',storage_gib:0}),{size_id:'large',storage_class:'fast',storage_gib:40}]}));
  fireEvent.click(screen.getAllByRole('button', {name:'删除行'})[0]);
  fireEvent.click(screen.getByRole('button', {name:'添加行'}));
  expect(screen.getByRole('combobox', {name:'存储容量 2'}).getAttribute('disabled')).not.toBeNull();
});
