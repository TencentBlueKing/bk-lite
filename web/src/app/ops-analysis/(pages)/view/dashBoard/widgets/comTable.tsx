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
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import CustomTable from '@/components/custom-table';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import type {
  ResponseFieldDefinition,
  DatasourceItem,
} from '@/app/ops-analysis/types/dataSource';
import type {
  ValueConfig,
  TableColumnConfigItem,
  TableFilterFieldConfig,
} from '@/app/ops-analysis/types/dashBoard';

const { RangePicker } = DatePicker;
const DEFAULT_CELL_MAX_WIDTH = 260;

interface ComTableProps {
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

// 后端标准格式：每个 namespace 的 data 字段是带分页的对象
interface NamespacePagedData {
  data?: TableDataItem[];
  count?: number;
  page?: number;
  page_size?: number;
}

interface NamespaceGroupedItem {
  namespace_id?: string | number;
  data?: NamespacePagedData;
}

const ComTable: React.FC<ComTableProps> = ({
  rawData,
  loading = false,
  onReady,
  config,
  dataSource,
  onQueryChange,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<Record<string, any>>({});
  const [keywordDrafts, setKeywordDrafts] = useState<Record<string, string>>(
    {},
  );
  const [activeKeywordFieldKey, setActiveKeywordFieldKey] =
    useState<string>('');
  const [selectedNamespace, setSelectedNamespace] = useState<string>();
  const [queryPagination, setQueryPagination] = useState<{
    current: number;
    pageSize: number;
  }>({
    current: 1,
    pageSize: 20,
  });
  const lastQueryParamsRef = useRef<string>('');
  const { namespaceList, fetchNamespaces } = useOpsAnalysis();

  useEffect(() => {
    void fetchNamespaces();
  }, [fetchNamespaces]);

  const { tableData, pagination } = useMemo(() => {
    const empty = {
      tableData: [],
      pagination: { current: 1, pageSize: 20, total: 0 },
    };

    if (!Array.isArray(rawData) || rawData.length === 0) return empty;

    const rows: TableDataItem[] = [];
    let total = 0;
    let current = 1;
    let pageSize = 20;

    for (const item of rawData as NamespaceGroupedItem[]) {
      const namespaceId = item?.namespace_id || '-';
      const paged = item?.data;
      const records = Array.isArray(paged?.data) ? paged.data! : [];
      records.forEach((record) =>
        rows.push({ namespace_id: namespaceId, ...record }),
      );
      total += Number(paged?.count) || records.length;
      if (paged?.page) current = Number(paged.page);
      if (paged?.page_size) pageSize = Number(paged.page_size);
    }

    return { tableData: rows, pagination: { current, pageSize, total } };
  }, [rawData]);

  const namespaceOptions = useMemo((): Array<{
    label: string;
    value: string;
  }> => {
    const configuredOptions = dataSource?.namespace_options || [];
    if (configuredOptions.length > 0) {
      return configuredOptions
        .filter(
          (item) =>
            item &&
            item.id !== undefined &&
            item.id !== null &&
            typeof item.name === 'string' &&
            !!item.name.trim(),
        )
        .map((item) => ({
          label: item.name,
          value: String(item.id),
        }));
    }

    const configuredNamespaceIds = (dataSource?.namespaces || [])
      .map((id) => Number(id))
      .filter((id) => !Number.isNaN(id));

    if (configuredNamespaceIds.length === 0) {
      return [];
    }

    const namespaceMap = new Map(
      namespaceList.map((item) => [item.id, item.name || String(item.id)]),
    );

    return configuredNamespaceIds.map((id) => ({
      label: namespaceMap.get(id) || String(id),
      value: String(id),
    }));
  }, [dataSource?.namespace_options, dataSource?.namespaces, namespaceList]);

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

  const nonKeywordFilterFields = useMemo<TableFilterFieldConfig[]>(() => {
    return filterFields.filter(
      (field) => field.inputType !== 'keyword' && !!field.key,
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

  useEffect(() => {
    if (namespaceOptions.length === 0) {
      if (selectedNamespace) {
        setSelectedNamespace(undefined);
      }
      return;
    }

    const optionValues = namespaceOptions.map((opt) => opt.value);
    if (!selectedNamespace || !optionValues.includes(selectedNamespace)) {
      setSelectedNamespace(optionValues[0]);
    }
  }, [namespaceOptions, selectedNamespace]);

  const columnConfigs = useMemo((): TableColumnConfigItem[] => {
    const widgetColumns = config?.tableConfig?.columns;
    if (widgetColumns && widgetColumns.length > 0) {
      return widgetColumns
        .filter((col) => col.visible)
        .sort((a, b) => a.order - b.order);
    }

    const schemaFields = dataSource?.field_schema;
    if (schemaFields && schemaFields.length > 0) {
      return schemaFields.map(
        (field: ResponseFieldDefinition, index: number) => ({
          key: field.key,
          title: field.title || field.key,
          visible: true,
          order: index,
        }),
      );
    }

    if (tableData.length > 0) {
      const firstRow = tableData[0];
      return Object.keys(firstRow).map((key, index) => ({
        key,
        title: key,
        visible: true,
        order: index,
      }));
    }

    return [];
  }, [config?.tableConfig?.columns, dataSource?.field_schema, tableData]);

  const antColumns = useMemo((): ColumnsType<TableDataItem> => {
    const namespaceColumn: ColumnsType<TableDataItem>[number] = {
      title: t('namespace.title'),
      dataIndex: 'namespace_id',
      key: 'namespace_id',
      width: 180,
      fixed: 'left',
      ellipsis: { showTitle: false },
      render: (text: any) => (
        <Tooltip placement="topLeft" title={text?.toString()}>
          <div
            style={{
              maxWidth: DEFAULT_CELL_MAX_WIDTH,
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

    const dataColumns = columnConfigs
      .filter((col) => col.key !== 'namespace_id')
      .map((col) => {
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

    return [namespaceColumn, ...dataColumns];
  }, [columnConfigs, t]);

  useEffect(() => {
    if (pagination?.current && pagination?.pageSize) {
      setQueryPagination((prev) => {
        if (
          prev.current === pagination.current &&
          prev.pageSize === pagination.pageSize
        ) {
          return prev;
        }
        return {
          current: pagination.current,
          pageSize: pagination.pageSize,
        };
      });
    }
  }, [pagination?.current, pagination?.pageSize]);

  useEffect(() => {
    if (!onQueryChange) return;

    if (namespaceOptions.length > 0 && !selectedNamespace) {
      return;
    }

    const queryParams: Record<string, any> = {
      page: queryPagination.current,
      page_size: queryPagination.pageSize,
    };
    const queryList: Array<Record<string, any>> = [];

    if (namespaceOptions.length > 0 && selectedNamespace) {
      queryParams.namespace_ids = [Number(selectedNamespace)];
    }

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
          start: value[0].format('YYYY-MM-DD HH:mm:ss'),
          end: value[1].format('YYYY-MM-DD HH:mm:ss'),
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

    const queryKey = JSON.stringify(queryParams);
    if (lastQueryParamsRef.current === queryKey) {
      return;
    }
    lastQueryParamsRef.current = queryKey;
    onQueryChange(queryParams);
  }, [
    onQueryChange,
    queryPagination,
    filters,
    namespaceOptions,
    selectedNamespace,
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
      if (namespaceOptions.length === 0) {
        return null;
      }

      return (
        <div className="mb-3 flex items-center gap-2">
          <span className="text-(--color-text-2) text-[13px] whitespace-nowrap">
            {t('namespace.title')}
          </span>
          <Select
            value={selectedNamespace}
            options={namespaceOptions}
            placeholder={t('dashboard.allNamespaces')}
            onChange={(value) => {
              setSelectedNamespace(value as string);
              setQueryPagination((prev) => ({ ...prev, current: 1 }));
            }}
            style={{ minWidth: 220 }}
          />
        </div>
      );
    }

    return (
      <div className="mb-3 flex flex-wrap gap-2">
        {namespaceOptions.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-(--color-text-2) text-[12px] whitespace-nowrap">
              {t('namespace.title')}
            </span>
            <Select
              value={selectedNamespace}
              options={namespaceOptions}
              placeholder={t('dashboard.allNamespaces')}
              onChange={(value) => {
                setSelectedNamespace(value as string);
                setQueryPagination((prev) => ({ ...prev, current: 1 }));
              }}
              style={{ minWidth: 180 }}
            />
          </div>
        )}

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

        {nonKeywordFilterFields.map((field) => {
          switch (field.inputType) {
            case 'select':
              return (
                <div key={field.key} className="flex items-center gap-2">
                  <span className="text-(--color-text-2) text-[12px] whitespace-nowrap">
                    {field.label}
                  </span>
                  <Select
                    placeholder={t('common.selectTip')}
                    value={filters[field.key]}
                    onChange={(value) =>
                      setFilters((prev) => ({ ...prev, [field.key]: value }))
                    }
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
    <div className="h-full flex flex-col overflow-hidden">
      {renderFilters()}

      <div className="flex-1 overflow-hidden">
        <CustomTable
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
            showSizeChanger: true,
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
