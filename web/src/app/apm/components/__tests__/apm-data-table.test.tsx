import { render, screen } from '@testing-library/react';
import type { TableColumnsType } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ApmDataTable from '../apm-data-table';

interface Row {
  count?: number;
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

  it('使用单层承载、固定布局和自适应高度，不创建表体滚动区', () => {
    const { container } = render(
      <ApmDataTable<Row>
        columns={columns}
        dataSource={[{ id: 1, name: 'checkout' }]}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(screen.getByText('checkout')).toBeTruthy();
    expect(container.querySelector('.ant-table-bordered')).toBeNull();
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

  it('表头统一左对齐，同时保留数值正文右对齐', () => {
    render(
      <ApmDataTable<Row>
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '服务数', dataIndex: 'count', align: 'right' },
        ]}
        dataSource={[{ id: 1, name: 'checkout', count: 3 }]}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(getComputedStyle(screen.getByRole('columnheader', { name: '服务数' })).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByText('3').closest('td')! as HTMLElement).textAlign).toBe('right');
  });

  it('指标表可让表头跟随列语义对齐', () => {
    render(
      <ApmDataTable<Row>
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '当前达标率', dataIndex: 'count', align: 'right' },
          { title: '启用状态', key: 'enabled', align: 'center', render: () => '启用' },
        ]}
        dataSource={[{ id: 1, name: 'checkout', count: 99.9 }]}
        headerAlignment="column"
        pagination={false}
        rowKey="id"
      />,
    );

    expect(
      getComputedStyle(screen.getByRole('columnheader', { name: '当前达标率' })).textAlign,
    ).toBe('right');
    expect(
      getComputedStyle(screen.getByRole('columnheader', { name: '启用状态' })).textAlign,
    ).toBe('center');
  });
});
