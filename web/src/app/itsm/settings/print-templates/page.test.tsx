import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PrintPreviewPage from './page';

const api = vi.hoisted(() => ({
  ready: true,
  previewPrintTemplate: vi.fn(),
}));
vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('直接显示全部字段的固定打印样例', async () => {
  api.previewPrintTemplate.mockResolvedValue({
    html: '<h1>示例工单</h1><table><tr><th>工单编号</th><td>REQ001</td></tr><tr><th>申请金额</th><td>360</td></tr></table>'
      + '<img src="https://example.test"><script>window.bad = true</script>',
  });
  render(<PrintPreviewPage />);

  expect(screen.getByRole('status', { name: '正在加载打印预览' })).toBeTruthy();
  const frame = await screen.findByTitle('打印样例预览');
  const fragment = frame.getAttribute('srcdoc');
  expect(fragment).toContain('<h1>示例工单</h1>');
  expect(fragment).toContain('<th>工单编号</th><td>REQ001</td>');
  expect(fragment).toContain('<th>申请金额</th><td>360</td>');
  expect(fragment).toContain("default-src 'none'");
  expect(fragment).not.toContain('<script>');
  expect(fragment).not.toContain('https://example.test');
  expect(frame.getAttribute('sandbox')).not.toContain('allow-scripts');
  expect(screen.queryByRole('button', { name: '新建打印模板' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: '模板内容' })).toBeNull();
  expect(screen.queryByRole('combobox', { name: '插入字段' })).toBeNull();
  expect(api.previewPrintTemplate).toHaveBeenCalledWith();
});

it('样例加载失败后可以重试', async () => {
  api.previewPrintTemplate.mockRejectedValueOnce(new Error('打印样例暂时不可用'))
    .mockResolvedValueOnce({ html: '<h1>示例工单</h1>' });
  render(<PrintPreviewPage />);

  expect((await screen.findByRole('alert')).textContent).toContain('打印样例暂时不可用');
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  expect((await screen.findByTitle('打印样例预览')).getAttribute('srcdoc')).toContain('示例工单');
});
