'use client';

import React, { useEffect } from 'react';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import ApplicationTopology from '@/app/ops-analysis/components/widgets/applicationTopology';
import type {
  FilterValue,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { resolveApplicationTopologyCanvasSelection } from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { isSceneWidgetAllowedOnSurface } from '@/app/ops-analysis/types/sceneWidgetCapability';
import {
  APPLICATION_TOPOLOGY_DEFAULT_DEPTH,
  APPLICATION_TOPOLOGY_MAX_DEPTH,
} from '@/app/ops-analysis/types/sceneWidget';
import { isScreenChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import { applicationTopologySurfaceStyle } from '@/app/ops-analysis/components/widgets/applicationTopology/graphView';

interface ApplicationTopologyCanvasProps {
  config?: ValueConfig;
  surface?: OpsAnalysisWidgetSurface;
  onReady?: (ready?: boolean) => void;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
}

const clampDepth = (value: unknown) => {
  const depth = Number(value);
  if (!Number.isInteger(depth) || depth < 1 || depth > APPLICATION_TOPOLOGY_MAX_DEPTH) {
    return APPLICATION_TOPOLOGY_DEFAULT_DEPTH;
  }
  return depth;
};

const ApplicationTopologyCanvas = ({
  config,
  surface = 'dashboard',
  onReady,
  unifiedFilterValues,
  filterDefinitions,
}: ApplicationTopologyCanvasProps) => {
  const { t } = useTranslation();
  const instUuid = resolveApplicationTopologyCanvasSelection({
    filterDefinitions,
    unifiedFilterValues,
    fallbackInstUuid: config?.applicationTopology?.instUuid,
  });
  const depth = clampDepth(config?.applicationTopology?.depth);
  const allowed = isSceneWidgetAllowedOnSurface('applicationTopology', surface);
  const usesScreenTheme = isScreenChartThemeMode(config?.chartThemeMode);

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
        style={applicationTopologySurfaceStyle(usesScreenTheme)}
      >
        <CompactEmptyState description={t('dashboard.applicationTopologySelectAsset')} />
      </div>
    );
  }

  return (
    <ApplicationTopology
      instUuid={instUuid}
      depth={depth}
      chartThemeMode={config?.chartThemeMode}
    />
  );
};

export default ApplicationTopologyCanvas;
