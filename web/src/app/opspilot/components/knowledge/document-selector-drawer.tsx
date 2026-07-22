'use client';

import React from 'react';
import {
  Button,
  Drawer,
  Empty,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';

export interface KnowledgeDocumentSelectorItem {
  key: string;
  title: string;
  type?: string;
  status?: string;
  chunk_size?: number;
  [key: string]: unknown;
}

export interface KnowledgeDocumentSelectorColumn {
  title: string;
  dataIndex: string;
  key: string;
  width?: number;
}

export interface KnowledgeDocumentSelectorDrawerProps {
  open: boolean;
  title?: string;
  onClose: () => void;
  onConfirm: () => void;
  confirmText?: string;
  activeTab: string;
  onTabChange: (key: string) => void;
  dataSource: KnowledgeDocumentSelectorItem[];
  columns: KnowledgeDocumentSelectorColumn[];
  selectedRowKeys: string[];
  onSelectionChange: (keys: string[]) => void;
  currentPage: number;
  pageSize: number;
  total: number;
  onPaginationChange: (page: number, pageSize: number) => void;
  selectedDocuments: KnowledgeDocumentSelectorItem[];
  onRemoveDocument: (doc: KnowledgeDocumentSelectorItem) => void;
  onClearAll: () => void;
  getDocumentTypeLabel: (type: string) => string;
  emptyDescription?: string;
  confirmHint?: string;
  renderSelectedMeta?: (doc: KnowledgeDocumentSelectorItem) => React.ReactNode;
}

const KnowledgeDocumentSelectorDrawer: React.FC<KnowledgeDocumentSelectorDrawerProps> = ({
  open,
  title = 'Select documents',
  onClose,
  onConfirm,
  confirmText = 'Confirm',
  activeTab,
  onTabChange,
  dataSource,
  columns,
  selectedRowKeys,
  onSelectionChange,
  currentPage,
  pageSize,
  total,
  onPaginationChange,
  selectedDocuments,
  onRemoveDocument,
  onClearAll,
  getDocumentTypeLabel,
  emptyDescription = 'No documents available.',
  confirmHint,
  renderSelectedMeta,
}) => {
  const tableColumns: ColumnsType<KnowledgeDocumentSelectorItem> = columns.map((col) => ({
    title: col.title,
    dataIndex: col.dataIndex,
    key: col.key,
    width: col.width,
  }));

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={title}
      width={920}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" onClick={onConfirm}>
            {confirmText}
          </Button>
        </Space>
      }
    >
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Tabs activeKey={activeTab} onChange={onTabChange} />
          <Table
            rowKey="key"
            size="small"
            dataSource={dataSource}
            columns={tableColumns}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys) => onSelectionChange(keys as string[]),
            }}
            pagination={{
              current: currentPage,
              pageSize,
              total,
              onChange: onPaginationChange,
            }}
          />
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium">Selected ({selectedDocuments.length})</span>
            <Button size="small" type="link" onClick={onClearAll}>
              Clear all
            </Button>
          </div>
          {selectedDocuments.length === 0 ? (
            <Empty description={emptyDescription} />
          ) : (
            <Space direction="vertical" className="w-full">
              {selectedDocuments.map((doc) => (
                <div
                  key={doc.key}
                  className="flex items-center justify-between rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2"
                >
                  <div>
                    <div className="text-sm font-medium">{doc.title}</div>
                    <div className="text-xs text-gray-500">
                      <Tag bordered={false}>{getDocumentTypeLabel(doc.type ?? '')}</Tag>
                      {doc.status ? <Tag bordered={false}>{doc.status}</Tag> : null}
                      {renderSelectedMeta ? renderSelectedMeta(doc) : null}
                    </div>
                  </div>
                  <Tooltip title="Remove">
                    <Button size="small" type="link" onClick={() => onRemoveDocument(doc)}>
                      Remove
                    </Button>
                  </Tooltip>
                </div>
              ))}
            </Space>
          )}
          {confirmHint ? <div className="mt-3 text-xs text-gray-500">{confirmHint}</div> : null}
        </div>
      </div>
    </Drawer>
  );
};

export default KnowledgeDocumentSelectorDrawer;
