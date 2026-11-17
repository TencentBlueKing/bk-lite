import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ItsmListTable from './itsm-list-table';
vi.mock('@/components/custom-table', () => ({ default: ({ dataSource, pagination }: { dataSource: { id: number }[]; pagination: { current: number; pageSize: number; total: number; pageSizeOptions: number[]; onChange: (page: number, size: number) => void } }) => <><span>{dataSource.map(item => item.id).join(',')}</span><span>{pagination.pageSizeOptions.join('/')}</span><button onClick={() => pagination.onChange(2, 20)}>下一页</button><button onClick={() => pagination.onChange(2, 100)}>100条</button></> }));
it('统一分页按页展示，切换大小回首页', () => {
  const items = Array.from({ length: 25 }, (_, i) => ({ id: i + 1 }));
  render(<ItsmListTable dataSource={items} />);
  expect(screen.getByText('10/20/50/100')).toBeTruthy();
  fireEvent.click(screen.getByText('下一页'));
  expect(screen.getByText('21,22,23,24,25')).toBeTruthy();
  fireEvent.click(screen.getByText('100条'));
  expect(screen.getByText(items.map(item => item.id).join(','))).toBeTruthy();
});
it('筛选条件变化回第一页，保留用户选择的每页条数', () => {
  const items = Array.from({ length: 30 }, (_, i) => ({ id: i + 1 }));
  const { rerender } = render(<ItsmListTable dataSource={items} queryKey="" />);
  fireEvent.click(screen.getAllByText('下一页').at(-1)!);
  expect(screen.getByText('21,22,23,24,25,26,27,28,29,30')).toBeTruthy();
  rerender(<ItsmListTable dataSource={items} queryKey="新筛选" />);
  expect(screen.queryByText('21,22,23,24,25,26,27,28,29,30')).toBeNull();
});
