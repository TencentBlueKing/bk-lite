'use client';

import React from 'react';
import { Skeleton, Table } from 'antd';
import { useTranslation } from '@/utils/i18n';

const Bone: React.FC<{ className?: string }> = ({ className = '' }) => (
  <Skeleton.Input active size="small" className={`!min-w-0 ${className}`} />
);

/** 智能体发布/渠道管理页加载骨架 — 与最终布局同构，符合 web/DESIGN.md 规范 */
export default function OpsPilotChannelPageSkeleton() {
  const { t } = useTranslation();

  const skeletonColumns = [
    {
      title: t('skill.channel.name', '名称'),
      key: 'name',
      render: () => (
        <div className="flex items-center gap-2">
          <Skeleton.Avatar active size={20} shape="square" className="!rounded" />
          <Bone className="!h-4 !w-36" />
        </div>
      ),
    },
    {
      title: t('skill.channel.type', '渠道类型'),
      key: 'channel_type',
      width: 150,
      render: () => <Bone className="!h-5 !w-16 !rounded" />,
    },
    {
      title: t('skill.channel.status', '启停'),
      key: 'status',
      width: 130,
      render: () => (
        <div className="flex items-center gap-2">
          <Bone className="!h-4 !w-7 !rounded-full" />
          <Bone className="!h-3.5 !w-10" />
        </div>
      ),
    },
    {
      title: t('common.action', '操作'),
      key: 'action',
      width: 180,
      render: () => (
        <div className="flex items-center gap-3">
          <Bone className="!h-4 !w-8" />
          <Bone className="!h-4 !w-8" />
        </div>
      ),
    },
  ];

  const skeletonData = [
    { key: '1' },
    { key: '2' },
    { key: '3' },
    { key: '4' },
    { key: '5' },
  ];

  return (
    <div
      className="flex h-full flex-col"
      aria-busy="true"
      aria-label="loading"
    >
      {/* 顶部引导说明横幅骨架 */}
      <div className="mb-4 flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)]/40 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Skeleton.Avatar active size={14} shape="circle" />
          <Bone className="!h-3.5 !w-80" />
        </div>
      </div>

      {/* 状态统计卡片骨架 */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="flex items-center gap-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] px-4 py-3"
          >
            <Skeleton.Avatar active size={36} shape="circle" />
            <div className="min-w-0 flex-1">
              <div className="mb-1">
                <Bone className="!h-3.5 !w-16" />
              </div>
              <div>
                <Bone className="!h-7 !w-12" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 工具栏骨架 */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="flex items-center gap-2">
          <Bone className="!h-4 !w-14" />
          <Bone className="!h-3.5 !w-6" />
        </div>
        <div className="flex items-center gap-2">
          <Bone className="!h-8 !w-36 !rounded-md" />
          <Bone className="!h-8 !w-60 !rounded-md" />
          <Skeleton.Button active size="default" className="!h-8 !w-8 !min-w-0 !rounded-md" />
          <Skeleton.Button active size="default" className="!h-8 !w-24 !min-w-0 !rounded-md" />
        </div>
      </div>

      {/* 表格骨架 */}
      <div className="flex-grow">
        <Table
          rowKey="key"
          size="middle"
          pagination={false}
          columns={skeletonColumns}
          dataSource={skeletonData}
          scroll={{ y: 'calc(100vh - 430px)' }}
        />
      </div>
    </div>
  );
}
