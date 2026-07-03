import React, { useState } from 'react';
import {
  AutoComplete,
  Button,
  Dropdown,
  Input,
  Select,
  Switch,
  Tag,
  Tooltip,
} from 'antd';
import {
  PlusCircleOutlined,
  MinusCircleOutlined,
  ExclamationCircleOutlined,
  SettingOutlined,
  DownOutlined,
} from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import type {
  DashboardActionConfig,
  TableFilterFieldConfig,
  TableColumnConfigItem,
} from '@/app/ops-analysis/types/dashBoard';
import type { DisplayColumnRow } from '../utils/columnProbing';
import CompactEmptyState from '@/app/ops-analysis/components/compactEmptyState';
import { ActionInteractionModal } from './actionInteractionModal';

type FilterFieldRow = TableFilterFieldConfig & { id: string };

interface FilterFieldOption {
  label: string;
  value: string;
}

interface TableSettingsSectionProps {
  t: (key: string) => string;
  displayColumns: DisplayColumnRow[];
  displayColumnOptions: FilterFieldOption[];
  actions: DashboardActionConfig[];
  filterFields: FilterFieldRow[];
  filterFieldOptions: FilterFieldOption[];
  showFilterFields: boolean;
  invalidConfiguredFieldKeys: string[];
  isProbingColumns: boolean;
  paramsChangedAfterProbe: boolean;
  displayColumnsError: string;
  onAddFilterField: (index: number) => void;
  onDeleteFilterField: (id: string) => void;
  onFilterFieldChange: (
    id: string,
    fieldName: keyof TableFilterFieldConfig,
    value: string,
    options: FilterFieldOption[],
  ) => void;
  onAddDisplayColumn: (index: number) => void;
  onDeleteDisplayColumn: (id: string) => void;
  onDisplayColumnChange: (
    id: string,
    fieldName: keyof TableColumnConfigItem,
    value: string | boolean,
  ) => void;
  onDisplayColumnKeyBlur: (id: string) => void;
  onDisplayColumnDragEnd: (targetTableData: DisplayColumnRow[]) => void;
  onReProbeColumns: () => void;
  onAddNewFilterField: () => void;
  onAddNewDisplayColumn: (columnType?: 'data' | 'actions') => void;
  onActionsChange: (actions: DashboardActionConfig[]) => void;
}

export const TableSettingsSection: React.FC<TableSettingsSectionProps> = ({
  t,
  displayColumns,
  displayColumnOptions,
  actions,
  filterFields,
  filterFieldOptions,
  showFilterFields,
  invalidConfiguredFieldKeys,
  isProbingColumns,
  paramsChangedAfterProbe,
  displayColumnsError,
  onAddFilterField,
  onDeleteFilterField,
  onFilterFieldChange,
  onAddDisplayColumn,
  onDeleteDisplayColumn,
  onDisplayColumnChange,
  onDisplayColumnKeyBlur,
  onDisplayColumnDragEnd,
  onReProbeColumns,
  onAddNewFilterField,
  onAddNewDisplayColumn,
  onActionsChange,
}) => {
  const [interactionColumn, setInteractionColumn] =
    useState<DisplayColumnRow | null>(null);

  const localizedFilterInputTypeOptions = [
    { label: t('dashboard.keyword'), value: 'keyword' },
    { label: t('dashboard.timeRange'), value: 'time_range' },
  ];

  const filterFieldColumns = [
    {
      title: t('dashboard.filterFieldKey'),
      dataIndex: 'key',
      key: 'key',
      width: 160,
      render: (_: unknown, record: FilterFieldRow) => (
        <Select
          value={record.key || undefined}
          placeholder={t('common.selectTip')}
          style={{ width: '100%' }}
          onChange={(val) =>
            onFilterFieldChange(record.id, 'key', val, filterFieldOptions)
          }
          options={filterFieldOptions}
          showSearch
          optionFilterProp="label"
        />
      ),
    },
    {
      title: t('dashboard.filterFieldLabel'),
      dataIndex: 'label',
      key: 'label',
      width: 140,
      render: (_: unknown, record: FilterFieldRow) => (
        <Input
          value={record.label}
          placeholder={t('dashboard.filterFieldLabel')}
          onChange={(e) =>
            onFilterFieldChange(
              record.id,
              'label',
              e.target.value,
              filterFieldOptions,
            )
          }
        />
      ),
    },
    {
      title: t('dashboard.filterInputType'),
      dataIndex: 'inputType',
      key: 'inputType',
      width: 120,
      render: (_: unknown, record: FilterFieldRow) => (
        <Select
          value={record.inputType}
          options={localizedFilterInputTypeOptions}
          style={{ width: '100%' }}
          onChange={(val) =>
            onFilterFieldChange(record.id, 'inputType', val, filterFieldOptions)
          }
        />
      ),
    },
    {
      title: t('dataSource.operation'),
      key: 'action',
      width: 80,
      render: (_: unknown, record: FilterFieldRow, index: number) => (
        <div
          style={{ display: 'flex', gap: '4px', justifyContent: 'flex-start' }}
        >
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddFilterField(index)}
            style={{ border: 'none', padding: '4px' }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => onDeleteFilterField(record.id)}
            style={{ border: 'none', padding: '4px' }}
          />
        </div>
      ),
    },
  ];

  const displayColumnTableColumns = [
    {
      title: t('dashboard.filterFieldKey'),
      dataIndex: 'key',
      key: 'key',
      width: 180,
      render: (_: unknown, record: DisplayColumnRow) =>
        record.columnType === 'actions' ? (
          <Tag className="m-0">{t('dashboard.operationColumn')}</Tag>
        ) : (
          <AutoComplete
            value={record.key}
            placeholder={t('dashboard.selectOrInputField')}
            style={{ width: '100%' }}
            options={displayColumnOptions}
            filterOption={(inputValue, option) => {
              const query = inputValue.toLowerCase();
              return (
                (option?.label || '').toString().toLowerCase().includes(query) ||
                (option?.value || '').toString().toLowerCase().includes(query)
              );
            }}
            onChange={(value) => onDisplayColumnChange(record.id, 'key', value)}
            onBlur={() => onDisplayColumnKeyBlur(record.id)}
          />
        ),
    },
    {
      title: t('dashboard.filterFieldLabel'),
      dataIndex: 'title',
      key: 'title',
      width: 180,
      render: (_: unknown, record: DisplayColumnRow) => (
        <Input
          value={record.title}
          placeholder={t('dashboard.filterFieldLabel')}
          onChange={(e) =>
            onDisplayColumnChange(record.id, 'title', e.target.value)
          }
        />
      ),
    },
    {
      title: t('dashboard.columnVisible') || 'Visible',
      dataIndex: 'visible',
      key: 'visible',
      width: 90,
      render: (_: unknown, record: DisplayColumnRow) => (
        <Switch
          size="small"
          checked={record.visible}
          onChange={(e) => onDisplayColumnChange(record.id, 'visible', e)}
        />
      ),
    },
    {
      title: t('dataSource.operation'),
      key: 'action',
      width: 132,
      render: (_: unknown, record: DisplayColumnRow, index: number) => (
        <div
          style={{ display: 'flex', gap: '4px', justifyContent: 'flex-start' }}
        >
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddDisplayColumn(index)}
            style={{ border: 'none', padding: '4px' }}
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => onDeleteDisplayColumn(record.id)}
            style={{ border: 'none', padding: '4px' }}
          />
          {record.columnType === 'actions' && (
            <Tooltip title={t('dashboard.interactionConfig')}>
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined />}
                onClick={() => setInteractionColumn(record)}
                style={{ border: 'none', padding: '4px' }}
              />
            </Tooltip>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="mb-6">
      <div
        className="font-bold text-(--color-text-1) mb-4"
        style={{ display: 'flex', alignItems: 'center', gap: 8 }}
      >
        <span>{t('dashboard.tableSettings')}</span>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <div
          style={{
            marginBottom: '8px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span
            style={{
              fontWeight: 500,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>{t('dashboard.displayColumns')}</span>
            {invalidConfiguredFieldKeys.length > 0 && (
              <Tooltip
                title={(
                  t('dashboard.invalidConfiguredFieldsTip') ||
                  '部分已配置字段不在当前可用字段集合中，可能不可用：{{fields}}'
                ).replace('{{fields}}', invalidConfiguredFieldKeys.join('、'))}
              >
                <ExclamationCircleOutlined
                  style={{ color: '#faad14', fontSize: 14 }}
                />
              </Tooltip>
            )}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <Tooltip
              title={
                t('dashboard.reProbeColumnsTip') ||
                '将基于当前数据源和参数重新探测并恢复默认列，同时保留已有自定义列'
              }
            >
              <Button
                size="small"
                onClick={onReProbeColumns}
                loading={isProbingColumns}
                type={paramsChangedAfterProbe ? 'primary' : 'default'}
              >
                {t('dashboard.reProbeColumns') || '重新探测列'}
              </Button>
            </Tooltip>
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  {
                    key: 'data',
                    label: t('dashboard.addDataColumn'),
                  },
                  {
                    key: 'actions',
                    label: t('dashboard.addOperationColumn'),
                  },
                ],
                onClick: ({ key }) =>
                  onAddNewDisplayColumn(
                    key === 'actions' ? 'actions' : 'data',
                  ),
              }}
            >
              <Button type="dashed" size="small" icon={<PlusCircleOutlined />}>
                {t('common.add')}
                <DownOutlined />
              </Button>
            </Dropdown>
          </div>
        </div>
        {displayColumns.length > 0 ? (
          <div className="pt-1">
            <CustomTable
              rowKey="id"
              columns={displayColumnTableColumns}
              dataSource={displayColumns}
              pagination={false}
              scroll={{ y: 320 }}
              size="small"
              rowDraggable
              onRowDragEnd={(targetTableData) =>
                onDisplayColumnDragEnd(
                  (targetTableData || []) as DisplayColumnRow[],
                )
              }
            />
          </div>
        ) : (
          <CompactEmptyState
            description={
              t('dashboard.noDisplayColumns') || t('dashboard.displayColumns')
            }
          />
        )}
        {displayColumnsError && (
          <div
            style={{
              color: 'var(--ant-color-error)',
              fontSize: 12,
              marginTop: 8,
            }}
          >
            {displayColumnsError}
          </div>
        )}
      </div>

      {showFilterFields && (
        <div>
          <div
            style={{
              marginBottom: '8px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span style={{ fontWeight: 500 }}>
              {t('dashboard.filterFields')}
            </span>
            <Button
              type="dashed"
              size="small"
              icon={<PlusCircleOutlined />}
              onClick={onAddNewFilterField}
              disabled={filterFieldOptions.length === 0}
            >
              {t('common.add')}
            </Button>
          </div>
          {filterFieldOptions.length === 0 ? (
            <CompactEmptyState description={t('dashboard.noSchemaFields')} />
          ) : filterFields.length > 0 ? (
            <CustomTable
              rowKey="id"
              columns={filterFieldColumns}
              dataSource={filterFields}
              pagination={false}
              scroll={{ y: 320 }}
            />
          ) : (
            <CompactEmptyState description={t('dashboard.noFilterFields')} />
          )}
        </div>
      )}
      <ActionInteractionModal
        open={!!interactionColumn}
        column={interactionColumn}
        actions={actions}
        fieldOptions={displayColumnOptions}
        t={t}
        onCancel={() => setInteractionColumn(null)}
        onConfirm={(nextActions) => {
          onActionsChange(nextActions);
          setInteractionColumn(null);
        }}
      />
    </div>
  );
};
