'use client';

import React from 'react';
import { CloseOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
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
}: DualSelectorProps<T>) {
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
    showTotal: (t) => `共 ${t} 条`,
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
          <span style={{ fontWeight: 500 }}>{rightTitle || `已选 ${selectedRecords.length} 项`}</span>
          {selectedRecords.length > 0 && (
            <a style={{ color: '#ff4d4f', fontSize: 12 }} onClick={() => onChange([])}>
              全部清除
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
              暂未选择
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
