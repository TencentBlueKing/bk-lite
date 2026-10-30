import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';
import ItsmIntegrationCard from '../itsmIntegrationCard';
const http = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('@/utils/request', () => ({ default: () => http }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/components/permission', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }) });
});
afterEach(() => { cleanup(); http.get.mockReset(); http.put.mockReset(); http.post.mockReset(); });
const config = { name: 'Dev ITSM', url: 'https://itsm.example/api', enabled: false, token_configured: true, failure_notification: {} };
async function openForm(saved: typeof config | null = config) {
  http.get.mockResolvedValue(saved);
  render(<ItsmIntegrationCard users={[]} channels={[]} />);
  await screen.findByText(saved ? 'Dev ITSM' : 'itsmIntegration.empty');
  expect(screen.queryByRole('button', { name: 'itsmIntegration.test' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'itsmIntegration.configure' }));
  return within(await screen.findByRole('dialog'));
}
it('首次配置在表单中测试当前输入，成功后才可启用', async () => {
  http.post.mockResolvedValue({ connected: true }); http.put.mockResolvedValue({ ...config, enabled: true });
  const form = await openForm(null);
  expect(form.getByRole('switch').hasAttribute('disabled')).toBe(true);
  fireEvent.change(form.getByLabelText('itsmIntegration.url'), { target: { value: config.url } });
  fireEvent.change(form.getByLabelText('itsmIntegration.token'), { target: { value: 'DRAFT-TOKEN' } });
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await form.findByText('itsmIntegration.testPassed');
  expect(http.put).not.toHaveBeenCalled();
  expect(http.post.mock.calls[0][1]).toMatchObject({ url: config.url, token: 'DRAFT-TOKEN', enabled: false });
  fireEvent.click(form.getByRole('switch'));
  fireEvent.click(form.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(http.put).toHaveBeenCalledOnce());
  expect(http.put.mock.calls[0][1].enabled).toBe(true);
});
it('测试失败保留输入和错误，仍可保存未启用草稿', async () => {
  http.post.mockRejectedValue(new Error('ITSM TLS 校验失败')); http.put.mockResolvedValue(config);
  const form = await openForm();
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await form.findByText('ITSM TLS 校验失败');
  expect(form.getByRole('switch').hasAttribute('disabled')).toBe(true);
  expect(http.post.mock.calls[0][1]).not.toHaveProperty('token');
  fireEvent.click(form.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(http.put).toHaveBeenCalledOnce());
  expect(http.put.mock.calls[0][1].enabled).toBe(false);
  expect(http.put.mock.calls[0][1]).not.toHaveProperty('token');
});
it.each(['url', 'token', 'ca'])('修改 %s 后旧测试成功失效', async (field) => {
  http.post.mockResolvedValue({ connected: true });
  const form = await openForm();
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await form.findByText('itsmIntegration.testPassed');
  fireEvent.click(form.getByRole('switch'));
  fireEvent.change(form.getByLabelText(`itsmIntegration.${field}`), { target: { value: field === 'url' ? 'https://new.example/api' : 'changed' } });
  expect(form.queryByText('itsmIntegration.testPassed')).toBeNull();
  expect(form.getByRole('switch').hasAttribute('disabled')).toBe(true);
  expect(form.getByRole('switch').getAttribute('aria-checked')).toBe('false');
});
it('迟到测试结果不能解锁修改后的配置', async () => {
  let finish!: (result: { connected: boolean }) => void;
  http.post.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const form = await openForm();
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await waitFor(() => expect(http.post).toHaveBeenCalledOnce());
  fireEvent.change(form.getByLabelText('itsmIntegration.url'), { target: { value: 'https://new.example/api' } });
  finish({ connected: true });
  await waitFor(() => expect(form.getByRole('button', { name: 'itsmIntegration.test' }).hasAttribute('disabled')).toBe(false));
  expect(form.queryByText('itsmIntegration.testPassed')).toBeNull();
  expect(form.getByRole('switch').hasAttribute('disabled')).toBe(true);
});
it('已启用连接无需通过测试即可停用', async () => {
  http.put.mockResolvedValue(config);
  const form = await openForm({ ...config, enabled: true });
  fireEvent.click(form.getByRole('switch'));
  fireEvent.click(form.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(http.put).toHaveBeenCalledOnce());
  expect(http.put.mock.calls[0][1].enabled).toBe(false);
  expect(http.post).not.toHaveBeenCalled();
});
it('保存复测失败，保留表单并重新锁定启用', async () => {
  http.post.mockResolvedValue({ connected: true }); http.put.mockRejectedValue(new Error('ITSM 认证失败'));
  const form = await openForm();
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await form.findByText('itsmIntegration.testPassed');
  fireEvent.click(form.getByRole('switch'));
  fireEvent.click(form.getByRole('button', { name: 'common.save' }));
  await form.findByText('ITSM 认证失败');
  expect(form.getByRole('switch').hasAttribute('disabled')).toBe(true);
  expect(form.queryByText('itsmIntegration.testPassed')).toBeNull();
});
it('修改已启用配置测试失败时，不会通过保存草稿意外停用原连接', async () => {
  http.post.mockRejectedValue(new Error('ITSM 认证失败')); http.put.mockResolvedValue(config);
  const form = await openForm({ ...config, enabled: true });
  fireEvent.change(form.getByLabelText('itsmIntegration.token'), { target: { value: 'BAD-TOKEN' } });
  fireEvent.click(form.getByRole('button', { name: 'itsmIntegration.test' }));
  await form.findByText('ITSM 认证失败');
  expect(form.getByRole('switch').getAttribute('aria-checked')).toBe('true');
  expect(form.getByRole('button', { name: 'common.save' }).hasAttribute('disabled')).toBe(true);
  expect(http.put).not.toHaveBeenCalled();
  fireEvent.click(form.getByRole('switch'));
  fireEvent.click(form.getByRole('button', { name: 'common.save' }));
  await waitFor(() => expect(http.put).toHaveBeenCalledOnce());
  expect(http.put.mock.calls[0][1].enabled).toBe(false);
});
it('加载失败不能打开配置以免覆盖', async () => {
  http.get.mockRejectedValue(new Error('network'));
  render(<ItsmIntegrationCard users={[]} channels={[]} />);
  await screen.findByText('itsmIntegration.loadFailed');
  expect(screen.getByRole('button', { name: 'itsmIntegration.configure' }).hasAttribute('disabled')).toBe(true);
});
