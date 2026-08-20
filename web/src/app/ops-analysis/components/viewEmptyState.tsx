'use client';

import React from 'react';
import { Button } from 'antd';
import PermissionWrapper from '@/components/permission';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import {
  getRecentViewedLabel,
  type RecentCanvasRecord,
} from '@/app/ops-analysis/utils/recentCanvasStorage';

interface ViewEmptyStateProps {
  recents: RecentCanvasRecord[];
  onCreateCanvas: () => void;
  onOpenRecent: (item: RecentCanvasRecord) => void;
}

const CANVAS_EMPTY_IMAGE = '/assets/ops-analysis/canvas-empty.png';
const CANVAS_CARD_PREVIEW_IMAGE = '/assets/ops-analysis/canvas-card-preview.png';

const CanvasIllustration: React.FC<{ className?: string }> = ({
  className = 'h-auto w-full max-w-[220px]',
}) => (
  <img
    aria-hidden="true"
    alt=""
    className={className}
    draggable={false}
    src={CANVAS_EMPTY_IMAGE}
  />
);

const RecentCanvasPreview: React.FC = () => (
  <img
    aria-hidden="true"
    alt=""
    className="h-[72px] w-auto rounded-lg object-contain"
    draggable={false}
    src={CANVAS_CARD_PREVIEW_IMAGE}
  />
);

const ViewEmptyState: React.FC<ViewEmptyStateProps> = ({
  recents,
  onCreateCanvas,
  onOpenRecent,
}) => {
  const { t } = useTranslation();
  const now = Date.now();
  const shouldShowRecents = recents.length >= 2;

  return (
    <div className="flex min-h-0 w-full flex-1 items-center justify-center bg-[var(--color-bg-1)] px-4 py-10 sm:px-6">
      <div className="flex w-full max-w-[680px] flex-col items-center">
        <div
          className="flex w-full max-w-[420px] flex-col items-center text-center"
          role="status"
        >
          <CanvasIllustration className="h-auto w-full max-w-[220px]" />
          <h2 className="mb-0 mt-3 text-[18px] font-semibold leading-7 text-[var(--color-text-1)]">
            {t('opsAnalysisSidebar.selectItem')}
          </h2>
          <p className="mb-0 mt-2 text-sm leading-6 text-[var(--color-text-3)]">
            {t('opsAnalysisSidebar.selectItemHint')}
          </p>
          <PermissionWrapper requiredPermissions={['AddChart']} className="mt-3">
            <Button type="primary" onClick={onCreateCanvas}>
              {t('opsAnalysisSidebar.newCanvas')}
            </Button>
          </PermissionWrapper>
        </div>

        {shouldShowRecents && (
          <section className="mt-8 flex w-full justify-center">
            <div>
              <h3 className="mb-3 text-[13px] font-medium leading-5 text-[var(--color-text-2)]">
                {t('opsAnalysisSidebar.recentVisited')}
              </h3>
              <div className="flex gap-5">
              {recents.map((item) => {
                const label = getRecentViewedLabel(item.viewedAt, now);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onOpenRecent(item)}
                    className="w-[220px] shrink-0 cursor-pointer overflow-hidden rounded-xl border border-[var(--color-border-2)] bg-[var(--color-bg)] text-left transition-colors duration-150 hover:border-[var(--color-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
                  >
                    <div className="flex justify-center px-1 pt-2 pb-2">
                      <div className="flex w-fit min-w-0 flex-col">
                        <RecentCanvasPreview />
                        <div className="pt-2">
                          <EllipsisWithTooltip
                            className="min-w-0 truncate text-sm font-medium text-[var(--color-text-1)]"
                            text={item.name}
                          />
                          <p className="mb-0 mt-1 text-xs leading-4 text-[var(--color-text-4)]">
                            {'count' in label
                              ? t(label.key, undefined, { count: label.count })
                              : t(label.key)}
                          </p>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default ViewEmptyState;
