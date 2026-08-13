'use client';

import { Table } from 'antd';
import type { TablePaginationConfig, TableProps } from 'antd';

import styles from './apm-data-table.module.scss';

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

const defaultShowTotal = (total: number) => (
  <span className={styles.paginationTotal}>共 {total} 条</span>
);

function normalizePagination(
  pagination: TableProps<never>['pagination'],
): TablePaginationConfig | false | undefined {
  if (pagination === false || pagination === undefined) return pagination;

  return {
    defaultPageSize: 20,
    pageSizeOptions: DEFAULT_PAGE_SIZE_OPTIONS,
    responsive: true,
    showLessItems: true,
    showSizeChanger: true,
    showTotal: defaultShowTotal,
    ...pagination,
  };
}

export default function ApmDataTable<RecordType extends object>({
  className = '',
  pagination,
  size = 'middle',
  tableLayout = 'fixed',
  ...props
}: TableProps<RecordType>) {
  return (
    <Table<RecordType>
      {...props}
      className={`${styles.table} ${className}`.trim()}
      pagination={normalizePagination(pagination as TableProps<never>['pagination'])}
      size={size}
      tableLayout={tableLayout}
    />
  );
}
