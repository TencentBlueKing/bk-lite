'use client';

import React from 'react';
import { CloseOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';

interface DualSelectorProps<T extends object> {
  leftTitle?: React.ReactNode;
  rightTitle?: React.ReactNode;
  dataSource: T[];
  columns: ColumnsType<T>;
  selectedKeys: React.Key[];
  onChange: (keys: React.Key[]) => void;
  rowKey: keyof T | ((record: T) => React.Key);
  getCheckboxProps?: (record: T) => { disabled?: boolean };
  height?: string;
  loading?: boolean;
  pagination?: TablePaginationConfig | false;
  onPageChange?: (page: number, pageSize: number) => void;
  selectedRecordsData?: T[];
  renderSelectedLabel: (record: T) => string;
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
  selectionColumnFixed = false,
}: DualSelectorProps<T>) {
  const { t } = useTranslation();
  const getRecordKey = (record: T): React.Key => {
    if (typeof rowKey === 'function') {
      return rowKey(record);
    }
    return record[rowKey] as React.Key;
  };

  const selectedRecords = selectedRecordsData ?? dataSource.filter((r) => selectedKeys.includes(getRecordKey(r)));

  const tablePagination: TablePaginationConfig | false = pagination ?? {
    total: dataSource.length,
    pageSize: 10,
    showSizeChanger: true,
    showTotal: (total) => t('patchManager.common.totalItems', 'Total {count} items', { count: total }),
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
            onChange={onPageChange ? (p) => onPageChange(p.current || 1, p.pageSize || 10) : undefined}
          />
        </div>
      </div>
      <div className="flex w-[220px] flex-col border-l border-[var(--color-border-1)] pl-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-medium">
            {rightTitle || t('patchManager.common.selectedItems', 'Selected {count} items', { count: selectedRecords.length })}
          </span>
          {selectedRecords.length > 0 && (
            <a
              className="cursor-pointer text-xs text-[var(--color-fail)]"
              onClick={() => onChange([])}
            >
              {t('patchManager.common.clearAll', 'Clear all')}
            </a>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {selectedRecords.map((r) => {
            const recordKey = getRecordKey(r);
            return (
              <div
                key={recordKey}
                className="group mb-1 flex items-center justify-between rounded-md bg-[var(--color-fill-1)] px-2 py-1.5 text-[13px]"
              >
                <span className="truncate">
                  {renderSelectedLabel(r)}
                </span>
                <CloseOutlined
                  className="cursor-pointer text-xs text-[var(--color-text-4)] opacity-0 transition-opacity group-hover:opacity-100"
                  onClick={() => onChange(selectedKeys.filter((k) => k !== recordKey))}
                />
              </div>
            );
          })}
          {selectedRecords.length === 0 && (
            <div className="mt-10 text-center text-[13px] text-[var(--color-text-3)]">
              {t('patchManager.common.noSelection', 'No selection')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
