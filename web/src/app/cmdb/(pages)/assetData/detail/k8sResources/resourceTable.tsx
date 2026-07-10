'use client';

import React from 'react';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import type { SorterResult } from 'antd/es/table/interface';
import CustomTable from '@/components/custom-table';

export interface K8sResourceTableProps {
  items: Record<string, unknown>[];
  columns: ColumnsType<Record<string, unknown>>;
  loading: boolean;
  page: number;
  pageSize: number;
  count: number;
  onPageChange: (page: number, pageSize: number) => void;
  onSortChange: (field: string, descending: boolean) => void;
}

export const K8sResourceTable: React.FC<K8sResourceTableProps> = ({
  items,
  columns,
  loading,
  page,
  pageSize,
  count,
  onPageChange,
  onSortChange,
}) => {
  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total: count,
    showSizeChanger: true,
    pageSizeOptions: [20, 50, 100],
    onChange: onPageChange,
  };

  return (
    <CustomTable<Record<string, unknown>>
      size="small"
      rowKey="id"
      loading={loading}
      dataSource={items}
      columns={columns}
      pagination={pagination}
      fieldSetting={{
        showSetting: false,
        displayFieldKeys: [],
        choosableFields: [],
      }}
      onChange={(_, __, sorter) => {
        const current = (Array.isArray(sorter) ? sorter[0] : sorter) as SorterResult<Record<string, unknown>>;
        if (current?.field) onSortChange(String(current.field), current.order === 'descend');
      }}
    />
  );
};
