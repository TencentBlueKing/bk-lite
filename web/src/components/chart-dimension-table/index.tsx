import React, { useMemo } from 'react';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { ColumnItem, ListItem } from '@/types';

interface ChartDimensionMetricColumn {
  key: string;
  title: string;
  width?: number;
  renderText?: (value: unknown, row: Record<string, any>) => string;
}

type DetailMode = 'identifier' | 'columns';

export interface ChartDimensionTableProps {
  data: Array<Record<string, any>>;
  colors: string[];
  details: Record<string, ListItem[]>;
  calculateMetrics: (data: Array<Record<string, any>>, key: string) => Record<string, any>;
  metricColumns: ChartDimensionMetricColumn[];
  detailMode?: DetailMode;
  detailColumnTitle?: string;
  scroll?: { x?: number | string; y?: number | string };
}

const getChartAreaKeys = (arr: Array<Record<string, any>>) => {
  const keys = new Set<string>();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const defaultDetailSummary = (detailItems: ListItem[]) =>
  detailItems
    .map((detail) => (detail.label ? `${detail.label}: ${detail.value}` : detail.value))
    .filter(Boolean)
    .join('-');

const ChartDimensionTable: React.FC<ChartDimensionTableProps> = ({
  data,
  colors,
  details,
  calculateMetrics,
  metricColumns,
  detailMode = 'identifier',
  detailColumnTitle = 'Identifier',
  scroll,
}) => {
  const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

  const tableData = useMemo(
    () =>
      chartAreaKeys.map((item, index) => {
        const detailItems = details[item] || [];
        const detailItemMap = detailItems.reduce((pre: Record<string, any>, cur: ListItem) => {
          if (cur.name) {
            pre[cur.name] = cur.value;
          }
          return pre;
        }, {});

        return {
          id: item,
          color: colors[index],
          identifier: defaultDetailSummary(detailItems),
          ...calculateMetrics(data, item),
          ...detailItemMap,
        };
      }),
    [calculateMetrics, chartAreaKeys, colors, data, details]
  );

  const sampleDetailItems = useMemo(() => {
    const firstKeyWithDetails = chartAreaKeys.find((key) => (details[key] || []).length > 0);
    return firstKeyWithDetails ? details[firstKeyWithDetails] || [] : [];
  }, [chartAreaKeys, details]);

  const columns = useMemo<ColumnItem[]>(() => {
    const colorColumn: ColumnItem = {
      title: '',
      dataIndex: 'color',
      key: 'color',
      width: 30,
      fixed: 'left',
      render: (_: unknown, row: Record<string, any>) => (
        <div
          className="h-[4px] w-[10px]"
          style={{
            background: row.color,
          }}
        ></div>
      ),
    };

    const detailColumns =
      detailMode === 'columns'
        ? sampleDetailItems.map((item: ListItem) => ({
          title: String(item.label || item.name || '--'),
          dataIndex: String(item.name || item.label || 'detail'),
          key: String(item.name || item.label || 'detail'),
          width: 100,
          ellipsis: true,
          fixed: 'left',
        }))
        : [
          {
            title: detailColumnTitle,
            dataIndex: 'identifier',
            key: 'identifier',
            width: 90,
            fixed: 'left',
          },
        ];

    const valueColumns = metricColumns.map<ColumnItem>((column) => ({
      title: column.title,
      dataIndex: column.key,
      key: column.key,
      width: column.width || 70,
      render: (_: unknown, row: Record<string, any>) => {
        const text = column.renderText
          ? column.renderText(row[column.key], row)
          : `${row[column.key] ?? '--'}`;
        return (
          <EllipsisWithTooltip
            className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
            text={text}
          />
        );
      },
    }));

    return [colorColumn, ...detailColumns, ...valueColumns];
  }, [detailColumnTitle, detailMode, metricColumns, sampleDetailItems]);

  return (
    <div className="ml-[10px] h-full w-[360px]">
      <CustomTable
        className="w-full"
        rowKey="id"
        size="small"
        scroll={scroll}
        dataSource={tableData}
        columns={columns}
      />
    </div>
  );
};

export default ChartDimensionTable;
