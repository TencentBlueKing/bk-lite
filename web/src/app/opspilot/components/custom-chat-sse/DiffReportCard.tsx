'use client';

import React, { useState } from 'react';
import { Modal, Tag } from 'antd';
import { FileTextOutlined, RightOutlined } from '@ant-design/icons';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { ConfigDiffReport, ConfigDiffItem } from '@/app/opspilot/types/global';

interface DiffReportCardProps {
  report: ConfigDiffReport;
}

const severityConfig = {
  critical: { color: '#f5222d', label: '严重', tagColor: 'error' },
  high: { color: '#fa541c', label: '高危', tagColor: 'volcano' },
  warning: { color: '#fa8c16', label: '警告', tagColor: 'warning' },
  info: { color: '#1890ff', label: '提示', tagColor: 'processing' },
} as const;

const DiffReportCard: React.FC<DiffReportCardProps> = ({ report }) => {
  const [selectedItem, setSelectedItem] = useState<ConfigDiffItem | null>(null);

  return (
    <div className="mt-3 w-full max-w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-white border-b border-gray-200 flex items-center gap-2">
        <FileTextOutlined className="text-blue-500 text-base" />
        <span className="font-semibold text-sm text-gray-800">{report.title}</span>
        <Tag className="ml-auto !mb-0" color="blue">{report.cluster_name}</Tag>
      </div>

      {/* Items */}
      <div className="divide-y divide-gray-100">
        {report.items.map((item, idx) => {
          const sev = severityConfig[item.severity];
          return (
            <div
              key={idx}
              className="px-4 py-3 cursor-pointer hover:bg-blue-50/50 transition-colors group"
              onClick={() => setSelectedItem(item)}
            >
              <div className="flex items-center gap-2">
                <Tag color={sev.tagColor} className="!m-0 text-xs">{sev.label}</Tag>
                <span className="text-sm font-medium text-gray-800 font-mono">
                  {item.namespace}/{item.workload_name}
                </span>
                <span className="text-xs text-gray-400 shrink-0">
                  {item.workload_type}
                </span>
                <RightOutlined className="ml-auto text-gray-300 text-xs group-hover:text-blue-400 transition-colors" />
              </div>
              <div className="mt-1.5 ml-[52px] text-xs text-gray-500 leading-relaxed">
                {item.summary}
              </div>
            </div>
          );
        })}
      </div>

      {/* Diff Modal */}
      <Modal
        open={!!selectedItem}
        onCancel={() => setSelectedItem(null)}
        title={
          selectedItem && (
            <div className="flex items-center gap-2">
              <Tag color={severityConfig[selectedItem.severity].tagColor}>
                {severityConfig[selectedItem.severity].label}
              </Tag>
              <span className="font-medium">{selectedItem.namespace}/{selectedItem.workload_name}</span>
              <span className="text-gray-400 text-sm font-normal">({selectedItem.workload_type})</span>
            </div>
          )
        }
        footer={null}
        width="90vw"
        styles={{ body: { padding: 0, maxHeight: '70vh', overflow: 'auto' } }}
      >
        {selectedItem && (
          <div>
            <div className="px-4 py-2 bg-gray-50 border-b text-sm text-gray-600">
              {selectedItem.summary}
            </div>
            <ReactDiffViewer
              oldValue={selectedItem.before_yaml}
              newValue={selectedItem.after_yaml}
              splitView={true}
              compareMethod={DiffMethod.LINES}
              leftTitle="❌ 当前配置"
              rightTitle="✅ 修复后配置"
              styles={{
                variables: {
                  light: {
                    diffViewerBackground: '#fafafa',
                    addedBackground: '#e6ffed',
                    addedColor: '#24292e',
                    removedBackground: '#ffeef0',
                    removedColor: '#24292e',
                    wordAddedBackground: '#acf2bd',
                    wordRemovedBackground: '#fdb8c0',
                  },
                },
              }}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default DiffReportCard;
