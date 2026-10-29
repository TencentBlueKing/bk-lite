'use client';

import React, { useEffect } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import RelatedTopology from '@/app/ops-analysis/components/widgets/relatedTopology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { isSceneWidgetAllowedOnSurface } from '@/app/ops-analysis/types/sceneWidgetCapability';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { relatedTopologyCanvasStyle } from './visual';

interface RelatedTopologyCanvasProps {
  config?: ValueConfig;
  surface?: OpsAnalysisWidgetSurface;
  onReady?: (ready?: boolean) => void;
  scenePermissionDenied?: boolean;
}

const RelatedTopologyCanvas = ({
  config,
  surface = 'dashboard',
  onReady,
  scenePermissionDenied = false,
}: RelatedTopologyCanvasProps) => {
  const { t } = useTranslation();
  const instUuid = config?.relatedTopology?.instUuid?.trim() || '';
  const allowed = isSceneWidgetAllowedOnSurface('relatedTopology', surface);

  useEffect(() => {
    if (!allowed) return;
    onReady?.(Boolean(instUuid));
  }, [allowed, instUuid, onReady]);

  if (!allowed) {
    return null;
  }

  if (scenePermissionDenied) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center text-sm text-[var(--color-text-3)]"
        style={relatedTopologyCanvasStyle(
          isScreenChartThemeMode(config?.chartThemeMode),
        )}
      >
        {t('common.noAuth')}
      </div>
    );
  }

  if (!instUuid) {
    return (
      <div
        className="flex h-full min-h-[280px] items-center justify-center"
        style={relatedTopologyCanvasStyle(
          isScreenChartThemeMode(config?.chartThemeMode),
        )}
      >
        <CompactEmptyState
          description={t('dashboard.relatedTopologySelectAsset')}
        />
      </div>
    );
  }

  return <RelatedTopology instUuid={instUuid} chartThemeMode={config?.chartThemeMode} />;
};

export default RelatedTopologyCanvas;
