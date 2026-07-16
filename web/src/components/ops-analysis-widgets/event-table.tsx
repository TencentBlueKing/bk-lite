import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CompactEmptyState from '@/components/compact-empty-state';
import type {
  DatasourceItem,
  TableColumnConfigItem,
  ValueConfig,
} from '@/components/ops-analysis-widgets';
import CustomTable from '@/components/custom-table';
import { EventTableDetail } from '@/components/ops-analysis-widgets/event-table-detail';
import {
  parseTableLikeData,
  type TableLikePaginationState,
} from '@/components/ops-analysis-widgets/table-like-data';
import { useTranslation } from '@/utils/i18n';

const DEFAULT_CELL_MAX_WIDTH = 260;

export interface OpsAnalysisEventTableProps {
  rawData: unknown;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  onQueryChange?: (params: Record<string, any>) => void;
}

interface EventTableRow {
  [key: string]: any;
}

const OpsAnalysisEventTable: React.FC<OpsAnalysisEventTableProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  dataSource,
  onQueryChange,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);
  const [queryPagination, setQueryPagination] =
    useState<TableLikePaginationState>({
      current: 1,
      pageSize: 20,
    });
  const [tableScrollY, setTableScrollY] = useState<string>();

  const { rows, pagination, isPaginated } = useMemo(
    () => parseTableLikeData<EventTableRow>(rawData, queryPagination),
    [rawData, queryPagination],
  );

  const configuredColumns = useMemo<TableColumnConfigItem[]>(() => {
    return (config?.tableConfig?.columns || [])
      .filter((col) => col.visible)
      .sort((a, b) => a.order - b.order);
  }, [config?.tableConfig?.columns]);

  const supportsPaginationParams = useMemo(
    () =>
      Array.isArray(dataSource?.params) &&
      dataSource.params.some(
        (param) => param.name === 'page' || param.name === 'page_size',
      ),
    [dataSource?.params],
  );

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const TABLE_HEADER_HEIGHT = 43;
    const PAGINATION_HEIGHT = isPaginated ? 56 : 0;
    const MIN_BODY_HEIGHT = 120;

    const updateScrollY = () => {
      const nextHeight = Math.max(
        container.clientHeight - TABLE_HEADER_HEIGHT - PAGINATION_HEIGHT,
        MIN_BODY_HEIGHT,
      );

      setTableScrollY(`${nextHeight}px`);
    };

    updateScrollY();

    const resizeObserver = new ResizeObserver(() => {
      updateScrollY();
    });

    resizeObserver.observe(container);
    if (container.parentElement) {
      resizeObserver.observe(container.parentElement);
    }

    window.addEventListener('resize', updateScrollY);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateScrollY);
    };
  }, [isPaginated]);

  useEffect(() => {
    setExpandedRowKeys([]);
  }, [rawData]);

  useEffect(() => {
    if (!loading) {
      onReady?.(rows.length > 0);
    }
  }, [loading, onReady, rows.length]);

  useEffect(() => {
    if (!onQueryChange) return;

    const queryParams: Record<string, any> = {};

    if (supportsPaginationParams || isPaginated) {
      queryParams.page = queryPagination.current;
      queryParams.page_size = queryPagination.pageSize;
    }

    onQueryChange(queryParams);
  }, [onQueryChange, queryPagination, supportsPaginationParams, isPaginated]);

  const columns = useMemo((): ColumnsType<EventTableRow> => {
    return configuredColumns.map((col) => {
      const column: any = {
        title: col.title,
        dataIndex: col.key,
        key: col.key,
        ellipsis: { showTitle: false },
        render: (text: any) => (
          <Tooltip placement="topLeft" title={text?.toString()}>
            <div
              style={{
                maxWidth: col.width || DEFAULT_CELL_MAX_WIDTH,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {text?.toString() ?? '-'}
            </div>
          </Tooltip>
        ),
      };

      if (col.width) {
        column.width = col.width;
      }

      return column;
    });
  }, [configuredColumns]);

  const handleTableChange = useCallback((pageConfig: any) => {
    setQueryPagination({
      current: pageConfig?.current || 1,
      pageSize: pageConfig?.pageSize || 20,
    });
  }, []);

  if (!configuredColumns.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <CompactEmptyState
          description={t('dashboard.atLeastOneVisibleColumn') || '请先配置展示字段'}
          className="py-6"
        />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="ops-analysis-event-table h-full min-h-0 flex flex-col"
    >
      <div className="flex-1 min-h-0 overflow-hidden">
        <CustomTable
          columns={columns}
          dataSource={rows}
          loading={loading}
          rowKey={(record, index) =>
            record.id || record.key || index?.toString() || '0'
          }
          size="small"
          pagination={
            isPaginated
              ? {
                current: pagination.current,
                pageSize: pagination.pageSize,
                total: pagination.total,
                showSizeChanger: {
                  getPopupContainer: () => document.body,
                },
                showQuickJumper: true,
                showTotal: (total) =>
                  `${t('common.total')} ${total} ${t('common.items')}`,
              }
              : false
          }
          onChange={isPaginated ? handleTableChange : undefined}
          scroll={
            tableScrollY
              ? { x: 'max-content', y: tableScrollY }
              : { x: 'max-content' }
          }
          expandable={{
            expandedRowKeys,
            onExpandedRowsChange: (keys) => {
              const latest = keys[keys.length - 1];
              setExpandedRowKeys(latest ? [latest] : []);
            },
            expandedRowRender: (record) => <EventTableDetail record={record} />,
          }}
        />
      </div>
    </div>
  );
};

export default OpsAnalysisEventTable;
