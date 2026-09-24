'use client';

import { CloseOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import type { Key, ReactNode } from 'react';

import CustomTable from '@/components/custom-table';

interface DualSelectorProps<T extends object> {
  leftTitle?: ReactNode;
  rightTitle: ReactNode;
  dataSource: T[];
  columns: ColumnsType<T>;
  selectedKeys: Key[];
  onChange: (keys: Key[]) => void;
  rowKey: keyof T | ((record: T) => Key);
  getCheckboxProps?: (record: T) => { disabled?: boolean };
  height?: string;
  loading?: boolean;
  pagination?: TablePaginationConfig | false;
  onPageChange?: (page: number, pageSize: number) => void;
  selectedRecordsData?: T[];
  renderSelectedLabel?: (record: T) => ReactNode;
  renderSelectedItem?: (record: T) => ReactNode;
  clearAllText: ReactNode;
  emptySelectionText: ReactNode;
  selectedPreviewLabel: string;
  getRemoveLabel: (record: T) => string;
  selectionColumnFixed?: boolean;
}

export default function DualSelector<T extends object>({
  leftTitle,
  rightTitle,
  dataSource,
  columns,
  selectedKeys,
  onChange,
  rowKey,
  getCheckboxProps,
  height = 'calc(100vh - 280px)',
  loading,
  pagination,
  onPageChange,
  selectedRecordsData,
  renderSelectedLabel,
  renderSelectedItem,
  clearAllText,
  emptySelectionText,
  selectedPreviewLabel,
  getRemoveLabel,
  selectionColumnFixed = false,
}: DualSelectorProps<T>) {
  const getRecordKey = (record: T): Key => {
    if (typeof rowKey === 'function') return rowKey(record);
    return record[rowKey] as Key;
  };

  const selectedRecords = selectedRecordsData ?? dataSource.filter((record) => (
    selectedKeys.includes(getRecordKey(record))
  ));
  const tablePagination: TablePaginationConfig | false = pagination ?? {
    total: dataSource.length,
    pageSize: 10,
    showSizeChanger: true,
  };

  return (
    <div className="flex gap-4" style={{ height }}>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {leftTitle}
        <div className="min-h-0 flex-1">
          <CustomTable<T>
            size="small"
            rowKey={rowKey}
            loading={loading}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: selectedKeys,
              onChange,
              getCheckboxProps,
              preserveSelectedRowKeys: true,
              fixed: selectionColumnFixed,
            }}
            columns={columns}
            dataSource={dataSource}
            pagination={tablePagination}
            onChange={onPageChange ? (next) => onPageChange(next.current || 1, next.pageSize || 10) : undefined}
          />
        </div>
      </div>
      <aside className="flex w-[220px] flex-col border-l border-[var(--color-border-1)] pl-4" aria-label={selectedPreviewLabel}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="font-medium text-[var(--color-text-1)]">
            {rightTitle}
          </span>
          {selectedKeys.length > 0 && (
            <Button type="link" size="small" danger className="!h-auto !p-0" onClick={() => onChange([])}>
              {clearAllText}
            </Button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {selectedRecords.map((record) => {
            const recordKey = getRecordKey(record);
            return (
              <div key={recordKey} className="group mb-2 flex items-center gap-2 rounded-md bg-[var(--color-fill-1)] px-3 py-2 text-[13px]">
                <div className="min-w-0 flex-1">
                  {renderSelectedItem?.(record) ?? renderSelectedLabel?.(record) ?? String(recordKey)}
                </div>
                <Button
                  type="text"
                  size="small"
                  className="shrink-0 !h-7 !w-7 !p-0 text-[var(--color-text-4)]"
                  aria-label={getRemoveLabel(record)}
                  icon={<CloseOutlined aria-hidden="true" />}
                  onClick={() => onChange(selectedKeys.filter((key) => key !== recordKey))}
                />
              </div>
            );
          })}
          {selectedRecords.length === 0 && (
            <div className="mt-10 text-center text-[13px] text-[var(--color-text-3)]">
              {emptySelectionText}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
