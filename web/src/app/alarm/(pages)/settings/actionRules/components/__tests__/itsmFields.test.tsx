import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Button, Form } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import ItsmFields from '../itsmFields';

const { get } = vi.hoisted(() => ({ get: vi.fn(() => Promise.resolve([])) }));
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

it('删除前面的映射后，后一项的常量编辑器与实际值一致', () => {
  render(<Form initialValues={{ workflow_key: 'flow', form_bindings: [{ name: 'ticket__title', from: 'const', value: 'CPU' }, { name: 'count', from: 'const', value: 0 }] }}>
    <ItsmFields connections={[]} />
  </Form>);
  fireEvent.click(screen.getAllByRole('button', { name: 'common.delete' })[0]);
  expect((screen.getByRole('textbox', { name: 'itsm.constant' }) as HTMLInputElement).value).toBe('0');
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

it('选择工单后按返回字段生成映射，并保留已填写的同名字段', async () => {
  get.mockImplementation((url: string) => {
    if (url.includes('/services/')) {
      return Promise.resolve([{ value: '20261008185800000809', label: '终端服务 / 个人电脑或外设申请与更换' }]);
    }
    return Promise.resolve([
      { key: 'ticket__title', name: '标题', type: 'text' },
      { key: 'reporter', name: '申请人', type: 'user' },
    ]);
  });
  render(<Form initialValues={{ form_bindings: [{ name: 'ticket__title', from: 'field', value: 'content' }] }}>
    <ItsmFields connections={[{ value: 'dev', label: '开发环境' }]} />
  </Form>);
  fireEvent.mouseDown(await screen.findByRole('combobox', { name: 'itsm.workflow' }));
  fireEvent.click(await screen.findByText('终端服务 / 个人电脑或外设申请与更换'));
  const reporter = await screen.findByDisplayValue('reporter');
  expect((reporter as HTMLInputElement).readOnly).toBe(true);
  const title = screen.getByDisplayValue('ticket__title') as HTMLInputElement;
  expect(title.readOnly).toBe(true);
  expect(screen.getByDisplayValue('content')).toBeTruthy();
});
