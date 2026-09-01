'use client';

import React from 'react';
import { Skeleton } from 'antd';

interface OpsPilotCardGridSkeletonProps {
  count?: number;
  className?: string;
}

/** Look B 列表卡加载骨架 — 各 OpsPilot 列表页刷新时共用 */
export default function OpsPilotCardGridSkeleton({
  count = 8,
  className = '',
}: OpsPilotCardGridSkeletonProps) {
  return (
    <div
      className={`grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 ${className}`}
      aria-busy="true"
      aria-label="loading"
    >
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="flex h-full min-h-[168px] flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]"
        >
          <div className="flex items-start justify-between gap-2.5 px-3.5 pt-3.5">
            <div className="flex min-w-0 flex-1 gap-3">
              <Skeleton.Avatar active size={40} shape="square" className="!rounded-md" />
              <div className="min-w-0 flex-1">
                <Skeleton.Input active size="small" className="!h-[15px] !w-[72%] !min-w-0" />
                <div className="mt-1 flex min-h-5 items-center">
                  <Skeleton.Input active size="small" className="!h-3 !w-16 !min-w-0" />
                </div>
              </div>
            </div>
            <Skeleton.Avatar active size={16} shape="circle" />
          </div>

          <div className="flex flex-1 flex-col gap-2.5 px-3.5 pb-3.5 pt-2.5">
            <Skeleton active title={false} paragraph={{ rows: 2, width: ['100%', '78%'] }} />
            <Skeleton.Input active size="small" className="!h-5 !w-14 !min-w-0 !rounded-md" />
            <div className="mt-auto flex items-center justify-between gap-3 border-t border-[var(--color-fill-2)] pt-2.5">
              <Skeleton.Input active size="small" className="!h-3 !w-24 !min-w-0" />
              <Skeleton.Input active size="small" className="!h-3 !w-20 !min-w-0" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
