'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import type { ModelItem } from '@/app/cmdb/types/assetManage';

interface ViewSummaryModel {
  model_id: string;
  count: number;
}

interface ViewSummaryProps {
  total: number;
  models: ViewSummaryModel[];
  modelNameById: Map<string, ModelItem>;
  onJump: (modelId: string) => void;
}

const ViewSummary: React.FC<ViewSummaryProps> = ({
  total,
  models,
  modelNameById,
  onJump,
}) => {
  const { t } = useTranslation();
  const safeTotal = total || 1;

  return (
    <div className="mb-5 rounded-2xl bg-[var(--color-fill-1)] p-2">
      <div className="flex flex-wrap items-stretch gap-4 rounded-xl bg-[var(--color-bg-1)] px-4 py-3">
        <div className="min-w-[7rem]">
          <div className="text-xs text-[var(--color-text-3)]">
            {t('SceneView.matchInstances')}
          </div>
          <div className="mt-1 text-[28px] font-semibold leading-none tracking-tight tabular-nums text-[var(--color-text-1)]">
            {total}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex h-1.5 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
            {models.map((item, index) => (
              <div
                key={item.model_id}
                className="h-full bg-[var(--color-primary)]"
                style={{
                  width: `${(item.count / safeTotal) * 100}%`,
                  opacity: Math.max(0.35, 1 - index * 0.22),
                }}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {models.map((item) => (
              <button
                key={item.model_id}
                type="button"
                className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-fill-1)] px-2.5 py-1.5 text-left hover:bg-[var(--color-fill-2)] focus-visible:outline focus-visible:outline-offset-2"
                onClick={() => onJump(item.model_id)}
              >
                <span className="max-w-[10rem] truncate text-xs text-[var(--color-text-3)]">
                  {modelNameById.get(item.model_id)?.model_name || item.model_id}
                </span>
                <span className="text-sm font-medium tabular-nums text-[var(--color-text-1)]">
                  {item.count}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ViewSummary;
