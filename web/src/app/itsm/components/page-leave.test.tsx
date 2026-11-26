import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Modal } from 'antd';
import { afterEach, expect, it, vi } from 'vitest';
import { usePageLeave } from './page-leave';
const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); });
function Editor() { usePageLeave(true); return <a href="/itsm/workflow">返回列表</a>; }
it('放弃编辑后站内跳转走客户端路由，取消不跳转', () => {
  const confirm = vi.spyOn(Modal, 'confirm').mockReturnValue({ destroy: vi.fn(), update: vi.fn() });
  render(<Editor />);
  fireEvent.click(screen.getByRole('link'));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(router.push).not.toHaveBeenCalled();
  confirm.mock.calls[0][0].onOk?.();
  expect(router.push).toHaveBeenCalledWith('/itsm/workflow');
});
