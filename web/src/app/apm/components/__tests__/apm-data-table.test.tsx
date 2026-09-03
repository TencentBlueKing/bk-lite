import { screen } from '@testing-library/react';
import { Space } from 'antd';
import type { TableColumnsType } from 'antd';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '../apm-data-table';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

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
    const { container } = renderWithApmIntl(
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
    renderWithApmIntl(
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

  it('统一覆盖存量数值列和状态列的对齐配置', () => {
    renderWithApmIntl(
      <ApmDataTable<Row>
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '服务数', dataIndex: 'count', align: 'right' },
          { title: '状态', key: 'status', align: 'center', render: () => '正常' },
        ]}
        dataSource={[{ id: 1, name: 'checkout', count: 3 }]}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(getComputedStyle(screen.getByRole('columnheader', { name: '服务数' })).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByText('3').closest('td')! as HTMLElement).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByText('正常').closest('td')! as HTMLElement).textAlign).toBe('left');
  });

  it('兼容存量表头参数并递归统一分组列左对齐', () => {
    renderWithApmIntl(
      <ApmDataTable<Row>
        columns={[
          { title: '名称', dataIndex: 'name' },
          {
            title: '指标',
            children: [
              { title: '当前达标率', dataIndex: 'count', align: 'right' },
              { title: '启用状态', key: 'enabled', align: 'center', render: () => '启用' },
            ],
          },
        ]}
        dataSource={[{ id: 1, name: 'checkout', count: 99.9 }]}
        headerAlignment="column"
        pagination={false}
        rowKey="id"
      />,
    );

    expect(
      getComputedStyle(screen.getByRole('columnheader', { name: '当前达标率' })).textAlign,
    ).toBe('left');
    expect(
      getComputedStyle(screen.getByRole('columnheader', { name: '启用状态' })).textAlign,
    ).toBe('left');
    expect(getComputedStyle(screen.getByText('99.9').closest('td')! as HTMLElement).textAlign).toBe('left');
  });

  it('将操作列和纵向复合内容所在单元格一并归左', () => {
    renderWithApmIntl(
      <ApmDataTable<Row>
        columns={[
          {
            title: <span className="flex items-end text-right">名称</span>,
            dataIndex: 'name',
            render: (value) => <Space direction="vertical" className="!items-end"><span>{value}</span></Space>,
          },
          {
            title: '操作',
            key: 'action',
            align: 'right',
            render: () => (
              <div>
                <Space className="w-full justify-end"><span>编辑</span></Space>
              </div>
            ),
          },
        ]}
        dataSource={[{ id: 1, name: 'checkout' }]}
        pagination={false}
        rowKey="id"
      />,
    );

    expect(getComputedStyle(screen.getByRole('columnheader', { name: '名称' })).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByText('checkout').closest('td')! as HTMLElement).textAlign).toBe('left');
    expect(getComputedStyle(screen.getByText('编辑').closest('td')! as HTMLElement).textAlign).toBe('left');

    const actionSpace = screen.getByText('编辑').closest('.ant-space') as HTMLElement;
    expect(['flex-end', 'end', 'right']).not.toContain(getComputedStyle(actionSpace).justifyContent);
    expect(getComputedStyle(actionSpace).width).not.toBe('100%');
  });

  it('为三连操作列预留右侧贴边空间', () => {
    expect(APM_TABLE_COLUMN_WIDTHS.actionGroup).toBe(192);
    expect(APM_TABLE_COLUMN_WIDTHS.actionPair).toBe(160);
    expect(APM_TABLE_COLUMN_WIDTHS.singleAction).toBe(96);
    expect(APM_TABLE_COLUMN_WIDTHS.traceId).toBe(288);
    expect(APM_TABLE_COLUMN_WIDTHS.entryService).toBe(168);
    expect(APM_TABLE_COLUMN_WIDTHS.resource).toBe(220);
  });
});
