'use client';

import React from 'react';
import { Empty, Spin, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';
import { resolveCanvasDescription } from '@/app/ops-analysis/utils/canvasDescription';

interface ViewWorkspaceProps {
  selectedItem?: DirItem | null;
  loading?: boolean;
  titleFallback: string;
  emptyDescription: string;
  toolbar?: React.ReactNode;
  filterBar?: React.ReactNode;
  contentRef?: React.Ref<HTMLDivElement>;
  contentClassName?: string;
  headerVisible?: boolean;
  children?: React.ReactNode;
}

const ViewWorkspace: React.FC<ViewWorkspaceProps> = ({
  selectedItem,
  loading = false,
  titleFallback,
  emptyDescription,
  toolbar,
  filterBar,
  contentRef,
  contentClassName = 'bg-[#f7f8fa]',
  headerVisible = true,
  children,
}) => {
  const { t } = useTranslation();

  if (!selectedItem) {
    return (
      <Empty className="w-full mt-[20vh]" description={emptyDescription} />
    );
  }

  const resolvedDescription = resolveCanvasDescription(selectedItem.desc);

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--color-bg-2)]">
      <div
        className={`mb-2 w-full shrink-0 items-center justify-between border-b border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-4 py-2 ${headerVisible ? 'flex' : 'hidden'}`}
      >
        <div className="mr-6 min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="m-0 truncate text-base font-semibold leading-6 text-[var(--color-text-1)]">
              {selectedItem.name || titleFallback}
            </h2>
            {selectedItem.is_build_in && (
              <Tag color="blue" className="rounded-full! px-2! py-0.5! text-xs">
                {t('common.builtIn')}
              </Tag>
            )}
          </div>
          {resolvedDescription && (
            <p className="mt-0.5 mb-0 truncate text-xs leading-4 text-[var(--color-text-3)]">
              {resolvedDescription}
            </p>
          )}
        </div>
        {toolbar && (
          <div className="flex shrink-0 items-center gap-1.5">{toolbar}</div>
        )}
      </div>

      <div
        ref={contentRef}
        className={`relative min-h-0 flex-1 overflow-hidden ${contentClassName}`}
      >
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--color-bg-1)]/70 backdrop-blur-sm">
            <Spin size="large" />
          </div>
        )}
        <div className="flex h-full min-h-0 flex-col overflow-hidden">
          {filterBar && (
            <div className="shrink-0 bg-[var(--color-bg-1)] px-2.5 pb-2 pt-1">
              {filterBar}
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-hidden pt-1">{children}</div>
        </div>
      </div>
    </div>
  );
};

export default ViewWorkspace;
