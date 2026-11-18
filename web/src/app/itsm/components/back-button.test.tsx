import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ItsmBackButton } from './back-button';
const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it('链接保留明确的返回目标和无障碍名称', () => {
  render(<ItsmBackButton href="/itsm/workflow" label="返回流程列表" />);
  const link = screen.getByRole('link', { name: '返回流程列表' });
  expect(link.getAttribute('href')).toBe('/itsm/workflow');
  expect(link.textContent).toBe('');
});
it('由调用方执行返回校验，忙碌时不能返回', () => {
  const leave = vi.fn();
  const { rerender } = render(<ItsmBackButton label="返回集成列表" onClick={leave} />);
  fireEvent.click(screen.getByRole('button', { name: '返回集成列表' }));
  expect(leave).toHaveBeenCalledTimes(1);
  rerender(<ItsmBackButton label="返回集成列表" onClick={leave} disabled />);
  fireEvent.click(screen.getByRole('button', { name: '返回集成列表' }));
  expect(leave).toHaveBeenCalledTimes(1);
});

it('普通返回使用客户端路由，不刷新整个应用', () => {
  render(<ItsmBackButton href="/itsm/workflow" label="返回流程列表" />);
  fireEvent.click(screen.getByRole('link', { name: '返回流程列表' }));
  expect(router.push).toHaveBeenCalledWith('/itsm/workflow');
});
it('修饰键打开新标签不被客户端路由接管', () => {
  render(<ItsmBackButton href="/itsm/workflow" label="返回流程列表" />);
  fireEvent.click(screen.getByRole('link', { name: '返回流程列表' }), { ctrlKey: true });
  expect(router.push).not.toHaveBeenCalled();
});
