'use client';

import React from 'react';
import { Empty, Spin, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';

interface CanvasWorkspaceProps {
  selectedItem?: DirItem | null;
  loading?: boolean;
  titleFallback: string;
  emptyDescription: string;
  description?: string;
  toolbar?: React.ReactNode;
  children?: React.ReactNode;
}

const CanvasWorkspace: React.FC<CanvasWorkspaceProps> = ({
  selectedItem,
  loading = false,
  titleFallback,
  emptyDescription,
  description,
  toolbar,
  children,
}) => {
  const { t } = useTranslation();

  if (!selectedItem) {
    return (
      <Empty className="w-full mt-[20vh]" description={emptyDescription} />
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--color-bg-2)] p-2 pb-0">
      <div
        className="mb-2 flex w-full shrink-0 items-center justify-between rounded-xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)] px-4 py-2.5"
        style={{ boxShadow: '0 8px 22px rgba(31, 63, 104, 0.05)' }}
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
          {(description || selectedItem.desc) && (
            <p className="mt-0.5 mb-0 truncate text-xs leading-4 text-[var(--color-text-3)]">
              {description || selectedItem.desc}
            </p>
          )}
        </div>
        {toolbar && (
          <div className="flex shrink-0 items-center gap-1.5">{toolbar}</div>
        )}
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-[0_12px_28px_rgba(31,63,104,0.06)]">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--color-bg-1)]/70 backdrop-blur-sm">
            <Spin size="large" />
          </div>
        )}
        <div className="h-full min-h-0 overflow-hidden">{children}</div>
      </div>
    </div>
  );
};

export default CanvasWorkspace;
