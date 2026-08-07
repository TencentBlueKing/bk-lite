import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from 'antd';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import MoreActionsDropdown from '..';

const renderDropdown = (
  items: React.ComponentProps<typeof MoreActionsDropdown>['items'],
  onCardClick: () => void,
) => render(
  <IntlProvider locale="zh" messages={{}} onError={() => undefined}>
    <div onClick={onCardClick}>
      <MoreActionsDropdown
        ariaLabel="更多操作"
        items={items}
        stopPropagation
      />
    </div>
  </IntlProvider>,
);

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  Modal.destroyAll();
  cleanup();
});

describe('MoreActionsDropdown stopPropagation', () => {
  it('编辑菜单动作不会触发外层卡片', async () => {
    const user = userEvent.setup();
    const onCardClick = vi.fn();
    const onEdit = vi.fn();

    renderDropdown([{ key: 'edit', label: '编辑', onClick: onEdit }], onCardClick);

    await user.click(screen.getByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByText('编辑'));

    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it('删除确认框显示时不会触发外层卡片', async () => {
    const user = userEvent.setup();
    const onCardClick = vi.fn();
    const onDelete = vi.fn();

    renderDropdown([
      {
        key: 'delete',
        label: '删除',
        danger: true,
        confirm: {
          title: '确认删除记忆？',
          content: '删除后将移除记忆空间“生产故障知识”及其中的记忆，且无法恢复。',
        },
        onClick: onDelete,
      },
    ], onCardClick);

    await user.click(screen.getByRole('button', { name: '更多操作' }));
    await user.click(await screen.findByText('删除'));

    expect((await screen.findAllByText('确认删除记忆？')).length).toBeGreaterThan(0);
    expect(await screen.findByText(/生产故障知识/)).toBeTruthy();
    expect(onDelete).not.toHaveBeenCalled();
    expect(onCardClick).not.toHaveBeenCalled();
  });
});
