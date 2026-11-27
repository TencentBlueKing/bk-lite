import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from './page';
import zh from '../../../locales/zh.json';

const api = vi.hoisted(() => ({
  getScriptList: vi.fn().mockResolvedValue({ items: [] }),
  getPlaybookList: vi.fn().mockResolvedValue({ items: [] }),
  getScriptDetail: vi.fn().mockResolvedValue({
    id: 109,
    name: '分页外脚本',
    params: [{ name: 'vm', label: '虚拟机', default: '平台默认', is_required: true }],
  }),
  quickExecute: vi.fn().mockResolvedValue({ id: 13 }),
}));

vi.mock('@/app/job/api', () => ({ default: () => api }));
vi.mock('@/utils/request', () => ({ default: () => ({ isLoading: false }) }));
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('script_id=109&mode=test'),
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => (zh.job as Record<string, string>)[key.split('.')[1]] || key }),
}));
vi.mock('@/components/permission', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/script-editor', () => ({ default: () => null }));
vi.mock('@/app/job/components/jobHostSelectionModalRuntime', () => ({
  default: ({ open, singleSelect, onConfirm }: {
    open: boolean;
    singleSelect: boolean;
    onConfirm: (keys: string[], items: unknown[]) => void;
  }) => open && singleSelect ? (
    <button onClick={() => onConfirm(['4'], [{ key: '4', hostName: '隔离目标', ipAddress: '127.0.0.1', osType: 'linux' }])}>
      选择隔离目标
    </button>
  ) : null,
}));
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }),
});

it('按 ID 加载分页之外的脚本，真实测试由操作者输入参数、单选目标并确认', async () => {
  sessionStorage.setItem('job.quick-exec.replay', JSON.stringify({ scriptId: 7, selectedHosts: [{ key: 'old' }] }));
  render(<Page />);
  await screen.findByText('分页外脚本', { selector: '.ant-select-selection-item' });
  expect(api.getScriptDetail).toHaveBeenCalledWith(109);
  expect(api.getScriptList).not.toHaveBeenCalled();
  expect(api.getPlaybookList).not.toHaveBeenCalled();

  const input = screen.getByLabelText('虚拟机');
  expect(input).toHaveProperty('value', '');
  fireEvent.change(input, { target: { value: 'vm-01' } });
  fireEvent.click(screen.getByRole('button', { name: /添加目标主机/ }));
  fireEvent.click(screen.getByRole('button', { name: '选择隔离目标' }));
  fireEvent.click(screen.getByRole('button', { name: /立即执行/ }));

  const dialog = await screen.findByRole('dialog');
  expect(dialog.textContent).toContain('隔离目标');
  expect(api.quickExecute).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole('button', { name: '确认执行' }));
  await waitFor(() => expect(api.quickExecute).toHaveBeenCalledWith(expect.objectContaining({
    script_id: 109,
    target_list: [expect.objectContaining({ target_id: 4 })],
    params: [{ name: 'vm', value: 'vm-01', is_modified: true }],
  })));
});
