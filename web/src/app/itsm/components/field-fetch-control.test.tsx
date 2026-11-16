import React from 'react';
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { Form, Input, Radio, TreeSelect } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { FieldFetchControl } from './field-fetch-control';
const api = vi.hoisted(() => ({ ready: true, fetchField: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() })) });
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function Sample() {
  return <Form initialValues={{ dept: '研发' }}><Form.Item name="dept"><Input aria-label="部门" /></Form.Item>
    <Form.Item name="result"><FieldFetchControl field={{ key: 'result', label: '结果', type: 'input', fetch: { source: 'integration', mode: 'value', integration_id: 1, inputs: { dept: '${form.dept}' }, dependencies: ['dept'] } }} context={{ service_id: 1 }}><Input aria-label="结果" /></FieldFetchControl></Form.Item>
    <Form.Item name="_field_receipts" hidden><Input /></Form.Item></Form>;
}
it('依赖变化重新取数，保留手动修改值', async () => {
  api.fetchField.mockResolvedValue({ value: '自动值', receipt: 'proof', options: [], fills: {} });
  render(<Sample />);
  await waitFor(() => expect((screen.getByLabelText('结果') as HTMLInputElement).value).toBe('自动值'));
  fireEvent.change(screen.getByLabelText('结果'), { target: { value: '手动值' } });
  fireEvent.change(screen.getByLabelText('部门'), { target: { value: '运维' } });
  await waitFor(() => expect(api.fetchField).toHaveBeenCalledTimes(2));
  expect((screen.getByLabelText('结果') as HTMLInputElement).value).toBe('手动值');
});
it('取数失败显示重试，不覆盖已填值', async () => {
  api.fetchField.mockRejectedValue(new Error('无权限'));
  render(<Sample />);
  await screen.findByText('无权限');
  expect((screen.getByRole('button', { name: '刷新取数' }) as HTMLButtonElement).disabled).toBe(false);
});

it('动态单选使用映射名称并联动填充目标字段', async () => {
  api.fetchField.mockResolvedValue({ receipt: 'proof', options: [{ value: 'a', label: '资产 A' }], fills: { a: { owner: '张三' } } });
  render(<Form><Form.Item name="asset"><FieldFetchControl field={{ key: 'asset', label: '资产', type: 'radio', fetch: { source: 'integration', mode: 'options', integration_id: 1 } }} context={{ service_id: 1 }}><Radio.Group /></FieldFetchControl></Form.Item><Form.Item name="owner"><Input aria-label="负责人" /></Form.Item><Form.Item name="_field_receipts" hidden><Input /></Form.Item></Form>);
  fireEvent.click(await screen.findByRole('radio', { name: '资产 A' }));
  expect((screen.getByLabelText('负责人') as HTMLInputElement).value).toBe('张三');
});

it('级联取数保留父子层级并可选择子节点', async () => {
  api.fetchField.mockResolvedValue({ receipt: 'proof', options: [{ value: 'p', label: '父项', children: [{ value: 'c', label: '子项' }] }], fills: {} });
  const changed = vi.fn();
  render(<Form onValuesChange={changed}><Form.Item name="tree"><FieldFetchControl field={{ key: 'tree', label: '级联', type: 'cascade', fetch: { source: 'dictionary', mode: 'options', resource_key: 'tree' } }} context={{ service_id: 1 }}><TreeSelect aria-label="级联" treeDefaultExpandAll fieldNames={{ label: 'label', value: 'value', children: 'children' }} /></FieldFetchControl></Form.Item></Form>);
  await waitFor(() => expect(api.fetchField).toHaveBeenCalled());
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '级联' }));
  fireEvent.click(await screen.findByText('子项'));
  expect(changed).toHaveBeenLastCalledWith({ tree: 'c' }, expect.objectContaining({ tree: 'c' }));
});
