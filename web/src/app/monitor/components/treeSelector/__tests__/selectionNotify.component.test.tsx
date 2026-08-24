import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TreeSelector from '../index';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

vi.mock('../index.module.scss', () => ({
  default: {
    treeWrap: 'treeWrap',
    node: 'node',
    icon: 'icon',
    label: 'label',
    ellipsis: 'ellipsis',
    count: 'count'
  }
}));

const treeData = [
  { title: '全部', key: 'all', children: [] },
  {
    title: '网络',
    key: 'web',
    children: [
      { title: 'Ping', key: '22', children: [] },
      { title: 'TCP', key: '35', children: [] }
    ]
  }
];

afterEach(() => {
  cleanup();
});

describe('TreeSelector 选中回写', () => {
  it('用户点选后 URL 回写同一节点时不再次 onNodeSelect', async () => {
    const onNodeSelect = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <TreeSelector
        showAllMenu
        allowParentSelect
        data={treeData}
        defaultSelectedKey="22"
        onNodeSelect={onNodeSelect}
      />
    );

    expect(onNodeSelect).toHaveBeenCalledTimes(1);
    expect(onNodeSelect).toHaveBeenCalledWith('22');

    await user.click(screen.getByText('TCP'));
    expect(onNodeSelect).toHaveBeenCalledWith('35');
    expect(onNodeSelect).toHaveBeenCalledTimes(2);

    rerender(
      <TreeSelector
        showAllMenu
        allowParentSelect
        data={treeData}
        defaultSelectedKey="35"
        onNodeSelect={onNodeSelect}
      />
    );

    expect(onNodeSelect).toHaveBeenCalledTimes(2);
  });
});
