import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { UserSelector } from './user-selector';
const searchUsers = vi.hoisted(() => vi.fn().mockResolvedValue({ items: [{ username: 'alice', display_name: 'Alice' }], count: 1 }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => ({ ready: true, searchUsers }) }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/components/user-avatar', () => ({ default: () => null }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('隐藏或未展开的多个用户选择器不预加载，展开后按需查询', async () => {
  render(<><UserSelector ariaLabel="委托人" /><UserSelector ariaLabel="代理人" /></>);
  expect(searchUsers).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: '委托人' }));
  await screen.findByText('Alice (alice)');
  expect(searchUsers).toHaveBeenCalledExactlyOnceWith('', 1);
  fireEvent.change(screen.getByRole('combobox', { name: '委托人' }), { target: { value: 'ali' } });
  await waitFor(() => expect(searchUsers).toHaveBeenLastCalledWith('ali', 1));
});
it('已有值仍显示，禁用选择器不请求候选用户', () => {
  render(<UserSelector disabled value={['alice']} />);
  expect(screen.getByText('alice')).toBeTruthy();
  expect(searchUsers).not.toHaveBeenCalled();
});
