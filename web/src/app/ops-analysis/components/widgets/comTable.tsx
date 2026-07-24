import React, {
  useEffect,
  useState,
  useMemo,
  useCallback,
} from 'react';
import { Button, Input, Select, DatePicker, Tooltip, message } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import { formatOpsRequestTime } from '@/app/ops-analysis/utils/dateTime';
import { getOpsChartThemeByMode } from '@/app/ops-analysis/utils/chartTheme';
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
  DashboardActionConfig,
} from '@/app/ops-analysis/types/dashBoard';
import {
  buildDashboardActionUrl,
  resolveDashboardActionParams,
} from '@/app/ops-analysis/utils/dashboardActions';
import { getScreenWidgetScale } from './shared/screenMetrics';

const { RangePicker } = DatePicker;
const DEFAULT_CELL_MAX_WIDTH = 260;

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
  
  const { tableData, pagination } = useMemo(() => {
    const parsed = parseTableLikeData<TableDataItem>(rawData, queryPagination);

    return {
      tableData: parsed.rows,
      pagination: parsed.pagination,
    };
  }, [rawData, queryPagination.current, queryPagination.pageSize]);

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
    return resolveTableLikeColumns({
      configuredColumns: config?.tableConfig?.columns,
      schemaFields: dataSource?.field_schema,
      rows: tableData,
    }).filter((col) => col.visible);
  }, [config?.tableConfig?.columns, dataSource?.field_schema, tableData]);

  const handleActionClick = useCallback(
    (action: DashboardActionConfig, record: TableDataItem) => {
      const params = resolveDashboardActionParams(action.params, record);
      const url = buildDashboardActionUrl(action.url, params);
      if (!url) {
        message.warning(t('dashboard.actionUrlUnavailable'));
        return;
      }

      if (action.openMode === 'newTab') {
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
      }

      window.location.href = url;
    },
    [t],
  );

  const renderActionButtons = useCallback(
    (actions: DashboardActionConfig[], record: TableDataItem) => {
      if (actions.length === 0) {
        return '-';
      }

      const visibleActions = actions.slice(0, 2);
      const dropdownActions = actions.slice(2);

      return (
        <div className="flex items-center gap-1">
          {visibleActions.map((action, index) => (
            <Button
              key={`${action.columnKey}_${index}_${action.text}`}
              type="link"
              size="small"
              className="p-0"
              onClick={() => handleActionClick(action, record)}
            >
              {action.text}
            </Button>
          ))}
          {dropdownActions.length > 0 && (
            <MoreActionsDropdown
              items={dropdownActions.map<MoreActionsDropdownItem>((action, index) => ({
                key: String(index),
                label: action.text,
                onClick: () => handleActionClick(action, record),
              }))}
              buttonType="link"
            />
          )}
        </div>
      );
    },
    [handleActionClick, t],
  );

  const antColumns = useMemo((): ColumnsType<TableDataItem> => {
    return columnConfigs.map((col) => {
      const columnActions = (config?.actions || []).filter(
        (action) => action.columnKey === col.key,
      );
      const column: any = {
        title: col.title,
        dataIndex: col.key,
        key: col.key,
        ellipsis: { showTitle: false },
        render: (text: any, record: TableDataItem) => {
          if (col.columnType === 'actions') {
            return renderActionButtons(columnActions, record);
          }

          const cellText = text === null || text === undefined ? '' : String(text);
          const displayText = cellText.trim() ? cellText : '--';

          return (
            <Tooltip placement="topLeft" title={displayText}>
              <div
                style={{
                  maxWidth: DEFAULT_CELL_MAX_WIDTH,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {displayText}
              </div>
            </Tooltip>
          );
        },
      };

      return column;
    });
  }, [columnConfigs, config?.actions, renderActionButtons]);

  useEffect(() => {
    if (!onQueryChange) return;

    const queryParams: Record<string, any> = {
      page: queryPagination.current,
      page_size: queryPagination.pageSize,
    };
    const queryList: Array<Record<string, any>> = [];

    Object.entries(filters).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') {
        return;
      }

      if (
        Array.isArray(value) &&
        value.length === 2 &&
        dayjs.isDayjs(value[0]) &&
        dayjs.isDayjs(value[1])
      ) {
        queryList.push({
          field: key,
          type: 'time',
          start: formatOpsRequestTime(value[0]),
          end: formatOpsRequestTime(value[1]),
        });
        return;
      }

      if (typeof value === 'string') {
        const text = value.trim();
        if (!text) {
          return;
        }
        queryList.push({
          field: key,
          type: 'str*',
          value: text,
        });
      }
    });

    if (queryList.length > 0) {
      queryParams.query_list = queryList;
    }

    onQueryChange(queryParams);
  }, [
    onQueryChange,
    queryPagination,
    filters,
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
        className={`mb-3 flex flex-wrap gap-2 ${usesScreenDarkTheme ? styles.screenDarkFilters : ''}`}
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
                    <SearchOutlined style={{ color: 'var(--color-text-3)' }} />
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
      className={`h-full flex flex-col ${usesScreenDarkTheme ? styles.screenDarkRoot : ''}`}
      style={screenTableStyle}
    >
      {renderFilters()}

      <div
        className={`flex-1 min-h-0 ${
          usesScreenDarkTheme
            ? `overflow-hidden ${styles.screenDarkTableWrap}`
            : 'overflow-visible'
        }`}
      >
        <CustomTable
          className={usesScreenDarkTheme ? styles.screenDarkTable : undefined}
          columns={antColumns}
          dataSource={tableData}
          loading={loading}
          rowKey={(record, index) =>
            record.id || record.key || index?.toString() || '0'
          }
          size="small"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: {
              getPopupContainer: () => document.body,
            },
            showQuickJumper: true,
            showTotal: (total) =>
              `${t('common.total')} ${total} ${t('common.items')}`,
          }}
          onChange={handleTableChange}
          scroll={{ x: 'max-content' }}
        />
      </div>
    </div>
  );
};

export default ComTable;
