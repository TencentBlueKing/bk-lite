import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Button, Form } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import ItsmFields, { defaultBindings } from '../itsmFields';

const { get } = vi.hoisted(() => ({ get: vi.fn<(url: string) => Promise<unknown>>(() => Promise.resolve([])) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/utils/request', () => ({ default: () => ({ get, post: vi.fn() }) }));
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }) });
});
afterEach(() => {
  cleanup();
  get.mockReset();
  get.mockImplementation(() => Promise.resolve([]));
});

const SCHEMA = [
  { key: 'ticket__title', name: '标题', type: 'input', required: true, options: [] },
  { key: 'reporter', name: '申请人', type: 'user', required: true, options: [] },
  { key: 'urgency', name: '紧急度', type: 'select', required: false, options: [{ key: 'p1', name: '高' }, { key: 'p2', name: '低' }] },
  { key: 'richText_reason', name: '申请理由', type: 'richText', required: true, options: [] },
];
const SERVICE = { value: '20261008185800000809', label: '终端服务 / 个人电脑或外设申请与更换' };
function mockSchema() {
  get.mockImplementation((url: string) => Promise.resolve(url.includes('/services/') ? [SERVICE] : SCHEMA));
}

it('读不到表单时删除前面的映射后，后一项的常量编辑器与实际值一致', () => {
  render(<Form initialValues={{ workflow_key: 'flow', form_bindings: [{ name: 'ticket__title', from: 'const', value: 'CPU' }, { name: 'extra', from: 'const', value: 'x' }, { name: 'count', from: 'const', value: 0 }] }}>
    <ItsmFields connections={[]} />
  </Form>);
  fireEvent.click(screen.getAllByRole('button', { name: 'common.delete' })[0]);
  expect(screen.getAllByRole('textbox', { name: 'itsm.constant' }).map(item => (item as HTMLInputElement).value)).toEqual(['CPU', '0']);
});

it('提交保留零、布尔值和 JSON 对象，不把常量转为字符串', async () => {
  const submit = vi.fn();
  const bindings = [
    { name: 'ticket__title', from: 'field', value: 'title' },
    { name: 'count', from: 'const', value: 0 },
    { name: 'enabled', from: 'const', value: false },
    { name: 'details', from: 'const', value: { host: 'test' } },
  ];
  render(<Form initialValues={{ connection: 'dev', workflow_key: 'flow', form_bindings: bindings }} onFinish={submit}>
    <ItsmFields connections={[{ value: 'dev', label: '开发环境' }]} />
    <Button htmlType="submit">保存</Button>
  </Form>);
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(submit.mock.calls[0][0].form_bindings).toEqual(bindings);
});

it('选择工单后按表单字段逐行展示，标题取告警标题、长文本取告警内容', async () => {
  mockSchema();
  const submit = vi.fn();
  render(<Form initialValues={{ connection: 'dev', form_bindings: [{ name: 'ticket__title', from: 'field', value: 'title' }] }} onFinish={submit}>
    <ItsmFields connections={[{ value: 'dev', label: '开发环境' }]} />
    <Button htmlType="submit">保存</Button>
  </Form>);
  fireEvent.mouseDown(await screen.findByRole('combobox', { name: 'itsm.workflow' }));
  fireEvent.click(await screen.findByText(SERVICE.label));
  const reporter = await screen.findByTestId('itsm-row-reporter');
  expect(within(reporter).getByText('申请人')).toBeTruthy();
  expect(within(reporter).getByText('itsm.requiredHint')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(submit.mock.calls[0][0].form_bindings).toEqual([
    { name: 'ticket__title', from: 'field', value: 'title' },
    { name: 'richText_reason', from: 'field', value: 'content' },
  ]);
});

it('编辑已有规则时自动读取表单，不覆盖已保存映射，旧字段单独标出', async () => {
  mockSchema();
  const bindings = [
    { name: 'ticket__title', from: 'field', value: 'resource_name' },
    { name: 'urgency', from: 'const', value: 'p1' },
    { name: 'legacy_field', from: 'const', value: 'keep' },
  ];
  const submit = vi.fn();
  render(<Form initialValues={{ connection: 'dev', workflow_key: SERVICE.value, form_bindings: bindings }} onFinish={submit}>
    <ItsmFields connections={[{ value: 'dev', label: '开发环境' }]} />
    <Button htmlType="submit">保存</Button>
  </Form>);
  const urgency = await screen.findByTestId('itsm-row-urgency');
  expect(within(urgency).getByText('高')).toBeTruthy();
  expect(within(screen.getByTestId('itsm-row-legacy_field')).getByText('itsm.missingField')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(submit.mock.calls[0][0].form_bindings).toEqual(bindings);
});

it('把可选字段切回不填写会移除映射；标题不能不填', async () => {
  mockSchema();
  const submit = vi.fn();
  render(<Form initialValues={{ connection: 'dev', workflow_key: SERVICE.value, form_bindings: [{ name: 'ticket__title', from: 'field', value: 'title' }, { name: 'urgency', from: 'const', value: 'p2' }] }} onFinish={submit}>
    <ItsmFields connections={[{ value: 'dev', label: '开发环境' }]} />
    <Button htmlType="submit">保存</Button>
  </Form>);
  const urgency = await screen.findByTestId('itsm-row-urgency');
  fireEvent.mouseDown(within(urgency).getByRole('combobox', { name: 'itsm.columnSource' }));
  fireEvent.click((await screen.findAllByText('itsm.sourceNone')).at(-1)!);
  fireEvent.mouseDown(within(screen.getByTestId('itsm-row-ticket__title')).getByRole('combobox', { name: 'itsm.columnSource' }));
  const none = (await screen.findAllByTitle('itsm.sourceNone')).at(-1)!;
  expect(none.closest('.ant-select-item-option')?.classList.contains('ant-select-item-option-disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(submit.mock.calls[0][0].form_bindings).toEqual([{ name: 'ticket__title', from: 'field', value: 'title' }]);
});

it('默认映射保留同名字段，不重复映射告警内容', () => {
  expect(defaultBindings(SCHEMA, [{ name: 'reporter', from: 'const', value: 'admin' }, { name: 'gone', from: 'const', value: 1 }])).toEqual([
    { name: 'ticket__title', from: 'field', value: 'title' },
    { name: 'reporter', from: 'const', value: 'admin' },
    { name: 'richText_reason', from: 'field', value: 'content' },
  ]);
  expect(defaultBindings(SCHEMA, [{ name: 'reporter', from: 'field', value: 'content' }])).toEqual([
    { name: 'ticket__title', from: 'field', value: 'title' },
    { name: 'reporter', from: 'field', value: 'content' },
  ]);
});
