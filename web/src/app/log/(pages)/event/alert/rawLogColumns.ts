import type { ReactNode } from 'react';
import { ColumnItem, TableDataItem } from '@/app/log/types';

interface BuildLogAlertRawColumnsParams {
  isAggregate: boolean;
  showFields?: string[];
  rawData?: TableDataItem[];
  renderTime?: (value?: string) => ReactNode;
}

const FIELD_ALIAS: Record<string, string> = {
  timestamp: '_time',
  _time: '_time',
  message: 'message',
  _msg: 'message'
};

const normalizeField = (field: string) => FIELD_ALIAS[field] || field;

export const buildLogAlertRawColumns = ({
  isAggregate,
  showFields = [],
  rawData = [],
  renderTime
}: BuildLogAlertRawColumnsParams): ColumnItem[] => {
  const firstRow = rawData[0] || {};
  const aggregateStatsRow =
    isAggregate &&
    rawData.length > 0 &&
    !('message' in firstRow) &&
    !('_msg' in firstRow);
  if (aggregateStatsRow) {
    return Object.keys(firstRow)
      .filter((item) => item !== 'id')
      .map((item) => ({
        title: item,
        dataIndex: item,
        key: item
      }));
  }

  const columns: ColumnItem[] = [
    {
      title: 'timestamp',
      dataIndex: '_time',
      key: '_time',
      width: 150,
      fixed: 'left',
      sorter: (a: any, b: any) => a.id - b.id,
      render: (val, record) => {
        const value = val || record.timestamp;
        return value && renderTime ? renderTime(value) : value || '--';
      }
    },
    {
      title: 'message',
      dataIndex: 'message',
      key: 'message',
      width: 350,
      render: (val, record) => val || record._msg || '--'
    }
  ];
  const existingFields = new Set(columns.map((item) => item.dataIndex));

  showFields.forEach((field) => {
    const normalizedField = normalizeField(field);
    if (existingFields.has(normalizedField)) {
      return;
    }
    existingFields.add(normalizedField);
    columns.push({
      title: field,
      dataIndex: field,
      key: field
    });
  });

  return columns;
};
