import React, { useState } from 'react';
import { Button, Table, Input, InputNumber, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { TableColumnSpec } from '@/app/cmdb/types/assetManage';
import { parseTableValue } from './common';

interface TableFieldEditorProps {
  columns: TableColumnSpec[];
  disabled?: boolean;
  value?: any;
  onChange?: (value: any) => void;
  inModal?: boolean;
}

const TableFieldEditor: React.FC<TableFieldEditorProps> = ({
  columns,
  disabled,
  value,
  onChange,
  inModal,
}) => {
  const { t } = useTranslation();
  const createEmptyRow = () => {
    const newRow: any = {};
    (Array.isArray(columns) ? columns : []).forEach((col) => {
      newRow[col.column_id] = '';
    });
    return newRow;
  };

  const initializedRef = React.useRef(false);

  const parseValue = parseTableValue;

  const [dataSource, setDataSource] = useState<any[]>(() => parseValue(value));

  React.useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      setDataSource(parseValue(value));
    }
  }, [value]);

  const isRowEmpty = (row: any) => {
    return columns.every((col) => {
      const val = row[col.column_id];
      return val === '' || val === null || val === undefined;
    });
  };

  const handleChange = (newData: any[]) => {
    setDataSource(newData);
    const nonEmptyRows = newData.filter((row) => !isRowEmpty(row));
    onChange?.(nonEmptyRows.length > 0 ? nonEmptyRows : undefined);
  };

  const handleAddRow = (index?: number) => {
    const newData = [...dataSource];
    if (index === undefined) {
      newData.push(createEmptyRow());
    } else {
      newData.splice(index + 1, 0, createEmptyRow());
    }
    handleChange(newData);
  };

  const handleDeleteRow = (index: number) => {
    const newData = dataSource.filter((_, idx) => idx !== index);
    handleChange(newData);
  };

  const handleCellChange = (index: number, columnId: string, val: any) => {
    const newData = [...dataSource];
    newData[index] = { ...newData[index], [columnId]: val };
    handleChange(newData);
  };
  const sortedColumns = [...(Array.isArray(columns) ? columns : [])].sort((a, b) => a.order - b.order);

  const tableColumns: Array<{
    title: string;
    dataIndex: string;
    key: string;
    align?: 'center';
    width?: number;
    render: (_: any, record: any, index: number) => React.ReactNode;
  }> = sortedColumns.map((col) => ({
    title: col.column_name,
    dataIndex: col.column_id,
    key: col.column_id,
    align: 'center' as const,
    render: (_: any, record: any, index: number) => {
      if (col.column_type === 'number') {
        return (
          <InputNumber
            value={record[col.column_id]}
            onChange={(val) => handleCellChange(index, col.column_id, val)}
            disabled={disabled}
            placeholder={t('common.inputTip')}
            style={{ width: '100%' }}
          />
        );
      }
      return (
        <Input
          value={record[col.column_id]}
          onChange={(e) =>
            handleCellChange(index, col.column_id, e.target.value)
          }
          disabled={disabled}
          placeholder={t('common.inputTip')}
        />
      );
    },
  }));

  tableColumns.push({
    title: t('common.actions'),
    key: 'action',
    dataIndex: 'action',
    width: 90,
    render: (_: any, __: any, index: number) => (
      <Space size={2}>
        <Button
          type="text"
          size="small"
          onClick={() => handleAddRow(index)}
          disabled={disabled}
          style={{
            minWidth: 20,
            padding: '0 4px',
            color: 'var(--color-primary)',
            fontSize: 16,
          }}
        >
          +
        </Button>
        {dataSource.length > 0 && (
          <Button
            type="text"
            size="small"
            onClick={() => handleDeleteRow(index)}
            disabled={disabled}
            style={{
              minWidth: 24,
              padding: '0 4px',
              color: 'var(--color-primary)',
              fontSize: 16,
            }}
          >
            −
          </Button>
        )}
      </Space>
    ),
  });

  return (
    <div className={inModal ? 'relative' : ''}>
      {dataSource.length === 0 && (
        <div
          className={
            inModal ? 'absolute right-0 -top-7 z-10' : 'flex justify-end mb-2'
          }
        >
          <Button
            type="link"
            size="small"
            icon={<PlusOutlined />}
            onClick={() => handleAddRow()}
            disabled={disabled}
            className="p-0"
          >
            {t('common.add')}
          </Button>
        </div>
      )}
      <Table
        dataSource={dataSource}
        columns={tableColumns}
        pagination={false}
        size="small"
        tableLayout="fixed"
        style={{ width: '100%' }}
        rowKey={(_, index) => String(index)}
        className="[&_.ant-table-thead_th]:py-1 [&_.ant-table-thead_th]:text-xs [&_.ant-table-placeholder_.ant-empty]:my-0 [&_.ant-table-placeholder_.ant-empty-image]:h-6 [&_.ant-table-placeholder_.ant-empty-image_svg]:h-6 [&_.ant-table-placeholder_td]:!py-2"
      />
    </div>
  );
};

export default TableFieldEditor;
