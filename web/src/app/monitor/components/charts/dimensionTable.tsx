import React, { useEffect, useState, memo, useMemo, useCallback } from 'react';
import chartStyle from './index.module.scss';
import CustomTable from '@/components/custom-table';
import { calculateMetrics } from '@/app/monitor/utils/common';
import { ListItem } from '@/types';
import { ColumnItem, TableDataItem } from '@/app/monitor/types';

interface DimensionTableProps {
  data: any[];
  colors: string[];
  details: any;
}

const getChartAreaKeys = (arr: any[]) => {
  const keys = new Set();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const DimensionTable: React.FC<DimensionTableProps> = memo(
  ({ data, colors, details }) => {
    const [tableData, setTableData] = useState<TableDataItem[]>([]);
    const [columns, setColumns] = useState<ColumnItem[]>([]);

    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const getTableData = useCallback(() => {
      const _data = chartAreaKeys.map((item, index) => {
        const detailItem = details[item as string].reduce(
          (pre: ListItem, cur: ListItem) => {
            const obj: Record<string, any> = {};
            obj[cur.name || ''] = cur.value;
            return Object.assign(pre, obj);
          },
          {}
        );
        return {
          id: item,
          color: colors[index],
          ...calculateMetrics(data, item as string),
          ...detailItem,
        };
      });
      return _data;
    }, [chartAreaKeys, colors, data, details]);

    const tableColumns = useMemo(() => {
      const _columns: ColumnItem[] = [
        {
          title: 'Min',
          dataIndex: 'minValue',
          key: 'minValue',
          width: 70,
          ellipsis: true,
          render: (_, { minValue }) => <>{(minValue || 0).toFixed(2)}</>,
        },
        {
          title: 'Max',
          dataIndex: 'maxValue',
          key: 'maxValue',
          width: 70,
          ellipsis: true,
          render: (_, { maxValue }) => <>{(maxValue || 0).toFixed(2)}</>,
        },
        {
          title: 'Last',
          dataIndex: 'latestValue',
          key: 'latestValue',
          width: 70,
          ellipsis: true,
          render: (_, { latestValue }) => <>{(latestValue || 0).toFixed(2)}</>,
        },
      ];

      if (!details?.value1) return _columns;

      const detailColumns = details.value1.map((item: ListItem) => ({
        title: item.label,
        dataIndex: item.name,
        key: item.name,
        width: 100,
        ellipsis: true,
        fixed: 'left',
      }));

      return [
        {
          title: '',
          dataIndex: 'color',
          key: 'color',
          width: 30,
          fixed: 'left',
          render: (_: any, row: TableDataItem) => (
            <div
              className="w-[10px] h-[4px]"
              style={{
                background: row.color,
              }}
            ></div>
          ),
        },
        ...detailColumns,
        ..._columns,
      ];
    }, [details]);

    useEffect(() => {
      if (data?.length && colors?.length && details?.value1) {
        try {
          const _tableData = getTableData();
          setTableData(_tableData);
          setColumns(tableColumns);
        } catch {
          setTableData([]);
          setColumns([]);
        }
      }
    }, [data, colors, details, getTableData, tableColumns]);

    return (
      <div className={chartStyle.tableArea}>
        <CustomTable
          className="w-full"
          rowKey="id"
          size="small"
          scroll={{ x: 340, y: 'calc(100vh - 450px)' }}
          dataSource={tableData}
          columns={columns}
        />
      </div>
    );
  }
);

DimensionTable.displayName = 'DimensionTable';

export default DimensionTable;
