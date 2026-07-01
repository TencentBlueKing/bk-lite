import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Empty, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  ScreenRenderContext,
  TableColumnConfigItem,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { getOpsChartThemeByMode } from '@/app/ops-analysis/utils/chartTheme';
import { EventTableDetail } from './eventTableDetail';
import {
  parseTableLikeData,
  type TableLikePaginationState,
} from '../shared/tableLikeData';
import { getScreenWidgetScale } from '../shared/screenMetrics';
import styles from '../comTable.module.scss';
const DEFAULT_CELL_MAX_WIDTH = 260;

interface EventTableProps {
  rawData: unknown;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
  onQueryChange?: (params: Record<string, any>) => void;
}

interface EventTableRow {
  [key: string]: any;
}

const EventTable: React.FC<EventTableProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  dataSource,
  screenRenderContext,
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
  const usesScreenDarkTheme = config?.chartThemeMode === 'screen-dark';
  const screenTableTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const widgetScale = getScreenWidgetScale(screenRenderContext);
  const screenTableStyle = useMemo(() => {
    if (!usesScreenDarkTheme) return undefined;

    return {
      '--ops-screen-table-bg': screenTableTheme.panelBg,
      '--ops-screen-table-subtle-bg': screenTableTheme.panelSubtleBg,
      '--ops-screen-table-border': screenTableTheme.panelBorderColor,
      '--ops-screen-table-text': screenTableTheme.axisLabelColor,
      '--ops-screen-table-heading': screenTableTheme.panelTitleColor,
      '--ops-screen-table-muted': screenTableTheme.singleValueMetaColor,
      '--ops-screen-table-accent': screenTableTheme.pieValueColor,
      '--ops-screen-table-header-font-size': `${Math.round(14 * widgetScale)}px`,
      '--ops-screen-table-body-font-size': `${Math.round(13 * widgetScale)}px`,
      '--ops-screen-table-line-height': `${Math.round(20 * widgetScale)}px`,
      '--ops-screen-table-cell-padding-y': `${Math.round(7 * widgetScale)}px`,
      '--ops-screen-table-cell-padding-x': `${Math.round(10 * widgetScale)}px`,
      '--ops-screen-table-pagination-font-size': `${Math.round(12 * widgetScale)}px`,
      '--ops-screen-table-pagination-gap': `${Math.round(6 * widgetScale)}px`,
      '--ops-screen-table-scrollbar-size': `${Math.round(8 * widgetScale)}px`,
    } as React.CSSProperties;
  }, [screenTableTheme, usesScreenDarkTheme, widgetScale]);

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

    const TABLE_HEADER_HEIGHT = Math.round(43 * widgetScale);
    const PAGINATION_HEIGHT = isPaginated ? Math.round(56 * widgetScale) : 0;
    const MIN_BODY_HEIGHT = Math.round(120 * widgetScale);

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
  }, [isPaginated, widgetScale]);

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
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            t('dashboard.atLeastOneVisibleColumn') || '请先配置展示字段'
          }
        />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`ops-analysis-event-table h-full min-h-0 flex flex-col ${
        usesScreenDarkTheme ? styles.screenDarkRoot : ''
      }`}
      style={screenTableStyle}
    >
      <div
        className={`flex-1 min-h-0 overflow-hidden ${
          usesScreenDarkTheme ? styles.screenDarkTableWrap : ''
        }`}
      >
        <CustomTable
          className={usesScreenDarkTheme ? styles.screenDarkTable : undefined}
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

export default EventTable;
