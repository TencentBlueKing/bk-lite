import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { isSceneWidgetType } from '@/app/ops-analysis/types/sceneWidgetCapability';

export const buildScreenWidgetConfig = (
  item: ScreenWidgetItem,
  chartThemeMode: OpsChartThemeMode,
): ValueConfig => ({
  ...item.valueConfig,
  chartType: item.chartType,
  chartThemeMode,
  ...(isSceneWidgetType(item.chartType)
    ? { sceneWidgetType: item.chartType }
    : {}),
});
