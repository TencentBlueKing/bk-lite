import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ItsmListEntry } from './list-entry';
afterEach(cleanup);
it('页面入口保留链接目标且不触发行选择', () => {
  const rowClick = vi.fn();
  render(<div onClick={rowClick}><ItsmListEntry href="/itsm/form/designer/3">表单甲</ItsmListEntry></div>);
  const link = screen.getByRole('link', { name: '表单甲' });
  expect(link.getAttribute('href')).toBe('/itsm/form/designer/3');
  fireEvent.click(link, { ctrlKey: true });
  expect(rowClick).not.toHaveBeenCalled();
});
it('弹窗入口复用回调，无权限则只有文本', () => {
  const edit = vi.fn();
  const { rerender } = render(<ItsmListEntry onClick={edit}>规则甲</ItsmListEntry>);
  fireEvent.click(screen.getByRole('button', { name: '规则甲' }));
  expect(edit).toHaveBeenCalledTimes(1);
  rerender(<ItsmListEntry allowed={false} onClick={edit}>规则甲</ItsmListEntry>);
  expect(screen.queryByRole('button')).toBeNull();
  fireEvent.click(screen.getByText('规则甲'));
  expect(edit).toHaveBeenCalledTimes(1);
});
it('未配置入口的名称不伪装成链接', () => {
  render(<ItsmListEntry>只读名称</ItsmListEntry>);
  expect(screen.queryByRole('link')).toBeNull();
  expect(screen.queryByRole('button')).toBeNull();
});
