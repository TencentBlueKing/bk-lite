import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, DatePicker, Dropdown, Input, Select, Tooltip, message } from 'antd';
import { MoreOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import type {
  DashboardActionConfig,
  DatasourceItem,
  TableColumnConfigItem,
  TableFilterFieldConfig,
  ValueConfig,
} from '@/components/ops-analysis-widgets';
import {
  applyValueMapping,
  getColorByThreshold,
} from '@/components/ops-analysis-config-sections';
import {
  buildDashboardActionUrl,
  resolveDashboardActionParams,
} from '@/components/ops-analysis-widgets/runtime';
import { formatOpsRequestTime } from '@/components/ops-analysis-widgets/date-time';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import {
  parseTableLikeData,
  resolveTableLikeColumns,
  type TableLikePaginationState,
} from '@/components/ops-analysis-widgets/table-like-data';

const { RangePicker } = DatePicker;
const DEFAULT_CELL_MAX_WIDTH = 260;

export interface OpsAnalysisTableProps {
  rawData: any;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  onQueryChange?: (params: Record<string, any>) => void;
}

interface TableDataItem {
  [key: string]: any;
}

const OpsAnalysisTable: React.FC<OpsAnalysisTableProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  dataSource,
  onQueryChange,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [keywordDrafts, setKeywordDrafts] = useState<Record<string, string>>({});
  const [activeKeywordFieldKey, setActiveKeywordFieldKey] = useState<string>('');
  const [queryPagination, setQueryPagination] = useState<TableLikePaginationState>({
    current: 1,
    pageSize: 20,
  });

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
      (field) => (field.inputType === 'keyword' || field.inputType === 'time_range') && !!field.key,
    );
  }, [filterFields]);

  const nonKeywordFilterFields = useMemo<TableFilterFieldConfig[]>(() => {
    return filterFields.filter((field) => field.inputType !== 'keyword' && !!field.key);
  }, [filterFields]);

  useEffect(() => {
    if (searchableFilterFields.length === 0) {
      if (activeKeywordFieldKey) {
        setActiveKeywordFieldKey('');
      }
      return;
    }

    const exists = searchableFilterFields.some((field) => field.key === activeKeywordFieldKey);
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
            <Dropdown
              trigger={['click']}
              menu={{
                items: dropdownActions.map((action, index) => ({
                  key: String(index),
                  label: action.text,
                })),
                onClick: ({ key }) => {
                  const action = dropdownActions[Number(key)];
                  if (action) {
                    handleActionClick(action, record);
                  }
                },
              }}
            >
              <Button type="link" size="small" className="p-0">
                {t('common.more')}
                <MoreOutlined />
              </Button>
            </Dropdown>
          )}
        </div>
      );
    },
    [handleActionClick, t],
  );

  const antColumns = useMemo((): ColumnsType<TableDataItem> => {
    const colGaugeMax: Record<string, number> = {};
    columnConfigs.forEach((col) => {
      if (col.cellType === 'gauge' && col.cellMax == null) {
        let maxValue = 0;
        for (const row of tableData) {
          const numericValue = Number((row as any)?.[col.key]);
          if (!Number.isNaN(numericValue) && numericValue > maxValue) maxValue = numericValue;
        }
        colGaugeMax[col.key] = maxValue;
      }
    });

    return columnConfigs.map((col) => {
      const columnActions = (config?.actions || []).filter((action) => action.columnKey === col.key);
      const column: any = {
        title: col.title,
        dataIndex: col.key,
        key: col.key,
        ellipsis: { showTitle: false },
        render: (text: any, record: TableDataItem) => {
          if (col.columnType === 'actions') {
            return renderActionButtons(columnActions, record);
          }

          const mapping = applyValueMapping(text, col.valueMappings);
          const cellText = text === null || text === undefined ? '' : String(text);
          const baseText = cellText.trim() ? cellText : '--';
          const displayText = mapping?.text !== undefined ? mapping.text : baseText;

          const numericValue = typeof text === 'number' ? text : parseFloat(String(text));
          const cellColor =
            mapping?.color ||
            (col.cellThresholdColors?.length && !Number.isNaN(numericValue)
              ? getColorByThreshold(numericValue, col.cellThresholdColors, undefined as any)
              : undefined);

          if (col.cellType === 'colorBackground' && cellColor) {
            return (
              <Tooltip placement="topLeft" title={displayText}>
                <div
                  style={{
                    background: cellColor,
                    color: '#fff',
                    fontWeight: 600,
                    borderRadius: 4,
                    padding: '1px 8px',
                    textAlign: 'center',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {displayText}
                </div>
              </Tooltip>
            );
          }

          if (col.cellType === 'gauge' && !Number.isNaN(numericValue)) {
            const maxValue = col.cellMax || colGaugeMax[col.key] || 100;
            const ratio = maxValue > 0 ? Math.min(Math.max(numericValue / maxValue, 0), 1) : 0;
            const barColor = cellColor || '#366ce4';
            return (
              <div className="flex items-center gap-2">
                <div
                  className="relative flex-1 overflow-hidden rounded"
                  style={{ height: 10, background: 'var(--color-fill-2, #f0f0f0)' }}
                >
                  <div
                    className="absolute left-0 top-0 h-full rounded"
                    style={{ width: `${ratio * 100}%`, background: barColor }}
                  />
                </div>
                <span className="shrink-0 text-xs tabular-nums">{displayText}</span>
              </div>
            );
          }

          return (
            <Tooltip placement="topLeft" title={displayText}>
              <div
                style={{
                  maxWidth: col.width || DEFAULT_CELL_MAX_WIDTH,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  ...(mapping?.color ? { color: mapping.color, fontWeight: 600 } : {}),
                }}
              >
                {displayText}
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
  }, [columnConfigs, config?.actions, handleActionClick, renderActionButtons, tableData]);

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

      if (Array.isArray(value) && value.length === 2 && dayjs.isDayjs(value[0]) && dayjs.isDayjs(value[1])) {
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
  }, [onQueryChange, queryPagination, filters]);

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
    return searchableFilterFields.find((field) => field.key === activeKeywordFieldKey);
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
      <div className="mb-3 flex flex-wrap gap-2">
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
                  value={activeKeywordFieldKey ? filters[activeKeywordFieldKey] : undefined}
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
                  suffix={<SearchOutlined style={{ color: 'var(--color-text-3)' }} />}
                  value={
                    activeKeywordFieldKey
                      ? (keywordDrafts[activeKeywordFieldKey] ?? filters[activeKeywordFieldKey] ?? '')
                      : ''
                  }
                  onPressEnter={(event) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    handleKeywordFilterCommit(activeKeywordFieldKey, (event.target as HTMLInputElement).value);
                  }}
                  onChange={(event) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    const nextValue = event.target.value;
                    setKeywordDrafts((prev) => ({
                      ...prev,
                      [activeKeywordFieldKey]: nextValue,
                    }));

                    if (!nextValue) {
                      handleKeywordFilterCommit(activeKeywordFieldKey, '');
                    }
                  }}
                  onBlur={(event) => {
                    if (!activeKeywordFieldKey) {
                      return;
                    }
                    handleKeywordFilterCommit(activeKeywordFieldKey, event.target.value);
                  }}
                  style={{ width: 220 }}
                  allowClear
                />
              )}
            </Input.Group>
          </div>
        )}

        {nonKeywordFilterFields.map((field) => {
          switch (field.inputType) {
            case 'select':
              return (
                <div key={field.key} className="flex items-center gap-2">
                  <span className="text-(--color-text-2) whitespace-nowrap text-[12px]">{field.label}</span>
                  <Select
                    placeholder={t('common.selectTip')}
                    value={filters[field.key]}
                    onChange={(value) => setFilters((prev) => ({ ...prev, [field.key]: value }))}
                    style={{ width: 160 }}
                    allowClear
                    options={field.options?.map((opt) => ({
                      label: opt,
                      value: opt,
                    }))}
                  />
                </div>
              );
            default:
              return null;
          }
        })}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col">
      {renderFilters()}

      <div className="min-h-0 flex-1 overflow-visible">
        <CustomTable
          columns={antColumns}
          dataSource={tableData}
          loading={loading}
          rowKey={(record, index) => record.id || record.key || index?.toString() || '0'}
          size="small"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: {
              getPopupContainer: () => document.body,
            },
            showQuickJumper: true,
            showTotal: (total) => `${t('common.total')} ${total} ${t('common.items')}`,
          }}
          onChange={handleTableChange}
          scroll={{ x: 'max-content' }}
        />
      </div>
    </div>
  );
};

export default OpsAnalysisTable;
