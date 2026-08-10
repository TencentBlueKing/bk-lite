'use client';

import React, { useMemo } from 'react';
import { Button, Table, Tabs } from 'antd';
import { FileOutlined, FolderOutlined } from '@ant-design/icons';
import ContentFormDrawer from '@/components/content-form-drawer';
import CompactEmptyState from '@/components/compact-empty-state';
import DetailListPanel from '@/components/detail-list-panel';
import MarkdownRenderer from '@/components/markdown';
import VersionBadge from '@/components/version-badge';
import { useTranslation } from '@/utils/i18n';
import type {
  JobPlaybookDetailLike as Playbook,
  JobPlaybookFileTreeNode as FileTreeNode,
} from './types';

interface SummaryItem {
  label: React.ReactNode;
  value: React.ReactNode;
}

export interface JobPlaybookDetailDrawerProps {
  open: boolean;
  onClose: () => void;
  playbook: Playbook | null;
  loading?: boolean;
  width?: number;
  extra?: React.ReactNode;
  summaryItems?: SummaryItem[];
  formatUpdatedAt?: (value: string) => React.ReactNode;
  onPreviewFile?: (fullPath: string) => void;
}

const JobPlaybookDetailDrawer: React.FC<JobPlaybookDetailDrawerProps> = ({
  open,
  onClose,
  playbook,
  loading = false,
  width = 600,
  extra,
  summaryItems = [],
  formatUpdatedAt,
  onPreviewFile,
}) => {
  const { t } = useTranslation();

  const renderFileTree = (
    nodes: FileTreeNode[],
    depth = 0,
    parentPaths: string[] = [],
  ): React.ReactNode =>
    nodes.map((node, idx) => {
      const currentPath = [...parentPaths, node.name];
      const fullPath = currentPath.join('/');

      return (
        <div key={`${depth}-${idx}-${node.name}`}>
          <div
            className="flex items-center justify-between rounded px-2 py-1.5 hover:bg-(--color-fill-2)"
            style={{ paddingLeft: `${depth * 20 + 8}px` }}
          >
            <div className="flex items-center gap-2">
              {node.type === 'directory' ? (
                <FolderOutlined style={{ color: '#faad14' }} />
              ) : (
                <FileOutlined style={{ color: 'var(--color-text-3)' }} />
              )}
              <span className="text-sm" style={{ color: 'var(--color-text-1)' }}>
                {node.name}
              </span>
            </div>
            {node.type === 'file' && onPreviewFile ? (
              <Button type="link" size="small" onClick={() => onPreviewFile(fullPath)}>
                {t('job.preview')}
              </Button>
            ) : null}
          </div>
          {node.type === 'directory' && node.children
            ? renderFileTree(node.children, depth + 1, currentPath)
            : null}
        </div>
      );
    });

  const tabs = useMemo(() => {
    if (!playbook) {
      return [];
    }

    const basicInfoItems = [
      ...summaryItems,
      { label: t('job.playbookName'), value: playbook.name },
      { label: t('job.playbookDescription'), value: playbook.description || '-' },
      { label: t('job.currentVersion'), value: playbook.version || '-' },
      {
        label: t('job.recentUpdateTime'),
        value: formatUpdatedAt ? formatUpdatedAt(playbook.updated_at) : playbook.updated_at || '-',
      },
      { label: t('job.uploader'), value: playbook.created_by || '-' },
    ];

    return [
      {
        key: 'basicInfo',
        label: t('job.basicInfoTab'),
        children: (
          <div className="py-2">
            <DetailListPanel
              className="border-0 bg-transparent"
              labelWidthClassName="w-32"
              items={basicInfoItems.map((item, idx) => ({
                key: `${idx}`,
                label: item.label,
                displayValue: item.value,
                copyable: false,
              }))}
            />
          </div>
        ),
      },
      {
        key: 'params',
        label: t('job.paramsDescriptionTab'),
        children:
          playbook.params && playbook.params.length > 0 ? (
            <Table
              dataSource={playbook.params}
              rowKey="name"
              pagination={false}
              size="small"
              columns={[
                {
                  title: t('job.parameterName'),
                  dataIndex: 'name',
                  key: 'name',
                  render: (text: string) => (
                    <span className="font-mono text-[var(--color-primary)]">{text}</span>
                  ),
                },
                {
                  title: t('job.defaultVal'),
                  dataIndex: 'default',
                  key: 'default',
                  render: (text: string) => text || '-',
                },
                {
                  title: t('job.paramDesc'),
                  dataIndex: 'description',
                  key: 'description',
                  render: (text: string) => text || '-',
                },
              ]}
            />
          ) : (
            <CompactEmptyState description={t('job.noParams')} className="py-8" />
          ),
      },
      {
        key: 'fileList',
        label: t('job.fileListTab'),
        children:
          playbook.file_list && playbook.file_list.length > 0 ? (
            <div
              className="rounded-md border p-2"
              style={{ borderColor: 'var(--color-border-1)' }}
            >
              {renderFileTree(playbook.file_list)}
            </div>
          ) : (
            <CompactEmptyState description={t('job.noFiles')} className="py-8" />
          ),
      },
      {
        key: 'readme',
        label: t('job.readmeTab'),
        children: playbook.readme ? (
          <MarkdownRenderer content={playbook.readme} />
        ) : (
          <CompactEmptyState description={t('job.noReadme')} className="py-8" />
        ),
      },
    ];
  }, [formatUpdatedAt, onPreviewFile, playbook, summaryItems, t]);

  return (
    <ContentFormDrawer
      open={open}
      onClose={onClose}
      width={width}
      title={
        playbook ? (
          <div className="flex items-center gap-3">
            <span>{playbook.name}</span>
            <VersionBadge value={playbook.version} />
          </div>
        ) : null
      }
      extra={extra}
      loading={loading}
      hideFooter
      styles={{
        body: {
          padding: '0 24px 24px',
        },
      }}
    >
      {playbook ? (
        <Tabs
          items={tabs}
          className="h-full [&_.ant-tabs-content]:h-full [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tabpane]:overflow-auto"
        />
      ) : null}
    </ContentFormDrawer>
  );
};

export default JobPlaybookDetailDrawer;
