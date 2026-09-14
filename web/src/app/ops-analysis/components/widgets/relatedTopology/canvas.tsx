'use client';

import React, { useEffect } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import RelatedTopology from '@/app/ops-analysis/components/widgets/relatedTopology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import {
  getSceneWidgetCapability,
  isSceneWidgetAllowedOnSurface,
} from '@/app/ops-analysis/types/sceneWidgetCapability';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { relatedTopologyCanvasStyle } from './visual';

interface RelatedTopologyCanvasProps {
  config?: ValueConfig;
  surface?: OpsAnalysisWidgetSurface;
  onReady?: (ready?: boolean) => void;
}

const RelatedTopologyCanvas = ({
  config,
  surface = 'dashboard',
  onReady,
}: RelatedTopologyCanvasProps) => {
  const { t } = useTranslation();
  const shareMode = useShareMode();
  const instUuid = config?.relatedTopology?.instUuid?.trim() || '';
  const allowed =
    isSceneWidgetAllowedOnSurface('relatedTopology', surface) &&
    (!shareMode ||
      getSceneWidgetCapability('relatedTopology')?.shareSupported === true);

  useEffect(() => {
    if (!allowed) return;
    onReady?.(Boolean(instUuid));
  }, [allowed, instUuid, onReady]);

  if (!allowed) {
    return null;
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
