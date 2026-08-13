'use client';

import { Table } from 'antd';
import type { TableColumnsType, TablePaginationConfig, TableProps } from 'antd';

import styles from './apm-data-table.module.scss';

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

type ApmDataTableProps<RecordType extends object> = Omit<TableProps<RecordType>, 'bordered'> & {
  headerAlignment?: 'left' | 'column';
};

function alignColumnHeaders<RecordType extends object>(
  columns: TableColumnsType<RecordType> | undefined,
  headerAlignment: NonNullable<ApmDataTableProps<RecordType>['headerAlignment']>,
): TableColumnsType<RecordType> | undefined {
  return columns?.map((column) => {
    const onHeaderCell = column.onHeaderCell;
    const normalizedColumn = {
      ...column,
      onHeaderCell: (...args: Parameters<NonNullable<typeof onHeaderCell>>) => {
        const headerCellProps = onHeaderCell?.(...args) ?? {};

        return {
          ...headerCellProps,
          style: {
            ...headerCellProps.style,
            textAlign: headerAlignment === 'column' ? column.align ?? 'left' : 'left',
          },
        };
      },
    };

    if ('children' in column) {
      return {
        ...normalizedColumn,
        children: alignColumnHeaders(column.children, headerAlignment) ?? [],
      };
    }

    return normalizedColumn;
  });
}

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
  columns,
  headerAlignment = 'left',
  pagination,
  size = 'middle',
  tableLayout = 'fixed',
  ...props
}: ApmDataTableProps<RecordType>) {
  return (
    <Table<RecordType>
      {...props}
      bordered={false}
      className={`${styles.table} ${className}`.trim()}
      columns={alignColumnHeaders(columns, headerAlignment)}
      pagination={normalizePagination(pagination as TableProps<never>['pagination'])}
      size={size}
      tableLayout={tableLayout}
    />
  );
}
