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
