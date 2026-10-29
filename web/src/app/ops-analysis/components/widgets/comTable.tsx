import React, {
  useEffect,
  useState,
  useMemo,
  useCallback,
  useRef,
} from 'react';
import { Input, Select, DatePicker, Tooltip } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import {
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  parseTableLikeData,
  resolveTableLikeColumns,
  type TableLikePaginationState,
} from './shared/tableLikeData';
import styles from './comTable.module.scss';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  ScreenRenderContext,
  ValueConfig,
  TableColumnConfigItem,
  TableFilterFieldConfig,
} from '@/app/ops-analysis/types/dashBoard';
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
import { resolveTableCellPresentation } from '@/app/ops-analysis/utils/tableCellStyle';
import {
  formatVisibleChartValue,
  hasValueFormatConfigured,
} from '@/app/ops-analysis/utils/chartValueFormat';
import { getScreenWidgetScale } from './shared/screenMetrics';
import { supportsServerPagination } from '@/app/ops-analysis/utils/tablePagination';
import {
  applyTableRowFilters,
  buildTableQueryList,
} from '@/app/ops-analysis/utils/tableQueryList';
import { useTableBodyScrollY } from './shared/useTableBodyScrollY';
import {
  opsTableCellTextStyle,
  resolveOpsTableColumnWidth,
} from '@/app/ops-analysis/utils/opsTableColumn';

const { RangePicker } = DatePicker;
const TOOLTIP_MAX_WIDTH = 480;
const TOOLTIP_STYLES = {
  root: { maxWidth: TOOLTIP_MAX_WIDTH },
  body: { whiteSpace: 'pre-line' as const, maxWidth: TOOLTIP_MAX_WIDTH },
};

interface ComTableProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
  onQueryChange?: (params: Record<string, any>) => void;
}

interface TableDataItem {
  [key: string]: any;
}

const ComTable: React.FC<ComTableProps> = ({
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
  const tableContainerRef = useRef<HTMLDivElement | null>(null);
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [keywordDrafts, setKeywordDrafts] = useState<Record<string, string>>(
    {},
  );
  const [activeKeywordFieldKey, setActiveKeywordFieldKey] =
    useState<string>('');
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

  const { tableData, pagination, isPaginated } = useMemo(() => {
    const parsed = parseTableLikeData<TableDataItem>(
      rawData,
      queryPagination,
      supportsPaginationParams,
    );

    return {
      tableData: parsed.rows,
      pagination: parsed.pagination,
      isPaginated: parsed.isPaginated,
    };
  }, [rawData, queryPagination.current, queryPagination.pageSize, supportsPaginationParams]);
  const displayedTableData = useMemo(
    () => applyTableRowFilters(tableData, filters),
    [filters, tableData],
  );
  const tableScrollY = useTableBodyScrollY({
    containerRef: tableContainerRef,
    hasPagination: isPaginated,
    scale: widgetScale,
  });

  const filterFields = useMemo<TableFilterFieldConfig[]>(() => {
    return config?.tableConfig?.filterFields || [];
  }, [config?.tableConfig?.filterFields]);

  const searchableFilterFields = useMemo<TableFilterFieldConfig[]>(() => {
    return filterFields.filter(
      (field) =>
        (field.inputType === 'keyword' || field.inputType === 'time_range') &&
        !!field.key,
    );
  }, [filterFields]);

  useEffect(() => {
    if (searchableFilterFields.length === 0) {
      if (activeKeywordFieldKey) {
        setActiveKeywordFieldKey('');
      }
      return;
    }

    const exists = searchableFilterFields.some(
      (field) => field.key === activeKeywordFieldKey,
    );
    if (!exists) {
      setActiveKeywordFieldKey(searchableFilterFields[0].key);
    }
  }, [searchableFilterFields, activeKeywordFieldKey]);

  const columnConfigs = useMemo((): TableColumnConfigItem[] => {
    const visible = resolveTableLikeColumns({
      configuredColumns: config?.tableConfig?.columns,
      schemaFields: dataSource?.field_schema,
      rows: tableData,
    }).filter((col) => col.visible);
    return withInteractionActionColumn(visible, dataLink, surface, {
      key: '__interaction',
      title: interactionActionColumnTitle(t),
      columnType: 'actions',
      visible: true,
      order: visible.length,
    });
  }, [config?.tableConfig?.columns, dataLink, dataSource?.field_schema, surface, t, tableData]);

  const antColumns = useMemo((): ColumnsType<TableDataItem> => {
    return columnConfigs.map((col, columnIndex) => {
      const columnWidth = resolveOpsTableColumnWidth(col.width);
      const column: any = {
        title: col.title,
        dataIndex: col.key,
        key: col.key,
        ...(columnWidth !== undefined ? { width: columnWidth } : {}),
        ellipsis: { showTitle: false },
        render: (text: any, record: TableDataItem) => {
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

          const presentation = resolveTableCellPresentation(text, col);
          const formattedPresentation =
            presentation.mode === 'text' &&
            col.key === 'value' &&
            hasValueFormatConfigured(config)
              ? {
                ...presentation,
                displayText: formatVisibleChartValue(text, config),
              }
              : presentation;
          if (formattedPresentation.mode === 'colorBackground') {
            return (
              <Tooltip
                placement="topLeft"
                title={formattedPresentation.tooltipText}
                styles={TOOLTIP_STYLES}
              >
                <div
                  role="img"
                  aria-label={formattedPresentation.tooltipText}
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: 3,
                    background: formattedPresentation.color,
                  }}
                >
                  <span className="sr-only">{formattedPresentation.tooltipText}</span>
                </div>
              </Tooltip>
            );
          }

          return (
            <Tooltip
              placement="topLeft"
              title={formattedPresentation.displayText}
              styles={TOOLTIP_STYLES}
            >
              <div style={opsTableCellTextStyle(formattedPresentation.color)}>
                {formattedPresentation.displayText}
              </div>
            </Tooltip>
          );
        },
      };

      return column;
    });
  }, [columnConfigs, config, dataLink, dataLinkName, openPoint, surface, t]);

  useEffect(() => {
    if (!onQueryChange) return;

    const queryParams: Record<string, any> = {};
    if (supportsPaginationParams) {
      queryParams.page = queryPagination.current;
      queryParams.page_size = queryPagination.pageSize;
    }
    const queryList = buildTableQueryList(filters);
    if (queryList.length > 0) {
      queryParams.query_list = queryList;
    }

    onQueryChange(queryParams);
  }, [
    onQueryChange,
    queryPagination,
    filters,
    supportsPaginationParams,
  ]);

  useEffect(() => {
    if (!loading) {
      const hasData = tableData && tableData.length > 0;
      onReady?.(hasData);
    }
  }, [tableData, loading, onReady]);

  const handleKeywordFilterCommit = useCallback(
    (key: string, value: string) => {
      const nextValue = value.trim();
      setFilters((prev) => {
        const nextFilters = { ...prev };
        searchableFilterFields.forEach((field) => {
          if (field.key !== key) {
            delete nextFilters[field.key];
          }
        });

        if (nextValue) {
          nextFilters[key] = nextValue;
        } else {
          delete nextFilters[key];
        }

        if (JSON.stringify(nextFilters) === JSON.stringify(prev)) {
          return prev;
        }

        setQueryPagination((pagePrev) => ({ ...pagePrev, current: 1 }));
        return nextFilters;
      });
    },
    [searchableFilterFields],
  );

  const handleKeywordFieldSwitch = useCallback(
    (nextKey: string) => {
      setActiveKeywordFieldKey(nextKey);
      setFilters((prev) => {
        const nextFilters = { ...prev };
        searchableFilterFields.forEach((field) => {
          if (field.key !== nextKey) {
            delete nextFilters[field.key];
          }
        });

        if (JSON.stringify(nextFilters) === JSON.stringify(prev)) {
          return prev;
        }

        setQueryPagination((pagePrev) => ({ ...pagePrev, current: 1 }));
        return nextFilters;
      });
    },
    [searchableFilterFields],
  );

  const activeSearchField = useMemo(() => {
    return searchableFilterFields.find(
      (field) => field.key === activeKeywordFieldKey,
    );
  }, [searchableFilterFields, activeKeywordFieldKey]);

  const handleTableChange = useCallback((pageConfig: any) => {
    setQueryPagination({
      current: pageConfig?.current || 1,
      pageSize: pageConfig?.pageSize || 20,
    });
  }, []);

  const renderFilters = () => {
    if (!filterFields || filterFields.length === 0) {
      return null;
    }

    return (
      <div
        className="mb-3 flex flex-wrap gap-2"
      >
        {searchableFilterFields.length > 0 && (
          <div className="flex items-center">
            <Input.Group compact>
              <Select
                value={activeKeywordFieldKey}
                placeholder={t('common.selectTip')}
                onChange={handleKeywordFieldSwitch}
                style={{ width: 130 }}
                options={searchableFilterFields.map((field) => ({
                  label: field.label || field.key,
                  value: field.key,
                }))}
              />
              {activeSearchField?.inputType === 'time_range' ? (
                <RangePicker
                  placeholder={[t('common.startTime'), t('common.endTime')]}
                  value={
                    activeKeywordFieldKey
                      ? filters[activeKeywordFieldKey]
                      : undefined
                  }
                  onChange={(dates) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    setFilters((prev) => ({
                      ...prev,
                      [activeKeywordFieldKey]: dates,
                    }));
                    setQueryPagination((prev) => ({ ...prev, current: 1 }));
                  }}
                  showTime
                />
              ) : (
                <Input
                  placeholder={t('dashboard.searchPlaceholder')}
                  suffix={
                    <SearchOutlined
                      className="cursor-pointer"
                      style={{
                        color: 'var(--ops-screen-table-muted, var(--color-text-3))',
                      }}
                      onClick={() => {
                        if (!activeKeywordFieldKey) {
                          return;
                        }
                        handleKeywordFilterCommit(
                          activeKeywordFieldKey,
                          keywordDrafts[activeKeywordFieldKey]
                            ?? filters[activeKeywordFieldKey]
                            ?? '',
                        );
                      }}
                    />
                  }
                  value={
                    activeKeywordFieldKey
                      ? (keywordDrafts[activeKeywordFieldKey] ??
                        filters[activeKeywordFieldKey] ??
                        '')
                      : ''
                  }
                  onPressEnter={(e) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    handleKeywordFilterCommit(
                      activeKeywordFieldKey,
                      (e.target as HTMLInputElement).value,
                    );
                  }}
                  onChange={(e) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    const nextValue = e.target.value;
                    setKeywordDrafts((prev) => ({
                      ...prev,
                      [activeKeywordFieldKey]: nextValue,
                    }));

                    if (!nextValue) {
                      handleKeywordFilterCommit(activeKeywordFieldKey, '');
                    }
                  }}
                  onBlur={(e) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    handleKeywordFilterCommit(
                      activeKeywordFieldKey,
                      e.target.value,
                    );
                  }}
                  style={{ width: 220 }}
                  allowClear
                />
              )}
            </Input.Group>
          </div>
        )}

      </div>
    );
  };

  return (
    <div
      className={`mt-2 h-full flex flex-col ${usesScreenTheme ? styles.screenDarkRoot : ''}`}
      style={screenTableStyle}
    >
      {renderFilters()}

      <div
        ref={tableContainerRef}
        className={`flex-1 min-h-0 ${
          usesScreenTheme
            ? `overflow-hidden ${styles.screenDarkTableWrap}`
            : 'overflow-hidden'
        }`}
      >
        <CustomTable
          className={usesScreenTheme ? styles.screenDarkTable : undefined}
          columns={antColumns}
          dataSource={displayedTableData}
          loading={loading}
          rowKey={(record) => {
            const row = record as Record<string, unknown>;
            if (row.id != null && row.id !== '') return String(row.id);
            if (row.key != null && row.key !== '') return String(row.key);
            try {
              return JSON.stringify(row);
            } catch {
              return 'row';
            }
          }}
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
          scroll={{ x: 'max-content', y: tableScrollY }}
        />
      </div>
    </div>
  );
};

export default ComTable;
