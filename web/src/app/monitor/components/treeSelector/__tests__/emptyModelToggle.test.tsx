import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY } from '@/utils/emptyModelTree';
import TreeSelector from '../index';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../index.module.scss', () => ({
  default: {
    treeWrap: 'treeWrap',
    node: 'node',
    icon: 'icon',
    label: 'label',
    ellipsis: 'ellipsis',
    count: 'count',
  },
}));

const countedTree = [
  {
    title: '操作系统',
    key: 'os',
    children: [
      { title: '主机', key: 'host', count: 3, children: [] },
      { title: '进程', key: 'proc', count: 0, children: [] },
    ],
  },
  {
    title: '数据库',
    key: 'db',
    children: [{ title: 'MySQL', key: 'mysql', count: 0, children: [] }],
  },
];

const plainTree = [
  {
    title: '网络',
    key: 'web',
    children: [
      { title: 'Ping', key: '22', children: [] },
      { title: 'TCP', key: '35', children: [] },
    ],
  },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('监控对象树空模型显隐', () => {
  it('没有实例计数的树不显示开关', async () => {
    render(<TreeSelector data={plainTree} />);

    expect(await screen.findByText('Ping')).toBeTruthy();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('默认显示空模型，切换后立即隐藏并写入 localStorage', async () => {
    const user = userEvent.setup();
    render(<TreeSelector data={countedTree} />);

    const toggle = await screen.findByRole('switch', { name: 'common.showEmptyModel' });
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    expect(screen.getByText('进程')).toBeTruthy();
    expect(screen.getByText('数据库')).toBeTruthy();

    await user.click(toggle);

    expect(localStorage.getItem(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe('true');
    expect(screen.queryByText('进程')).toBeNull();
    expect(screen.queryByText('数据库')).toBeNull();
    expect(screen.queryByText('MySQL')).toBeNull();
    expect(screen.getByText('主机')).toBeTruthy();
    expect(screen.getByRole('switch', { name: 'common.hideEmptyModel' }).getAttribute('aria-checked')).toBe('false');

    await user.click(screen.getByText('common.hideEmptyModel'));

    expect(localStorage.getItem(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY)).toBe('false');
    expect(screen.getByText('进程')).toBeTruthy();
    expect(screen.getByText('数据库')).toBeTruthy();
  });

  it('再次进入时沿用上次隐藏空模型的选择', async () => {
    localStorage.setItem(MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY, 'true');
    render(<TreeSelector data={countedTree} />);

    expect(await screen.findByRole('switch', { name: 'common.hideEmptyModel' })).toBeTruthy();
    expect(screen.getByText('主机')).toBeTruthy();
    expect(screen.queryByText('进程')).toBeNull();
    expect(screen.queryByText('MySQL')).toBeNull();
  });

  it('隐藏时空模型即使匹配搜索也不出现', async () => {
    const user = userEvent.setup();
    render(<TreeSelector data={countedTree} />);

    const toggle = await screen.findByRole('switch', { name: 'common.showEmptyModel' });
    await user.click(toggle);
    const input = screen.getByPlaceholderText('common.searchPlaceHolder');
    await user.type(input, 'MySQL{Enter}');

    expect(screen.queryByText('MySQL')).toBeNull();
    expect(screen.queryByText('主机')).toBeNull();
  });
});
