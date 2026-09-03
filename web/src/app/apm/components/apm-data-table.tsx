'use client';

import { Table } from 'antd';
import type { TableColumnsType, TablePaginationConfig, TableProps } from 'antd';
import { useTranslation } from '@/utils/i18n';

import styles from './apm-data-table.module.scss';

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

/**
 * APM 列表只为稳定窄列保留固定宽度；名称等主信息列不设置 width，由表格分配剩余空间。
 * 调用链 Trace ID 需要放下 32 位十六进制，因此入口服务、资源收成稳定窄列，把剩余空间留给 Trace ID。
 *
 * 密度约定：工作面 16px 内边距；表头/单元格 8×12，最右列右侧 20px，避免操作贴边；高度随行数，不锁死视口。
 */
export const APM_TABLE_COLUMN_WIDTHS = {
  actionGroup: 192,
  actionPair: 160,
  compact: 120,
  entryService: 168,
  metric: 132,
  metricWide: 152,
  organization: 160,
  progress: 260,
  relativeTime: 128,
  resource: 220,
  singleAction: 96,
  status: 100,
  timestamp: 168,
  traceId: 288,
  trend: 104,
} as const;

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

function ApmDataTablePaginationTotal({ total }: { total: number }) {
  const { t } = useTranslation();
  return (
    <span className={styles.paginationTotal}>
      {t('apm.common.paginationTotal', '共 {total} 条', { total })}
    </span>
  );
}

const defaultShowTotal = (total: number) => <ApmDataTablePaginationTotal total={total} />;

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
