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
import CompactEmptyState from '@/components/compact-empty-state';
import { ConfigGroupTitle } from '../configTitles';
import { ActionInteractionModal } from './actionInteractionModal';
import { ColumnCellStyleModal } from './columnCellStyleModal';

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
  showColumnCellStyle?: boolean;
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
    value: TableColumnConfigItem[keyof TableColumnConfigItem],
  ) => void;
  onDisplayColumnStyleChange: (
    id: string,
    style: Pick<
      TableColumnConfigItem,
      'cellType' | 'valueMappings' | 'cellThresholdColors'
    >,
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
  showColumnCellStyle = false,
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
  onDisplayColumnStyleChange,
  onDisplayColumnKeyBlur,
  onDisplayColumnDragEnd,
  onReProbeColumns,
  onAddNewFilterField,
  onAddNewDisplayColumn,
  onActionsChange,
}) => {
  const [interactionColumn, setInteractionColumn] =
    useState<DisplayColumnRow | null>(null);
  const [styleColumnId, setStyleColumnId] = useState<string | null>(null);

  const styleColumn =
    displayColumns.find(
      (column) =>
        column.id === styleColumnId && column.columnType !== 'actions',
    ) || null;

  const hasColumnCellStyle = (column: DisplayColumnRow) =>
    column.cellType === 'colorBackground' ||
    (column.valueMappings?.length ?? 0) > 0 ||
    (column.cellThresholdColors?.length ?? 0) > 0;

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
          className="w-full"
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
          className="w-full"
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
        <div className="flex justify-start gap-1">
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddFilterField(index)}
            className="border-none p-1"
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => onDeleteFilterField(record.id)}
            className="border-none p-1"
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
            className="w-full"
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
        <div className="flex justify-start gap-1">
          <Button
            type="text"
            size="small"
            icon={<PlusCircleOutlined />}
            onClick={() => onAddDisplayColumn(index)}
            className="border-none p-1"
          />
          <Button
            type="text"
            size="small"
            icon={<MinusCircleOutlined />}
            onClick={() => {
              if (styleColumnId === record.id) {
                setStyleColumnId(null);
              }
              onDeleteDisplayColumn(record.id);
            }}
            className="border-none p-1"
          />
          {record.columnType === 'actions' && (
            <Tooltip title={t('dashboard.interactionConfig')}>
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined aria-hidden />}
                aria-label={t('dashboard.interactionConfig')}
                onClick={() => setInteractionColumn(record)}
                className="border-none p-1"
              />
            </Tooltip>
          )}
          {showColumnCellStyle && record.columnType !== 'actions' && (
            <Tooltip title={t('dashboard.columnCellStyleConfig')}>
              <Button
                type="text"
                size="small"
                icon={<SettingOutlined aria-hidden />}
                aria-label={t('dashboard.columnCellStyleConfig')}
                onClick={() => setStyleColumnId(record.id)}
                className={`border-none p-1 ${
                  hasColumnCellStyle(record)
                    ? 'text-[var(--color-primary)]'
                    : 'text-[var(--color-text-2)]'
                }`}
              />
            </Tooltip>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <div>
        <ConfigGroupTitle
          extra={
            invalidConfiguredFieldKeys.length > 0 ? (
              <Tooltip
                title={(
                  t('dashboard.invalidConfiguredFieldsTip') ||
                  '部分已配置字段不在当前可用字段集合中，可能不可用：{{fields}}'
                ).replace('{{fields}}', invalidConfiguredFieldKeys.join('、'))}
              >
                <ExclamationCircleOutlined className="text-[14px] text-[var(--color-warning)]" />
              </Tooltip>
            ) : null
          }
          actions={
            <div className="flex gap-2">
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
          }
        >
          {t('dashboard.displayColumns')}
        </ConfigGroupTitle>
        {displayColumns.length > 0 ? (
          <div className="pt-1">
            <CustomTable
              rowKey="id"
              columns={displayColumnTableColumns}
              dataSource={displayColumns}
              pagination={false}
              scroll={
                displayColumns.length > 8 ? { y: 320 } : undefined
              }
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
          <div className="mt-2 text-xs text-[var(--color-fail)]">
            {displayColumnsError}
          </div>
        )}
      </div>

      {showFilterFields && (
        <div>
          <ConfigGroupTitle
            actions={
              <Button
                type="dashed"
                size="small"
                icon={<PlusCircleOutlined />}
                onClick={onAddNewFilterField}
                disabled={filterFieldOptions.length === 0}
              >
                {t('common.add')}
              </Button>
            }
          >
            {t('dashboard.filterFields')}
          </ConfigGroupTitle>
          {filterFieldOptions.length === 0 ? (
            <CompactEmptyState description={t('dashboard.noSchemaFields')} />
          ) : filterFields.length > 0 ? (
            <CustomTable
              rowKey="id"
              columns={filterFieldColumns}
              dataSource={filterFields}
              pagination={false}
              scroll={filterFields.length > 8 ? { y: 320 } : undefined}
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
      <ColumnCellStyleModal
        open={!!styleColumn}
        column={styleColumn}
        t={t}
        onCancel={() => setStyleColumnId(null)}
        onConfirm={(nextStyle) => {
          if (!styleColumn) return;
          onDisplayColumnStyleChange(styleColumn.id, nextStyle);
          setStyleColumnId(null);
        }}
      />
    </div>
  );
};
