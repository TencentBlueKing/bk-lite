import React, { useState } from 'react';
import { Modal } from 'antd';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import type { FormFieldSchema } from '../types';
import { FieldFetchEditor, FieldFetchSettings } from './field-fetch-editor';
const api = vi.hoisted(() => ({ ready: true, fieldCatalog: vi.fn(), bindFieldGateway: vi.fn(), fetchField: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, Select: ({ options = [], value, onChange, 'aria-label': label }: { options?: { value: string | number; label: string }[]; value?: string | number; onChange: (v: unknown) => void; 'aria-label'?: string }) => <select aria-label={label} value={value ?? ''} onChange={e => onChange(options.find(o => String(o.value) === e.target.value)?.value)}><option value="" />{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select> };
});

const capabilities = {
  radio: { sources: ['api', 'python', 'dictionary', 'table'], mode: 'options', fill: true },
  input: { sources: ['api', 'python', 'table'], mode: 'value', fill: false },
  number: { sources: ['api', 'python', 'table'], mode: 'value', fill: false },
  table: { sources: ['api', 'python', 'table'], mode: 'table', fill: false },
  user: { sources: [], mode: null, fill: false },
};
const catalog = { capabilities, integrations: [{ id: 1, name: '查询接口', kind: 'api', request_schema: { properties: { page: { type: 'integer' } } } }, { id: 2, name: '计算动作', kind: 'python' }], tables: [{ key: 'assets', name: '资产表', columns: [{ key: 'amount', type: 'number' }, { key: 'name', type: 'string' }] }], dictionaries: [{ key: 'd', name: '字典一' }] };
beforeEach(() => { api.fieldCatalog.mockReset().mockResolvedValue(catalog); api.fetchField.mockReset(); });
afterEach(cleanup);
function Editor({ type = 'radio' }: { type?: string }) {
  const [field, setField] = useState<FormFieldSchema>({ key: 'x', type, label: '测试字段', props: { columns: '金额:amount:number' }, fetch: { source: 'integration', integration_kind: 'api', mode: type === 'radio' ? 'options' : type === 'table' ? 'table' : 'value', integration_id: 1 } });
  return <><FieldFetchSettings field={field} fields={[field]} patch={(_, next) => setField({ ...field, ...next })} /><output data-testid="schema">{JSON.stringify(field)}</output></>;
}
it.each([['radio','选项来源'],['number','自动填值'],['table','行数据来源']])('按 %s 字段显示 %s，复杂配置默认折叠', async (type, title) => {
  render(<Editor type={type} />);
  expect(await screen.findByLabelText(title)).toBeTruthy();
  expect(screen.getByText('高级设置').closest('details')?.open).toBe(false);
  expect(screen.queryByText('数据来源与联动')).toBeNull();
});
it('API 测试后从返回字段下拉选择名称和值，再验证映射', async () => {
  api.fetchField.mockResolvedValueOnce({ sample: { data: { items: [{ id: 7, title: '工单七' }] } } }).mockResolvedValueOnce({ options: [{ value: 7, label: '工单七' }], receipt: 'private' });
  render(<Editor />);
  fireEvent.click(await screen.findByRole('button', { name: '测试并选择返回字段' }));
  await screen.findByText('已获取样本，请确认下方映射；最多展示 3 行。');
  expect(api.fetchField.mock.calls[0][0]).toMatchObject({ preview: true, inspect: true, field: 'x' });
  expect(within(screen.getByLabelText('显示名称')).getByRole('option', { name: 'title · string' })).toBeTruthy();
  fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'title' } });
  fireEvent.change(screen.getByLabelText('选项值'), { target: { value: 'id' } });
  expect(JSON.parse(screen.getByTestId('schema').textContent || '{}').fetch).toMatchObject({ list_path: 'data.items', label_path: 'title', value_path: 'id' });
  fireEvent.click(screen.getByRole('button', { name: '验证映射' }));
  expect(await screen.findByText('映射成功，返回 1 个选项')).toBeTruthy();
  expect(screen.queryByText('private')).toBeNull();
});
it('数值填充值只展示数值路径，数据表自动切换为列下拉', async () => {
  api.fetchField.mockResolvedValue({ sample: { name: '设备', amount: 42 } });
  render(<Editor type="number" />);
  fireEvent.click(await screen.findByRole('button', { name: '测试并选择返回字段' }));
  await screen.findByText('已获取样本，请确认下方映射；最多展示 3 行。');
  expect(within(screen.getByLabelText('填充值')).queryByRole('option', { name: 'name · string' })).toBeNull();
  expect(within(screen.getByLabelText('填充值')).getByRole('option', { name: 'amount · number' })).toBeTruthy();
  fireEvent.change(screen.getByLabelText('自动填值'), { target: { value: 'table' } });
  fireEvent.change(screen.getByLabelText('数据表'), { target: { value: 'assets' } });
  fireEvent.change(screen.getByLabelText('填充值'), { target: { value: '0.amount' } });
  expect(JSON.parse(screen.getByTestId('schema').textContent || '{}').fetch.value_path).toBe('0.amount');
});
it('表格可先获取样本再配置列，不要求事先填写路径', async () => {
  api.fetchField.mockResolvedValue({ sample: [{ amount: 42, name: '设备' }] });
  render(<Editor type="table" />);
  fireEvent.click(await screen.findByRole('button', { name: '测试并选择返回字段' }));
  await screen.findByText('已获取样本，请确认下方映射；最多展示 3 行。');
  expect(within(screen.getByLabelText('列：金额')).queryByRole('option', { name: 'name · string' })).toBeNull();
  fireEvent.change(screen.getByLabelText('列：金额'), { target: { value: 'amount' } });
  expect(JSON.parse(screen.getByTestId('schema').textContent || '{}').fetch.columns).toEqual({ amount: 'amount' });
});
it('切换来源清除样本并忽略旧请求，字典不显示路径配置', async () => {
  let finish!: (value: unknown) => void;
  api.fetchField.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<Editor />);
  fireEvent.click(await screen.findByRole('button', { name: '测试并选择返回字段' }));
  fireEvent.change(screen.getByLabelText('选项来源'), { target: { value: 'dictionary' } });
  await waitFor(() => { finish({ sample: [{ id: 1, name: '旧结果' }] }); });
  expect(screen.queryByText('已获取样本，请确认下方映射；最多展示 3 行。')).toBeNull();
  expect(screen.queryByLabelText('显示名称')).toBeNull();
  expect(screen.queryByLabelText('手动列表路径')).toBeNull();
});
it('专用人员字段隐藏取数，旧错误配置可移除', async () => {
  const patch = vi.fn();
  const { rerender } = render(<FieldFetchEditor field={{ key: 'u', type: 'user', label: '人员' }} fields={[]} patch={patch} />);
  await waitFor(() => expect(api.fieldCatalog).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: '测试并选择返回字段' })).toBeNull();
  rerender(<FieldFetchEditor field={{ key: 'u', type: 'user', label: '人员', fetch: { source: 'dictionary', mode: 'options' } }} fields={[]} patch={patch} />);
  fireEvent.click(await screen.findByRole('button', { name: '移除无效配置' }));
  expect(patch).toHaveBeenCalledWith('u', { fetch: undefined });
});

it('弹窗修改先保留草稿，取消不应用，确定才保存', async () => {
  const confirm=vi.spyOn(Modal,'confirm').mockReturnValue({destroy:vi.fn(),update:vi.fn()});
  function ModalEditor() {
    const [field, setField] = useState<FormFieldSchema>({ key: 'r', type: 'radio', label: '单选', fetch: { source: 'dictionary', mode: 'options', resource_key: 'd' } });
    return <><FieldFetchEditor field={field} fields={[field]} patch={(_, next) => setField({ ...field, ...next })} /><output data-testid="saved">{JSON.stringify(field)}</output></>;
  }
  render(<ModalEditor />);
  fireEvent.click(await screen.findByRole('button', { name: /设\s*置/ }));
  fireEvent.change(await screen.findByLabelText('数据字典'), { target: { value: 'd' } });
  fireEvent.change(screen.getAllByLabelText('选项来源').at(-1)!, { target: { value: 'api' } });
  expect(JSON.parse(screen.getByTestId('saved').textContent!).fetch.source).toBe('dictionary');
  fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }));
  expect(confirm).toHaveBeenCalled();
  confirm.mock.calls.at(-1)![0].onOk?.();
  confirm.mockRestore();
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: /设\s*置/ }));
  expect(await screen.findByLabelText('数据字典')).toBeTruthy();
  fireEvent.change(screen.getAllByLabelText('选项来源').at(-1)!, { target: { value: 'api' } });
  fireEvent.change(screen.getByLabelText('API'), { target: { value: '1' } });
  fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }));
  await waitFor(() => expect(JSON.parse(screen.getByTestId('saved').textContent!).fetch.integration_id).toBe(1));
});

it('未创建集成的网关接口可直接选择并使用其参数定义', async () => {
  api.fieldCatalog.mockResolvedValue({ ...catalog, gateways: [{ path: 'cmdb/models', method: 'GET', name: '模型列表' }] });
  api.bindFieldGateway.mockResolvedValue({ id: 99, kind: 'api', name: '模型列表', request_schema: { properties: { keyword: { type: 'string' } } } });
  render(<Editor />);
  const select = await screen.findByLabelText('API');
  fireEvent.change(select, { target: { value: 'gateway:GET:cmdb/models' } });
  await waitFor(() => expect(api.bindFieldGateway).toHaveBeenCalledWith({ path: 'cmdb/models', method: 'GET' }));
  await waitFor(() => expect(JSON.parse(screen.getByTestId('schema').textContent!).fetch.integration_id).toBe(99));
  expect(screen.getByText('keyword')).toBeTruthy();
});

it('打开取数设置复用已加载目录，不重复查询', async () => {
  const field: FormFieldSchema = { key: 'x', type: 'radio', label: '单选', fetch: { source: 'integration', integration_kind: 'api', mode: 'options', integration_id: 1 } };
  render(<FieldFetchEditor field={field} fields={[field]} patch={vi.fn()} />);
  await screen.findByText('查询接口');
  fireEvent.click(screen.getByRole('button', { name: /设\s*置/ }));
  await screen.findByRole('dialog');
  expect(api.fieldCatalog).toHaveBeenCalledTimes(1);
});

it('子表单参数从同行选择，测试使用子字段路径和单行值', async () => {
  const field: FormFieldSchema = {key: 'size', type:'radio', label:'规格', fetch: { source:'integration', integration_kind:'api', integration_id:1, mode:'options', inputs:{page:'${form.region}'} }};
  const table: FormFieldSchema = {key:'vms', type:'table', label:'配置', children:[{key:'region',type:'input',label:'机房'},field]};
  api.fetchField.mockResolvedValue({sample:[{id:1,name:'小型'}]});
  render(<FieldFetchSettings field={field} fields={[{key:'outside', type:'input',label:'外层'},table]} tableKey="vms" patch={vi.fn()} />);
  const options = within(await screen.findByLabelText('参数1联动字段'));
  expect(options.getByRole('option',{name:'机房 (region)',hidden:true})).toBeTruthy();
  expect(options.queryByRole('option',{name:'外层 (outside)',hidden:true})).toBeNull();
  fireEvent.change(screen.getByLabelText('测试行数据（JSON）'),{target:{value:'{"region":"北京"}'}});
  fireEvent.click(screen.getByRole('button',{name:'测试并选择返回字段'}));
  await waitFor(() => expect(api.fetchField).toHaveBeenCalledWith(expect.objectContaining({field:'vms.size',values:{vms:[{region:'北京'}]}})));
});
