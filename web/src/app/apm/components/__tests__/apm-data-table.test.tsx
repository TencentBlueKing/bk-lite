import { render, screen } from '@testing-library/react';
import type { TableColumnsType } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ApmDataTable from '../apm-data-table';

interface Row {
  id: number;
  name: string;
}

const columns: TableColumnsType<Row> = [
  { title: '名称', dataIndex: 'name' },
];

describe('ApmDataTable', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('使用固定布局并保留自适应高度，不创建表体滚动区', () => {
    const { container } = render(
      <ApmDataTable<Row>
        columns={columns}
        dataSource={[{ id: 1, name: 'checkout' }]}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(screen.getByText('checkout')).toBeTruthy();
    expect(container.querySelector('table')?.getAttribute('style')).toContain('table-layout: fixed');
    expect(container.querySelector('.ant-table-body')).toBeNull();
  });

  it('为分页列表提供统一总数和分页规格', () => {
    render(
      <ApmDataTable<Row>
        columns={columns}
        dataSource={[{ id: 1, name: 'checkout' }]}
        pagination={{ current: 1, pageSize: 20, total: 21 }}
        rowKey="id"
      />,
    );

    expect(screen.getByText('共 21 条')).toBeTruthy();
    expect(screen.getAllByLabelText('Page Size').length).toBeGreaterThan(0);
    expect(document.querySelector('.ant-select-selection-item')?.textContent).toContain('20');
  });
});
