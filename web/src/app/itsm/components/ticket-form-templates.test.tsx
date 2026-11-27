import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App, Form, Input } from 'antd';
import { beforeEach, expect, it, vi } from 'vitest';
import { TicketFormTemplates } from './ticket-form-templates';

const api = vi.hoisted(() => ({
  ready: true,
  listFormTemplates: vi.fn(),
  saveFormTemplate: vi.fn(),
  deleteFormTemplate: vi.fn(),
}));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }) });

function Example() {
  const [form] = Form.useForm();
  return <App><TicketFormTemplates serviceId={7} form={form} fields={[
    { key: 'title', type: 'input', label: '标题' },
    { key: 'amount', type: 'input', label: '数量' },
    { key: 'dynamic', type: 'select', label: '动态选项', fetch: { source: 'integration', mode: 'options' } },
    { key: 'rows', type: 'table', label: '明细' },
  ]} /><Form form={form} initialValues={{ title: '当前值', amount: '9', dynamic: '旧值', rows: '旧行' }}>
    <Form.Item name="title"><Input aria-label="标题" /></Form.Item>
    <Form.Item name="amount"><Input aria-label="数量" /></Form.Item>
    <Form.Item name="dynamic"><Input aria-label="动态选项" /></Form.Item>
    <Form.Item name="rows"><Input aria-label="明细" /></Form.Item>
  </Form></App>;
}

beforeEach(() => {
  vi.resetAllMocks();
  api.listFormTemplates.mockResolvedValue({ items: [{ id: 3, name: '常用申请', form_data: { title: '模板值' }, changed: false }] });
  api.saveFormTemplate.mockResolvedValue({ id: 4 });
  api.deleteFormTemplate.mockResolvedValue({ id: 3 });
});

it('未填完仍可保存当前内容为同流程模板', async () => {
  render(<Example />);
  fireEvent.click(screen.getByRole('button', { name: '保存为模板' }));
  const dialog = screen.getByRole('dialog');
  fireEvent.change(within(dialog).getByRole('textbox', { name: '模板名称' }), { target: { value: '我的模板' } });
  fireEvent.click(within(dialog).getByRole('button', { name: '保存模板' }));
  await waitFor(() => expect(api.saveFormTemplate).toHaveBeenCalledWith(7, { name: '我的模板', form_data: { title: '当前值', amount: '9', dynamic: '旧值', rows: '旧行' } }));
});

it('套用模板覆盖已填字段并清空未保存字段，再次打开仍可复用', async () => {
  render(<Example />);
  fireEvent.click(screen.getByRole('button', { name: '套用模板' }));
  const dialog = await screen.findByRole('dialog');
  await within(dialog).findByText('常用申请');
  fireEvent.click(within(dialog).getByRole('button', { name: '套用' }));
  await waitFor(() => expect((screen.getByRole('textbox', { name: '标题' }) as HTMLInputElement).value).toBe('模板值'));
  expect((screen.getByRole('textbox', { name: '数量' }) as HTMLInputElement).value).toBe('');
  expect((screen.getByRole('textbox', { name: '动态选项' }) as HTMLInputElement).value).toBe('');
  expect((screen.getByRole('textbox', { name: '明细' }) as HTMLInputElement).value).toBe('');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '套用模板' })); });
  expect(await screen.findByText('常用申请')).toBeTruthy();
});
