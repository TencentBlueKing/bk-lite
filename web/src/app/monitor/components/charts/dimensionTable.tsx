import React, { useEffect, useState, memo, useMemo, useRef } from 'react';
import chartStyle from './index.module.scss';
import CustomTable from '@/components/custom-table';
import { calculateMetrics } from '@/app/monitor/utils/common';
import { ListItem } from '@/types';
import { ColumnItem, TableDataItem } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import { useUnitTransform } from '@/app/monitor/hooks/useUnitTransform';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface DimensionTableProps {
  data: any[];
  colors: string[];
  details: any;
  unit?: string;
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
  ({ data, colors, details, unit = '' }) => {
    const { t } = useTranslation();
    const { findUnitNameById } = useUnitTransform();
    const [tableData, setTableData] = useState<TableDataItem[]>([]);
    const [columns, setColumns] = useState<ColumnItem[]>([]);

    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const unitName = useMemo(() => findUnitNameById(unit), [unit]);

    const unitNameRef = useRef(unitName);
    unitNameRef.current = unitName;

    const formatValueWithUnit = (value: number | undefined | null) => {
      const formattedValue = (value ?? 0).toFixed(2);
      return unitNameRef.current
        ? `${formattedValue} ${unitNameRef.current}`
        : formattedValue;
    };

    const getTableData = () => {
      const _data = chartAreaKeys.map((item, index) => {
        const detailItem = details[item as string].reduce(
          (pre: ListItem, cur: ListItem) => {
            const obj: Record<string, any> = {};
            obj[cur.name || ''] = cur.value;
            return Object.assign(pre, obj);
          },
          {}
        );
        const identifierParts = (details[item as string] || [])
          .map((detail: ListItem) =>
            detail.label ? `${detail.label}: ${detail.value}` : detail.value
          )
          .filter(Boolean);
        const identifier = identifierParts.join('-');
        return {
          id: item,
          color: colors[index],
          identifier,
          ...calculateMetrics(data, item as string),
          ...detailItem
        };
      });
      return _data;
    };

    const tableColumns = useMemo(() => {
      const _columns: ColumnItem[] = [
        {
          title: t('monitor.search.min'),
          dataIndex: 'minValue',
          key: 'minValue',
          width: 70,
          render: (_, { minValue }) => (
            <EllipsisWithTooltip
              className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
              text={formatValueWithUnit(minValue)}
            />
          )
        },
        {
          title: t('monitor.search.max'),
          dataIndex: 'maxValue',
          key: 'maxValue',
          width: 70,
          render: (_, { maxValue }) => (
            <EllipsisWithTooltip
              className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
              text={formatValueWithUnit(maxValue)}
            />
          )
        },
        {
          title: t('monitor.search.avg'),
          dataIndex: 'avgValue',
          key: 'avgValue',
          width: 70,
          render: (_, { avgValue }) => (
            <EllipsisWithTooltip
              className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
              text={formatValueWithUnit(avgValue)}
            />
          )
        }
      ];
      if (!details?.value1) return _columns;
      const identifierColumn: ColumnItem = {
        title: t('monitor.search.identifier'),
        dataIndex: 'identifier',
        key: 'identifier',
        width: 90,
        fixed: 'left'
      };
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
                background: row.color
              }}
            ></div>
          )
        },
        identifierColumn,
        ..._columns
      ];
    }, [details, unit, t]);

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
    }, [data, colors, details, unit]);

    return (
      <div className={chartStyle.tableArea}>
        <CustomTable
          className="w-full"
          rowKey="id"
          size="small"
          scroll={{ y: 240 }}
          dataSource={tableData}
          columns={columns}
        />
      </div>
    );
  }
);

DimensionTable.displayName = 'DimensionTable';

export default DimensionTable;
