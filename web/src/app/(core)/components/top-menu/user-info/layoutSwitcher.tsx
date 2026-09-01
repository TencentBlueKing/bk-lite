'use client';

import React from 'react';
import { RightOutlined } from '@ant-design/icons';
import { useConsoleLayout } from '@/console-layout';
import type { ConsoleChromeLayout } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';

const LayoutPreview = ({ variant }: { variant: ConsoleChromeLayout }) => {
  if (variant === 'classic') {
    return (
      <div className="h-14 overflow-hidden rounded-sm border border-[var(--color-border-2)] bg-[var(--color-bg-1)]">
        <div className="flex h-3.5 items-center gap-1 border-b border-[var(--color-border-2)] px-1">
          <span className="h-2 w-2 shrink-0 rounded-sm bg-[var(--color-fill-3)]" />
          <span className="h-1.5 w-3 rounded-sm bg-[var(--color-fill-3)]" />
        </div>
        <div className="flex h-3 items-center justify-center gap-1 px-2">
          <span className="h-1 w-4 rounded-sm bg-[var(--color-primary)]" />
          <span className="h-1 w-4 rounded-sm bg-[var(--color-fill-3)]" />
          <span className="h-1 w-4 rounded-sm bg-[var(--color-fill-3)]" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-14 overflow-hidden rounded-sm border border-[var(--color-border-2)] bg-[var(--color-bg-1)]">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-3.5 items-center gap-1 border-b border-[var(--color-border-2)] px-1">
          <span className="h-1 w-4 rounded-sm bg-[var(--color-primary)]" />
          <span className="h-1 w-3 rounded-sm bg-[var(--color-fill-3)]" />
          <span className="h-1 w-3 rounded-sm bg-[var(--color-fill-3)]" />
        </div>
        <div className="flex min-h-0 flex-1">
          <span className="w-3 border-r border-[var(--color-border-2)] bg-[var(--color-fill-1)]" />
          <span className="flex-1" />
        </div>
      </div>
    </div>
  );
};

interface LayoutSwitcherRowProps {
  onToggle?: () => void;
}

const LayoutSwitcher = ({ onToggle }: LayoutSwitcherRowProps) => {
  const { t } = useTranslation();
  const { layout } = useConsoleLayout();

  return (
    <div
      data-testid="layout-switcher-row"
      className="flex w-full items-center justify-between"
      onClick={(event) => {
        event.stopPropagation();
        onToggle?.();
      }}
    >
      <span>{t('common.layout')}</span>
      <span className="flex min-w-0 items-center gap-1 text-xs text-[var(--color-text-4)]">
        <span className="max-w-[120px] truncate">
          {layout === 'classic' ? t('common.layoutClassic') : t('common.layoutAppTop')}
        </span>
        <RightOutlined className="text-[10px]" />
      </span>
    </div>
  );
};

interface LayoutSwitcherPanelProps {
  onApplied?: () => void;
}

export const LayoutSwitcherPanel = ({ onApplied }: LayoutSwitcherPanelProps) => {
  const { t } = useTranslation();
  const { layout, setLayout } = useConsoleLayout();

  const apply = (next: ConsoleChromeLayout) => {
    setLayout(next);
    onApplied?.();
  };

  return (
    <div
      data-testid="layout-switcher-panel"
      className="w-[248px] p-2"
      onClick={(event) => event.stopPropagation()}
    >
      <div className="grid grid-cols-2 gap-2">
        {(['classic', 'app-top'] as const).map((option) => {
          const selected = layout === option;
          return (
            <button
              key={option}
              type="button"
              className={`rounded-md p-1.5 text-left transition-colors ${
                selected
                  ? 'bg-[var(--color-fill-2)] ring-1 ring-[var(--color-primary)]'
                  : 'hover:bg-[var(--color-fill-1)]'
              }`}
              onClick={() => apply(option)}
            >
              <LayoutPreview variant={option} />
              <div className="mt-1.5 text-xs font-medium text-[var(--color-text-1)]">
                {option === 'classic' ? t('common.layoutClassic') : t('common.layoutAppTop')}
              </div>
              <div className="mt-0.5 text-[10px] leading-snug text-[var(--color-text-3)]">
                {option === 'classic' ? t('common.layoutClassicHint') : t('common.layoutAppTopHint')}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export const getLayoutPanelPosition = (item: HTMLElement) => {
  const menu = item.closest('.ant-dropdown') as HTMLElement | null;
  const menuRect = (menu ?? item).getBoundingClientRect();
  const itemRect = item.getBoundingClientRect();
  return {
    top: Math.max(8, itemRect.top),
    right: Math.max(8, window.innerWidth - menuRect.left + 8),
  };
};

export default LayoutSwitcher;
