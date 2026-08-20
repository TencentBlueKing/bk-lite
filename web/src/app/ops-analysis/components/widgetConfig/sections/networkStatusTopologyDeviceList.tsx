import React, { useMemo } from 'react';
import { Button, Input, Pagination, Select, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { normalizeNetworkStatusTopologyNodeLimit } from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import { mergePageSelection } from '../utils/networkStatusTopologyDevicePage';
import type { NetworkSelectOption } from '../hooks/useNetworkStatusTopologyConfig';

interface NetworkStatusTopologyDeviceListProps {
  value?: string[];
  onChange?: (value: string[]) => void;
  nodeLimit?: number;
  listedOptions: NetworkSelectOption[];
  instanceTotal: number;
  instancePage: number;
  instancePageSize: number;
  instanceKeyword: string;
  instancesLoading: boolean;
  modelsLoading: boolean;
  modelFilter?: string;
  modelOptions: { label: string; value: string }[];
  onModelFilterChange: (value?: string) => void;
  onSearch: (keyword: string) => void;
  onPageChange: (page: number, pageSize: number) => void;
}

export const NetworkStatusTopologyDeviceList: React.FC<
  NetworkStatusTopologyDeviceListProps
> = ({
  value,
  onChange,
  nodeLimit,
  listedOptions,
  instanceTotal,
  instancePage,
  instancePageSize,
  instanceKeyword,
  instancesLoading,
  modelsLoading,
  modelFilter,
  modelOptions,
  onModelFilterChange,
  onSearch,
  onPageChange,
}) => {
  const { t } = useTranslation();
  const selectedValues = Array.isArray(value) ? value.map(String) : [];
  const limit = normalizeNetworkStatusTopologyNodeLimit(nodeLimit);
  const atLimit = selectedValues.length >= limit;

  const columns: ColumnsType<NetworkSelectOption> = useMemo(
    () => [
      {
        title: t('dashboard.networkTopoInstance'),
        dataIndex: 'name',
        ellipsis: true,
        render: (name: string | undefined, record) => (
          <EllipsisWithTooltip className="max-w-full" text={name || record.label} />
        ),
      },
      {
        title: t('dashboard.networkTopoModel'),
        dataIndex: 'modelLabel',
        width: 140,
        ellipsis: true,
        render: (modelLabel: string | undefined) => (
          <EllipsisWithTooltip className="max-w-full" text={modelLabel || ''} />
        ),
      },
    ],
    [t],
  );

  const applySelection = (selectedOnPage: string[]) => {
    const { next, truncated } = mergePageSelection(
      selectedValues,
      listedOptions.map((item) => item.value),
      selectedOnPage,
      limit,
    );
    if (truncated) {
      message.warning(t('dashboard.networkTopoSelectionExceedsLimit'));
    }
    onChange?.(next);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          allowClear
          className="min-w-[180px] flex-1"
          value={instanceKeyword}
          placeholder={t('dashboard.networkTopoSelectDevices')}
          onChange={(event) => onSearch(event.target.value)}
          onPressEnter={(event) => event.preventDefault()}
        />
        <Select
          allowClear
          showSearch
          className="w-[180px]"
          loading={modelsLoading}
          placeholder={t('dashboard.networkTopoModelFilterAll')}
          options={modelOptions}
          optionFilterProp="label"
          value={modelFilter}
          notFoundContent={
            modelsLoading ? undefined : t('dashboard.networkTopoNoSupportedModel')
          }
          onChange={(next) => onModelFilterChange(next || undefined)}
        />
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[var(--color-text-3)]">
          {t('dashboard.networkTopoSelectedCount', '已选 {count} / {limit}', {
            count: selectedValues.length,
            limit,
          })}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="link"
            size="small"
            className="px-1"
            disabled={!listedOptions.length || instancesLoading}
            onClick={() =>
              applySelection(listedOptions.map((item) => item.value))
            }
          >
            {t('dashboard.networkTopoSelectCurrentPage', '全选本页')}
          </Button>
          <Button
            type="link"
            size="small"
            className="px-1"
            disabled={!selectedValues.length}
            onClick={() => onChange?.([])}
          >
            {t('common.clear', '清空')}
          </Button>
        </div>
      </div>
      <div className="overflow-hidden rounded-md border border-[var(--color-border-2)]">
        <Table<NetworkSelectOption>
          size="small"
          rowKey="value"
          columns={columns}
          dataSource={listedOptions}
          loading={instancesLoading}
          scroll={{ y: 280 }}
          pagination={false}
          locale={{
            emptyText: instancesLoading
              ? t('common.loading')
              : t('dashboard.noData'),
          }}
          rowSelection={{
            columnWidth: 48,
            selectedRowKeys: selectedValues,
            preserveSelectedRowKeys: true,
            onChange: (keys) => {
              const pageIds = new Set(listedOptions.map((item) => item.value));
              applySelection(keys.map(String).filter((id) => pageIds.has(id)));
            },
            getCheckboxProps: (record) => ({
              disabled: atLimit && !selectedValues.includes(record.value),
            }),
          }}
        />
        <div className="flex justify-end border-t border-[var(--color-border-2)] px-3 py-2">
          <Pagination
            current={instancePage}
            pageSize={instancePageSize}
            total={instanceTotal}
            size="small"
            showSizeChanger
            disabled={instancesLoading}
            pageSizeOptions={['10', '20', '50']}
            showTotal={(total) =>
              `${t('common.total')} ${total} ${t('common.items')}`
            }
            onChange={onPageChange}
          />
        </div>
      </div>
    </div>
  );
};
