'use client';

import React from 'react';
import { Progress } from 'antd';
import {
  ColumnItem,
  MetricItem,
  ObjectItem,
  TableDataItem
} from '@/app/monitor/types';
import { ListItem } from '@/types';
import {
  getBaseInstanceColumn,
  getEnumColor,
  isStringArray
} from '@/app/monitor/utils/common';
import { getDisplayFieldType } from '@/app/monitor/utils/displayFieldType';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import MetricDimensionTooltip from './metricDimensionTooltip';
import { resolveDisplayMetric } from './displayFieldMetric';

export type DisplayCol = NonNullable<ObjectItem['display_fields']>[number];

const DISPLAY_FIELD_KEY_SEP = '::';
const FIELD_DISPLAY_KEY_PREFIX = 'field';

export const INSTANCE_VIEW_ACTION_KEY = 'action';

// 云平台子对象的 IP 由采集 label 提供，走展示字段列；标记为该 role 后按内置 IP 列渲染，
// 与基础对象的 asset.ip 摘要列保持同一列头与位置。
export const RESOURCE_IP_ROLE = 'resource_ip';
export const NAMESPACE_ROLE = 'namespace';

// 字段展示列的筛选参数键，与主机 asset.ip 的筛选参数互不影响（后端 FIELD_PARAM_PREFIX）。
export const displayFieldParamKey = (field?: string) => `field:${field ?? ''}`;

const isResourceIpColumn = (col: DisplayCol) =>
  col.type === 'field' && col.role === RESOURCE_IP_ROLE;

const isNamespaceColumn = (col: DisplayCol) =>
  col.type === 'field' && col.role === NAMESPACE_ROLE;

const isRoleFieldColumn = (col: DisplayCol) =>
  col.type === 'field' && Boolean(col.role);

const fieldColumnTitle = (col: DisplayCol, t?: (key: string) => string) => {
  if (isResourceIpColumn(col) && t) return t('monitor.views.assetIp');
  if (isNamespaceColumn(col) && t) return t('monitor.views.namespace');
  return col.name;
};

export const displayFieldKey = (
  plugin?: string,
  metric?: string,
  field?: string
): string => {
  if (field) {
    return `${FIELD_DISPLAY_KEY_PREFIX}${DISPLAY_FIELD_KEY_SEP}${plugin}${DISPLAY_FIELD_KEY_SEP}${metric}${DISPLAY_FIELD_KEY_SEP}${field}`;
  }
  return plugin ? `${plugin}${DISPLAY_FIELD_KEY_SEP}${metric}` : (metric ?? '');
};

export const resolveDisplayCell = (record: TableDataItem, col: DisplayCol) => {
  for (const binding of col.metrics || []) {
    const key = displayFieldKey(
      binding.plugin,
      binding.metric,
      col.type === 'field' ? binding.field : undefined
    );
    const cell = record[key] as
      | { value?: string | number; unit?: string }
      | string
      | number
      | undefined;
    if (col.type === 'field') {
      if (cell != null && cell !== '') {
        return {
          value: cell as string | number,
          unit: undefined,
          metricName: binding.metric,
          pluginName: binding.plugin
        };
      }
      continue;
    }
    const metricCell =
      cell && typeof cell === 'object'
        ? (cell as { value?: string | number; unit?: string })
        : undefined;
    const v = metricCell?.value;
    if (v != null && v !== '') {
      return {
        value: v,
        unit: metricCell?.unit,
        metricName: binding.metric,
        pluginName: binding.plugin
      };
    }
  }
  const primary = col.metrics?.[0]?.metric;
  return {
    value: undefined as string | number | undefined,
    unit: undefined as string | undefined,
    metricName: primary,
    pluginName: col.metrics?.[0]?.plugin
  };
};

const getPercent = (value: number) => {
  return +(+value).toFixed(2);
};

interface BuildReportTimeColumnOptions {
  t: (key: string) => string;
  convertToLocalizedTime: (value: string) => string;
  /** 服务端排序受控态：当前排序列的 Ant Design sortOrder */
  sortOrder?: 'ascend' | 'descend' | null;
}

export const buildReportTimeColumn = ({
  t,
  convertToLocalizedTime,
  sortOrder = null
}: BuildReportTimeColumnOptions): ColumnItem => ({
  title: t('monitor.views.reportTime'),
  dataIndex: 'time',
  key: 'time',
  onCell: () => ({ style: { minWidth: 160 } }),
  sorter: true,
  sortOrder,
  render: (_, { time }) => (
    <>{time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}</>
  )
});

interface BuildDisplayFieldColumnsOptions {
  displayFields: DisplayCol[];
  metrics: MetricItem[];
  getEnumValueUnit: (
    metricItem: any,
    value: string | number | undefined,
    unit: string
  ) => string;
  objectId?: React.Key;
  includeDimensionTooltip?: boolean;
  t?: (key: string) => string;
  fieldFilterOptions?: Record<string, string[]>;
  /** 当前服务端排序列 key 与方向（Ant Design） */
  activeSort?: { key: string; order: 'ascend' | 'descend' } | null;
}

export const buildDisplayFieldColumns = ({
  displayFields,
  metrics,
  getEnumValueUnit,
  objectId,
  includeDimensionTooltip = true,
  t,
  fieldFilterOptions,
  activeSort = null
}: BuildDisplayFieldColumnsOptions): ColumnItem[] => {
  const displayCols = (displayFields || [])
    .slice()
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

  return displayCols.map((col: DisplayCol, colIndex: number) => {
    const primaryMeta = resolveDisplayMetric(metrics, col.metrics?.[0] || {});
    const colType = getDisplayFieldType(primaryMeta);
    const dataKey = col.column_key || `df_${colIndex}`;
    const columnSortOrder =
      activeSort?.key === dataKey ? activeSort.order : null;

    if (col.type === 'field') {
      const filterParam = displayFieldParamKey(col.metrics?.[0]?.field);
      const fieldFilters = (fieldFilterOptions?.[filterParam] || []).map(
        (value) => ({ text: value, value })
      );
      return {
        title: fieldColumnTitle(col, t),
        ...(isRoleFieldColumn(col)
          ? {
            role: col.role,
            filterMultiple: true,
            filterSearch: true,
            filterParam,
            filters: fieldFilters.length ? fieldFilters : undefined
          }
          : {}),
        dataIndex: dataKey,
        key: dataKey,
        onCell: () => ({ style: { minWidth: 150 } }),
        // MVP：field 列不做全局排序，避免误导性本页排序。
        render: (_: unknown, record: TableDataItem) => {
          const value = resolveDisplayCell(record, col).value;
          return (
            <EllipsisWithTooltip
              text={value == null || value === '' ? '--' : String(value)}
              className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            />
          );
        }
      };
    }

    if (colType === 'progress') {
      return {
        title: col.name,
        dataIndex: dataKey,
        key: dataKey,
        type: 'progress',
        sorter: true,
        sortOrder: columnSortOrder,
        render: (_: unknown, record: TableDataItem) => {
          const cell = resolveDisplayCell(record, col);
          const meta =
            resolveDisplayMetric(metrics, {
              plugin: cell.pluginName,
              metric: cell.metricName
            }) || primaryMeta;
          const hasDimensions = (meta?.dimensions?.length ?? 0) > 1;
          const size: [number, number] = hasDimensions ? [220, 20] : [240, 20];
          const metricUnit = cell.unit || meta?.unit || '';
          return (
            <div className="flex items-center justify-between">
              <Progress
                className="flex"
                strokeLinecap="butt"
                strokeColor="var(--color-primary)"
                showInfo={!!cell.value}
                format={(percent) => (
                  <span style={{ color: 'var(--color-text-1)' }}>
                    {percent?.toFixed(2)}%
                  </span>
                )}
                percent={getPercent(Number(cell.value) || 0)}
                percentPosition={{ align: 'start', type: 'outer' }}
                size={size}
              />
              {includeDimensionTooltip && hasDimensions && objectId != null && (
                <MetricDimensionTooltip
                  instanceId={record.instance_id}
                  monitorObjectId={objectId}
                  metricInfo={{ metricItem: meta, metricUnit }}
                />
              )}
            </div>
          );
        }
      };
    }

    return {
      title: col.name,
      dataIndex: dataKey,
      key: dataKey,
      onCell: () => ({ style: { minWidth: 150 } }),
      ...(colType === 'value'
        ? { sorter: true, sortOrder: columnSortOrder }
        : {}),
      ...(colType === 'enum' &&
      primaryMeta?.name &&
      isStringArray(primaryMeta?.unit || '')
        ? {
          filterMultiple: true,
          filterParam: primaryMeta.name,
          filters: (JSON.parse(primaryMeta.unit || '[]') as ListItem[]).map(
            (item) => ({
              text: String(item.name ?? item.id ?? ''),
              value: String(item.id ?? '')
            })
          )
        }
        : {}),
      render: (_: unknown, record: TableDataItem) => {
        const cell = resolveDisplayCell(record, col);
        const meta =
          resolveDisplayMetric(metrics, {
            plugin: cell.pluginName,
            metric: cell.metricName
          }) || primaryMeta;
        const color = getEnumColor(meta, cell.value);
        const hasDimensions = (meta?.dimensions?.length ?? 0) > 1;
        const metricUnit = cell.unit || meta?.unit || '';
        const metricItem: any = {
          unit: metricUnit,
          name: meta?.name,
          dimensions: meta?.dimensions || []
        };
        return (
          <div className="flex items-center justify-between">
            <span style={{ color }}>
              <EllipsisWithTooltip
                text={getEnumValueUnit(metricItem, cell.value, metricUnit)}
                className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
              />
            </span>
            {includeDimensionTooltip && hasDimensions && objectId != null && (
              <MetricDimensionTooltip
                instanceId={record.instance_id}
                monitorObjectId={objectId}
                metricInfo={{ metricItem: meta, metricUnit }}
              />
            )}
          </div>
        );
      }
    };
  });
};

interface BuildInstanceViewColumnsOptions {
  objects: ObjectItem[];
  targetObject?: ObjectItem;
  t: (key: string) => string;
  convertToLocalizedTime: (value: string) => string;
  metrics: MetricItem[];
  getEnumValueUnit: (
    metricItem: any,
    value: string | number | undefined,
    unit: string
  ) => string;
  objectId?: React.Key;
  queryData?: any[];
  ipFilterOptions?: string[];
  fieldFilterOptions?: Record<string, string[]>;
  includeDimensionTooltip?: boolean;
  activeSort?: { key: string; order: 'ascend' | 'descend' } | null;
}

export const buildInstanceViewColumns = ({
  objects,
  targetObject,
  t,
  convertToLocalizedTime,
  metrics,
  getEnumValueUnit,
  objectId,
  queryData,
  ipFilterOptions,
  fieldFilterOptions,
  includeDimensionTooltip = true,
  activeSort = null
}: BuildInstanceViewColumnsOptions): ColumnItem[] => {
  const displayColumns = buildDisplayFieldColumns({
    displayFields: targetObject?.display_fields || [],
    metrics,
    getEnumValueUnit,
    objectId,
    includeDimensionTooltip,
    t,
    fieldFilterOptions,
    activeSort
  });
  // 命名空间紧跟集群列；内置 IP 列再跟其后，与基础对象的 asset.ip 摘要列同位置；
  // 其余展示列排在上报时间之后。
  const namespaceColumns = displayColumns.filter(
    (column) => column.role === NAMESPACE_ROLE
  );
  const resourceIpColumns = displayColumns.filter(
    (column) => column.role === RESOURCE_IP_ROLE
  );
  const restDisplayColumns = displayColumns.filter(
    (column) =>
      column.role !== RESOURCE_IP_ROLE && column.role !== NAMESPACE_ROLE
  );
  return [
    ...getBaseInstanceColumn({
      objects,
      row: targetObject,
      t,
      queryData,
      ipFilterOptions
    }),
    ...namespaceColumns,
    ...resourceIpColumns,
    buildReportTimeColumn({
      t,
      convertToLocalizedTime,
      sortOrder: activeSort?.key === 'time' ? activeSort.order : null
    }),
    ...restDisplayColumns
  ];
};
