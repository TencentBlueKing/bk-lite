import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Page from './page';

const api = vi.hoisted(() => ({
  ready: true,
  listResources: vi.fn(),
  createResource: vi.fn(),
  updateResource: vi.fn(),
  deleteResource: vi.fn(),
}));

vi.mock('../../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);

it('只读角色能看到模板但看不到写操作', async () => {
  api.listResources.mockResolvedValue({ items: [{ id: 1, name: '使用体验', questions: [] }], can_add: false, can_edit: false, can_delete: false });
  render(<Page />);
  expect(await screen.findByText('使用体验')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '新建' })).toBeNull();
});

it('新建模板时保存题目和必填设置', async () => {
  api.listResources.mockResolvedValue({ items: [], can_add: true, can_edit: true, can_delete: true });
  api.createResource.mockResolvedValue({});
  render(<Page />);
  fireEvent.click(await screen.findByRole('button', { name: '新建' }));
  fireEvent.change(screen.getByLabelText('模板名称'), { target: { value: '使用体验' } });
  fireEvent.click(screen.getByRole('button', { name: '添加题目' }));
  fireEvent.change(screen.getByLabelText('题目 1'), { target: { value: '恢复是否及时' } });
  fireEvent.click(screen.getByRole('checkbox', { name: '题目 1 必填' }));
  fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith('surveys', {
    name: '使用体验', questions: [{ id: expect.any(String), title: '恢复是否及时', required: true }],
  }));
});
