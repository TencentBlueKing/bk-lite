import React from 'react';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CatalogState from '../catalog-state';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

afterEach(cleanup);

describe('CatalogState', () => {
  it('为错误状态提供可防重的恢复动作', async () => {
    const retry = vi.fn();
    const user = userEvent.setup();

    renderWithApmIntl(<CatalogState kind="error" onRetry={retry} retryLoading />);

    const button = screen.getByRole('button', { name: /重新加载/ });
    expect(button.classList.contains('ant-btn-loading')).toBe(true);
    await user.click(button);
    expect(retry).not.toHaveBeenCalled();
  });

  it('允许空状态承载上下文动作', async () => {
    const clear = vi.fn();
    const user = userEvent.setup();

    renderWithApmIntl(
      <CatalogState
        kind="empty"
        description="没有匹配结果"
        action={<button type="button" onClick={clear}>清除筛选</button>}
      />,
    );

    await user.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(clear).toHaveBeenCalledTimes(1);
  });

  it('权限状态只给出申请路径，不渲染无效重试', () => {
    renderWithApmIntl(<CatalogState kind="forbidden" onRetry={vi.fn()} />);

    expect(screen.queryByRole('button', { name: '重新加载' })).toBeNull();
    expect(screen.getByText('请联系组织管理员申请查看权限。')).not.toBeNull();
  });
});
