import React from 'react';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterValue,
  ScreenRenderContext,
  UnifiedFilterDefinition,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { CanvasRuntimeRefreshCause } from '@/app/ops-analysis/utils/canvasRefreshTimer';
import type { RuntimeRequestPriority } from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';
import { supportsComponentSwitch } from '@/app/ops-analysis/utils/componentParamSwitch';
import { getWidgetComponent } from './widgetRegistry';

interface WidgetRendererProps {
  chartType?: string;
  rawData: any;
  baselineData?: any;
  loading?: boolean;
  config?: ValueConfig;
  refreshKey?: string | number;
  refreshCause?: CanvasRuntimeRefreshCause;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready?: boolean) => void;
  onError?: (message: string) => void;
  onQueryChange?: (params: Record<string, any>) => void;
  layoutEditable?: boolean;
  onTopologyLayoutChange?: (
    next: NonNullable<ValueConfig['networkStatusTopology']>,
  ) => void;
  componentSwitchControl?: React.ReactNode;
  errorMessage?: string;
  runtimeOwnerId?: string;
  runtimeActive?: boolean;
  runtimePriority?: RuntimeRequestPriority;
  fallback?: React.ReactNode;
  surface?: OpsAnalysisWidgetSurface;
  onRawData?: (data: unknown) => void;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
  scenePermissionDenied?: boolean;
}

const WidgetRenderer: React.FC<WidgetRendererProps> = ({
  chartType,
  rawData,
  baselineData,
  loading = false,
  config,
  refreshKey,
  refreshCause,
  dataSource,
  screenRenderContext,
  onReady,
  onError,
  onQueryChange,
  layoutEditable,
  onTopologyLayoutChange,
  componentSwitchControl,
  errorMessage,
  runtimeOwnerId,
  runtimeActive,
  runtimePriority,
  fallback = null,
  surface = 'dashboard',
  onRawData,
  unifiedFilterValues,
  filterDefinitions,
  scenePermissionDenied,
}) => {
  const Component = getWidgetComponent(chartType, surface);
  if (!Component) {
    return <>{fallback}</>;
  }

  return (
    <Component
      rawData={rawData}
      baselineData={baselineData}
      loading={loading}
      config={config}
      refreshKey={refreshKey}
      refreshCause={refreshCause}
      dataSource={dataSource}
      screenRenderContext={screenRenderContext}
      surface={surface}
      onReady={onReady}
      onError={onError}
      onQueryChange={onQueryChange}
      layoutEditable={layoutEditable}
      editMode={layoutEditable}
      onTopologyLayoutChange={onTopologyLayoutChange}
      runtimeOwnerId={runtimeOwnerId}
      runtimeActive={runtimeActive}
      runtimePriority={runtimePriority}
      onRawData={onRawData}
      {...(chartType === 'room3D' || chartType === 'applicationTopology'
        ? { unifiedFilterValues, filterDefinitions }
        : {})}
      {...(scenePermissionDenied ? { scenePermissionDenied } : {})}
      {...(supportsComponentSwitch(chartType) ? { componentSwitchControl, errorMessage } : {})}
    />
  );
};

export default WidgetRenderer;
