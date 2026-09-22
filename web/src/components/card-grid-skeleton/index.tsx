'use client';

import React from 'react';
import { Skeleton } from 'antd';

interface CardGridSkeletonProps {
  count?: number;
  className?: string;
  compact?: boolean;
}

const DEFAULT_GRID_CLASS =
  'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5';

/** Look B 列表卡加载骨架 — 与 grid-entity-card 同解剖 */
export default function CardGridSkeleton({
  count = 8,
  className = DEFAULT_GRID_CLASS,
  compact = false,
}: CardGridSkeletonProps) {
  return (
    <div
      className={`grid gap-4 ${className}`}
      aria-busy="true"
      aria-label="loading"
    >
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className={`flex h-full ${compact ? 'min-h-[144px]' : 'min-h-[168px]'} flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]`}
        >
          <div className={`flex items-center justify-between gap-2.5 px-3.5 ${compact ? 'pt-4' : 'pt-3.5'}`}>
            <div className="flex min-w-0 flex-1 gap-3">
              <Skeleton.Avatar active size={40} shape="square" className="!rounded-md" />
              <div className="min-w-0 flex-1">
                <Skeleton.Input active size="small" className="!h-[15px] !w-[72%] !min-w-0" />
                {compact ? null : (
                  <div className="mt-1 flex min-h-5 items-center">
                    <Skeleton.Input active size="small" className="!h-3 !w-16 !min-w-0" />
                  </div>
                )}
              </div>
            </div>
            {compact ? null : (
              <Skeleton.Avatar active size={16} shape="circle" />
            )}
          </div>
          <div className={`flex flex-1 flex-col gap-2.5 px-3.5 ${compact ? 'pb-4 pt-3' : 'pb-3.5 pt-2.5'}`}>
            <Skeleton active title={false} paragraph={{ rows: 2, width: ['100%', '78%'] }} />
            {compact ? null : (
              <>
                <Skeleton.Input active size="small" className="!h-5 !w-14 !min-w-0 !rounded-md" />
                <div className="mt-auto flex items-center justify-between gap-3 border-t border-[var(--color-fill-2)] pt-2.5">
                  <Skeleton.Input active size="small" className="!h-3 !w-24 !min-w-0" />
                  <Skeleton.Input active size="small" className="!h-3 !w-20 !min-w-0" />
                </div>
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
