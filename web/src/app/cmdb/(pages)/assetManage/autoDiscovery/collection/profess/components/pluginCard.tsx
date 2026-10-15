'use client';

import React from 'react';
import Image from 'next/image';
import { Tooltip } from 'antd';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';
import {
  cleanPluginName,
  getCollectionIconSrc,
} from '../pluginCatalog';

export { getCollectionIconSrc };

interface ExpandableTextProps {
  text?: string;
  collapsedLines?: 2 | 3;
}

interface PluginCardProps {
  tab: TreeNode;
  isActive: boolean;
  onSelect: (pluginId: string) => void;
  runningLabel: string;
  successLabel: string;
  failedLabel: string;
  runningCount: number;
  successCount: number;
  failedCount: number;
}

const ExpandableText: React.FC<ExpandableTextProps> = ({
  text,
  collapsedLines = 3,
}) => {
  if (!text) {
    return null;
  }

  return (
    <div
      className={`mt-1.5 text-xs leading-5 text-[var(--color-text-3)] ${collapsedLines === 3 ? 'line-clamp-3' : 'line-clamp-2'}`}
    >
      {text}
    </div>
  );
};

const PluginCard: React.FC<PluginCardProps> = React.memo(
  ({
    tab,
    isActive,
    onSelect,
    runningLabel,
    successLabel,
    failedLabel,
    runningCount,
    successCount,
    failedCount,
  }) => {
    const tags = tab.tag || [];
    const description = tab.desc || '';
    const iconSrc = getCollectionIconSrc(tab);

    const { cleanName, isBeta } = cleanPluginName(tab.name);

    const statusItems = [
      {
        dotClass: 'bg-[var(--color-primary)]',
        label: runningLabel,
        value: runningCount,
      },
      {
        dotClass: 'bg-[var(--color-success)]',
        label: successLabel,
        value: successCount,
      },
      {
        dotClass: 'bg-[var(--color-fail)]',
        label: failedLabel,
        value: failedCount,
      },
    ];

    return (
      <div
        role="button"
        tabIndex={0}
        aria-pressed={isActive}
        className={`group relative w-full shrink-0 cursor-pointer overflow-hidden rounded-xl border p-3 text-left transition-colors ${
          isActive
            ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]'
            : 'border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)]'
        }`}
        onClick={() => onSelect(tab.id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onSelect(tab.id);
          }
        }}
      >
        <div className="relative z-10 flex items-start gap-2.5">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${
              isActive
                ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)]'
                : 'border-[var(--color-border)] bg-[var(--color-fill-1)]'
            }`}
          >
            <Image
              src={iconSrc}
              alt={tab.name}
              width={26}
              height={26}
              unoptimized
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div
                  className={`text-sm font-semibold leading-5 tracking-[0.01em] wrap-break-word flex items-center gap-1 ${isActive ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-1)]'}`}
                >
                  <span>{cleanName}</span>
                  {isBeta && (
                    <span className="scale-90 px-1 py-0.2 text-[9px] font-semibold text-amber-700 bg-amber-50 rounded border border-amber-200/80 leading-none">
                      BETA
                    </span>
                  )}
                </div>
                <ExpandableText text={description} collapsedLines={2} />
              </div>
              <div
                className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${isActive ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-fill-3)]'}`}
              />
            </div>

            {tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-xs leading-4 text-[var(--color-text-3)]">
                {tags.map((tag: string) => (
                  <span
                    key={tag}
                    className={`inline-flex items-center wrap-break-word ${isActive ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-3)]'}`}
                  >
                    <span
                      className={`mr-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-fill-4)]'}`}
                    />
                    <span className="break-keep">{tag}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <Tooltip
          placement="left"
          title={
            <div className="flex flex-col gap-1.5">
              {statusItems.map(({ dotClass, value, label }) => (
                <div key={label} className="flex items-center gap-2 text-xs">
                  <div className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`} />
                  <span>
                    {label}：{value}
                  </span>
                </div>
              ))}
            </div>
          }
        >
          <div
            className="mt-3 border-t border-[var(--color-border-2)] pt-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center">
              {statusItems.map(({ dotClass, value, label }, index) => (
                <div
                  key={label}
                  className={`flex flex-1 items-center justify-center ${index < statusItems.length - 1 ? 'border-r border-[var(--color-border-2)]' : ''}`}
                >
                  <div
                    className="flex min-w-10.5 items-center justify-center gap-1.5 rounded-md px-1.5 py-0.5 transition-colors hover:bg-[var(--color-fill-1)]"
                    aria-label={`${label}：${value}`}
                  >
                    <div
                      className={`h-2 w-2 shrink-0 rounded-full ${dotClass} ring-2 ring-[var(--color-bg)]`}
                    />
                    <span className="text-sm font-semibold leading-none tabular-nums text-[var(--color-text-1)]">
                      {value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Tooltip>
      </div>
    );
  },
);

PluginCard.displayName = 'PluginCard';

export default PluginCard;
