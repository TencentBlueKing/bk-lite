'use client';

import { Table } from 'antd';
import type { TableColumnsType, TablePaginationConfig, TableProps } from 'antd';

import styles from './apm-data-table.module.scss';

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

type ApmDataTableProps<RecordType extends object> = Omit<TableProps<RecordType>, 'bordered'> & {
  /** @deprecated APM 表格已统一使用左对齐；保留此属性只为兼容存量调用。 */
  headerAlignment?: 'left' | 'column';
};

function alignColumnsLeft<RecordType extends object>(
  columns: TableColumnsType<RecordType> | undefined,
): TableColumnsType<RecordType> | undefined {
  return columns?.map((column) => {
    const onHeaderCell = column.onHeaderCell;
    const normalizedColumn = {
      ...column,
      align: 'left' as const,
      onHeaderCell: (...args: Parameters<NonNullable<typeof onHeaderCell>>) => {
        const headerCellProps = onHeaderCell?.(...args) ?? {};

        return {
          ...headerCellProps,
          style: {
            ...headerCellProps.style,
            textAlign: 'left' as const,
          },
        };
      },
    };

    if ('children' in column) {
      return {
        ...normalizedColumn,
        children: alignColumnsLeft(column.children) ?? [],
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
  headerAlignment,
  pagination,
  size = 'middle',
  tableLayout = 'fixed',
  ...props
}: ApmDataTableProps<RecordType>) {
  // 存量页面可能仍传入 column；公共契约始终以节点管理的左对齐规范为准。
  void headerAlignment;

  return (
    <Table<RecordType>
      {...props}
      bordered={false}
      className={`${styles.table} ${className}`.trim()}
      columns={alignColumnsLeft(columns)}
      pagination={normalizePagination(pagination as TableProps<never>['pagination'])}
      size={size}
      tableLayout={tableLayout}
    />
  );
}
