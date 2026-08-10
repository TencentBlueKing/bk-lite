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
    <div style={{ display: 'flex', gap: 16, height }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {leftTitle}
        <div style={{ flex: 1, minHeight: 0 }}>
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
      <div
        style={{
          width: 220,
          display: 'flex',
          flexDirection: 'column',
          borderLeft: '1px solid var(--color-border-1, #e8e8e8)',
          paddingLeft: 16,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
          }}
        >
          <span style={{ fontWeight: 500 }}>{rightTitle || t('patchManager.common.selectedItems', 'Selected {count} items', { count: selectedRecords.length })}</span>
          {selectedRecords.length > 0 && (
            <a style={{ color: '#ff4d4f', fontSize: 12 }} onClick={() => onChange([])}>
              {t('patchManager.common.clearAll', 'Clear all')}
            </a>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {selectedRecords.map((r) => {
            const recordKey = getRecordKey(r);
            return (
              <div
                key={recordKey}
                className="dual-selector-item"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '6px 8px',
                  borderRadius: 6,
                  marginBottom: 4,
                  background: 'var(--color-fill-1, #f4f6f9)',
                  fontSize: 13,
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {renderSelectedLabel(r)}
                </span>
                <CloseOutlined
                  className="dual-selector-remove-btn"
                  style={{
                    color: '#bfbfbf',
                    fontSize: 12,
                    cursor: 'pointer',
                    opacity: 0,
                    transition: 'opacity 0.2s',
                  }}
                  onClick={() => onChange(selectedKeys.filter((k) => k !== recordKey))}
                />
              </div>
            );
          })}
          {selectedRecords.length === 0 && (
            <div
              style={{
                color: 'var(--color-text-3, #8c8c8c)',
                fontSize: 13,
                textAlign: 'center',
                marginTop: 40,
              }}
            >
              {t('patchManager.common.noSelection', 'No selection')}
            </div>
          )}
        </div>
      </div>
      <style>{`
        .dual-selector-item:hover .dual-selector-remove-btn { opacity: 1 !important; }
      `}</style>
    </div>
  );
}
