'use client';

import React from 'react';
import { Progress, Tag } from 'antd';
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

// 字段展示列的筛选参数键，与主机 asset.ip 的筛选参数互不影响（后端 FIELD_PARAM_PREFIX）。
export const displayFieldParamKey = (field?: string) => `field:${field ?? ''}`;

const isResourceIpColumn = (col: DisplayCol) =>
  col.type === 'field' && col.role === RESOURCE_IP_ROLE;

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
}

export const buildReportTimeColumn = ({
  t,
  convertToLocalizedTime
}: BuildReportTimeColumnOptions): ColumnItem => ({
  title: t('monitor.views.reportTime'),
  dataIndex: 'time',
  key: 'time',
  onCell: () => ({ style: { minWidth: 160 } }),
  sorter: (a: any, b: any) => a.time - b.time,
  render: (_, { time }) => (
    <>{time ? convertToLocalizedTime(new Date(time * 1000) + '') : '--'}</>
  )
});

interface BuildReportingStatusColumnOptions {
  t: (key: string) => string;
  includeFilters?: boolean;
}

export const buildReportingStatusColumn = ({
  t,
  includeFilters = true
}: BuildReportingStatusColumnOptions): ColumnItem => ({
  title: t('monitor.integrations.reportingStatus'),
  dataIndex: 'status',
  key: 'status',
  onCell: () => ({ style: { minWidth: 100 } }),
  ...(includeFilters
    ? {
      filterMultiple: true,
      filterParam: 'status',
      filters: [
        {
          text: t('monitor.integrations.normal'),
          value: 'normal'
        },
        {
          text: t('monitor.integrations.unavailable'),
          value: 'unavailable'
        }
      ]
    }
    : {}),
  render: (_, record) => {
    if (!record?.status) return <>--</>;
    const isNormal = record.status === 'normal';
    return (
      <Tag color={isNormal ? 'success' : 'default'}>
        {isNormal
          ? t('monitor.integrations.normal')
          : t('monitor.integrations.unavailable')}
      </Tag>
    );
  }
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
}

export const buildDisplayFieldColumns = ({
  displayFields,
  metrics,
  getEnumValueUnit,
  objectId,
  includeDimensionTooltip = true,
  t,
  fieldFilterOptions
}: BuildDisplayFieldColumnsOptions): ColumnItem[] => {
  const displayCols = (displayFields || [])
    .slice()
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

  return displayCols.map((col: DisplayCol, colIndex: number) => {
    const primaryMeta = resolveDisplayMetric(metrics, col.metrics?.[0] || {});
    const colType = getDisplayFieldType(primaryMeta);
    const dataKey = col.column_key || `df_${colIndex}`;

    const baseSorter = (a: any, b: any) => {
      const va = resolveDisplayCell(a, col).value;
      const vb = resolveDisplayCell(b, col).value;
      const na = va == null || va === '';
      const nb = vb == null || vb === '';
      if (na && nb) return 0;
      if (na) return -1;
      if (nb) return 1;
      return Number(va) - Number(vb);
    };

    if (col.type === 'field') {
      const isResourceIp = isResourceIpColumn(col);
      const filterParam = displayFieldParamKey(col.metrics?.[0]?.field);
      const fieldFilters = (fieldFilterOptions?.[filterParam] || []).map(
        (value) => ({ text: value, value })
      );
      return {
        title:
          isResourceIp && t ? t('monitor.views.assetIp') : col.name,
        ...(isResourceIp
          ? {
            role: RESOURCE_IP_ROLE,
            filterMultiple: true,
            filterSearch: true,
            filterParam,
            filters: fieldFilters.length ? fieldFilters : undefined
          }
          : {}),
        dataIndex: dataKey,
        key: dataKey,
        onCell: () => ({ style: { minWidth: 150 } }),
        sorter: (a: any, b: any) => {
          const va = `${resolveDisplayCell(a, col).value ?? ''}`;
          const vb = `${resolveDisplayCell(b, col).value ?? ''}`;
          return va.localeCompare(vb);
        },
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
        sorter: baseSorter,
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
      ...(colType === 'value' ? { sorter: baseSorter } : {}),
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
  includeDimensionTooltip = true
}: BuildInstanceViewColumnsOptions): ColumnItem[] => {
  const displayColumns = buildDisplayFieldColumns({
    displayFields: targetObject?.display_fields || [],
    metrics,
    getEnumValueUnit,
    objectId,
    includeDimensionTooltip,
    t,
    fieldFilterOptions
  });
  // 内置 IP 列紧跟基础列，与基础对象的 asset.ip 摘要列同位置；其余展示列排在上报时间之后。
  const resourceIpColumns = displayColumns.filter(
    (column) => column.role === RESOURCE_IP_ROLE
  );
  const restDisplayColumns = displayColumns.filter(
    (column) => column.role !== RESOURCE_IP_ROLE
  );
  return [
    ...getBaseInstanceColumn({
      objects,
      row: targetObject,
      t,
      queryData,
      ipFilterOptions
    }),
    ...resourceIpColumns,
    buildReportTimeColumn({ t, convertToLocalizedTime }),
    ...restDisplayColumns
  ];
};
