'use client';

import React from 'react';
import { Empty, Spin, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { DirItem } from '@/app/ops-analysis/types';

interface StatItem {
  label: string;
  value: React.ReactNode;
}

interface BasicCanvasPageProps {
  selectedItem?: DirItem | null;
  loading?: boolean;
  titleFallback: string;
  emptyDescription: string;
  description?: string;
  stats?: StatItem[];
  children?: React.ReactNode;
  extra?: React.ReactNode;
}

const BasicCanvasPage: React.FC<BasicCanvasPageProps> = ({
  selectedItem,
  loading = false,
  titleFallback,
  emptyDescription,
  description,
  stats = [],
  children,
  extra,
}) => {
  const { t } = useTranslation();

  if (!selectedItem) {
    return (
      <Empty className="w-full mt-[20vh]" description={emptyDescription} />
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-[var(--color-bg-1)]">
      <div className="border-b border-[var(--color-border-1)] px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="m-0 truncate text-xl font-semibold text-[var(--color-text-1)]">
                {selectedItem.name || titleFallback}
              </h2>
              {selectedItem.is_build_in && (
                <Tag color="blue" className="rounded-full! px-2! py-0.5!">
                  {t('common.builtIn')}
                </Tag>
              )}
            </div>
            <p className="mt-1 mb-0 text-sm text-[var(--color-text-2)]">
              {description || selectedItem.desc || '--'}
            </p>
          </div>
          {extra && <div className="flex shrink-0 items-center gap-2">{extra}</div>}
        </div>
        {stats.length > 0 && (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {stats.map((item) => (
              <div
                key={item.label}
                className="rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)] px-4 py-3"
              >
                <div className="text-xs text-[var(--color-text-3)]">
                  {item.label}
                </div>
                <div className="mt-1 text-base font-medium text-[var(--color-text-1)]">
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <Spin spinning={loading} wrapperClassName="h-full">
        <div className="h-full flex-1 overflow-auto p-6">{children}</div>
      </Spin>
    </div>
  );
};

export default BasicCanvasPage;
