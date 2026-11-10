import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  ScreenRenderContext,
  TableColumnConfigItem,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { useTranslation } from '@/utils/i18n';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';
import CustomTable from '@/components/custom-table';
import {
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';
import { EventTableDetail } from './eventTableDetail';
import {
  parseTableLikeData,
  type TableLikePaginationState,
} from '../shared/tableLikeData';
import { useTableBodyScrollY } from '../shared/useTableBodyScrollY';
import { getScreenWidgetScale } from '../shared/screenMetrics';
import styles from '../comTable.module.scss';
import WidgetState from '@/app/ops-analysis/components/widget-state';
import { supportsServerPagination } from '@/app/ops-analysis/utils/tablePagination';
import { useInteractionSurface } from '@/app/ops-analysis/context/interactionSurface';
import { InteractionActionCell, useWidgetDataLink } from '@/app/ops-analysis/components/interactionTitleIcon';
import {
  interactionActionColumnTitle,
  interactionActionLinkText,
  isFirstActionColumn,
  readWidgetInteraction,
  tableRowLinkPoint,
  withInteractionActionColumn,
} from '@/app/ops-analysis/utils/interactionLink';
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
  const surface = useInteractionSurface();
  const { openPoint } = useWidgetDataLink(config);
  const dataLink = readWidgetInteraction(config);
  const dataLinkName = dataLink?.kind === 'data' ? dataLink.name : '';
  const [expandedRowKeys, setExpandedRowKeys] = useState<React.Key[]>([]);
  const [queryPagination, setQueryPagination] =
    useState<TableLikePaginationState>({
      current: 1,
      pageSize: 20,
    });
  const usesScreenTheme = isScreenChartThemeMode(config?.chartThemeMode);
  const screenTableTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const widgetScale = getScreenWidgetScale(screenRenderContext);
  const screenTableStyle = useMemo(() => {
    if (!usesScreenTheme) return undefined;

    return {
      '--ops-screen-table-bg': screenTableTheme.panelBg,
      '--ops-screen-table-subtle-bg': screenTableTheme.panelSubtleBg,
      '--ops-screen-table-border': screenTableTheme.panelBorderColor,
      '--ops-screen-table-text': screenTableTheme.axisLabelColor,
      '--ops-screen-table-heading': screenTableTheme.panelTitleColor,
      '--ops-screen-table-muted': screenTableTheme.singleValueMetaColor,
      '--ops-screen-table-accent': screenTableTheme.pieValueColor,
      '--ops-screen-table-row-bg': screenTableTheme.panelBg,
      '--ops-screen-table-row-alt-bg': screenTableTheme.panelSubtleBg,
      '--ops-screen-table-row-hover-bg': screenTableTheme.legendHoverBg,
      '--ops-screen-table-control-bg': screenTableTheme.panelBg,
      '--ops-screen-table-scrollbar-thumb': screenTableTheme.axisPointerColor,
      '--ops-screen-table-scrollbar-track': screenTableTheme.panelSubtleBg,
      '--ops-screen-table-header-font-size': `${Math.round(14 * widgetScale)}px`,
      '--ops-screen-table-body-font-size': `${Math.round(13 * widgetScale)}px`,
      '--ops-screen-table-line-height': `${Math.round(20 * widgetScale)}px`,
      '--ops-screen-table-cell-padding-y': `${Math.round(7 * widgetScale)}px`,
      '--ops-screen-table-cell-padding-x': `${Math.round(10 * widgetScale)}px`,
      '--ops-screen-table-pagination-font-size': `${Math.round(12 * widgetScale)}px`,
      '--ops-screen-table-pagination-gap': `${Math.round(6 * widgetScale)}px`,
      '--ops-screen-table-scrollbar-size': `${Math.round(8 * widgetScale)}px`,
    } as React.CSSProperties;
  }, [screenTableTheme, usesScreenTheme, widgetScale]);

  const supportsPaginationParams = useMemo(
    () => supportsServerPagination(dataSource?.params),
    [dataSource?.params],
  );

  const { rows, pagination, isPaginated } = useMemo(
    () => parseTableLikeData<EventTableRow>(
      rawData,
      queryPagination,
      supportsPaginationParams,
    ),
    [rawData, queryPagination, supportsPaginationParams],
  );
  const { slotRef: tableSlotRef, tableScrollY } = useTableBodyScrollY({
    hasPagination: isPaginated,
  });
  const configuredColumns = useMemo<TableColumnConfigItem[]>(() => {
    return (config?.tableConfig?.columns || [])
      .filter((col) => col.visible)
      .sort((a, b) => a.order - b.order);
  }, [config?.tableConfig?.columns]);

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

    if (supportsPaginationParams) {
      queryParams.page = queryPagination.current;
      queryParams.page_size = queryPagination.pageSize;
    }

    onQueryChange(queryParams);
  }, [onQueryChange, queryPagination, supportsPaginationParams]);

  const columnConfigs = useMemo(() => {
    return withInteractionActionColumn(configuredColumns, dataLink, surface, {
      key: '__interaction',
      title: interactionActionColumnTitle(t),
      columnType: 'actions',
      visible: true,
      order: configuredColumns.length,
    });
  }, [configuredColumns, dataLink, surface, t]);

  const columns = useMemo((): ColumnsType<EventTableRow> => {
    return columnConfigs.map((col, columnIndex) => {
      const column: any = {
        title: col.title,
        dataIndex: col.key,
        key: col.key,
        ellipsis: { showTitle: false },
        render: (text: any, record: EventTableRow) => {
          if (col.columnType === 'actions') {
            return (
              <InteractionActionCell
                link={dataLink}
                surface={surface}
                isFirst={isFirstActionColumn(columnConfigs, columnIndex)}
                label={interactionActionLinkText(dataLinkName, t)}
                onOpen={() => openPoint(tableRowLinkPoint(record))}
              />
            );
          }
          return (
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
          );
        },
      };

      if (col.width) {
        column.width = col.width;
      }

      return column;
    });
  }, [columnConfigs, dataLink, dataLinkName, openPoint, surface, t]);

  const handleTableChange = useCallback((pageConfig: any) => {
    setQueryPagination({
      current: pageConfig?.current || 1,
      pageSize: pageConfig?.pageSize || 20,
    });
  }, []);

  if (!configuredColumns.length) {
    return (
      <WidgetState
        description={t('dashboard.configureDisplayFieldsFirst')}
      />
    );
  }

  return (
    <div
      className={`ops-analysis-event-table flex h-full min-h-0 flex-col pt-2 ${
        usesScreenTheme ? styles.screenDarkRoot : ''
      }`}
      style={screenTableStyle}
    >
      <div
        ref={tableSlotRef}
        className={`${styles.opsTableScroll} flex-1 min-h-0 overflow-hidden ${
          usesScreenTheme ? styles.screenDarkTableWrap : ''
        }`}
      >
        <CustomTable
          className={usesScreenTheme ? styles.screenDarkTable : undefined}
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
                  getPopupContainer: fullscreenPopupContainer,
                },
                showQuickJumper: true,
                showTotal: (total) =>
                    `${t('common.total')} ${total} ${t('common.items')}`,
              }
              : false
          }
          onChange={isPaginated ? handleTableChange : undefined}
          scroll={{
            x: 'max-content',
            y: tableScrollY,
          }}
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
