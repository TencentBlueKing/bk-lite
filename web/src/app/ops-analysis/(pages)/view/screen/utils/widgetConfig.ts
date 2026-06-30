import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

export const buildScreenWidgetConfig = (
  item: ScreenWidgetItem,
): ValueConfig => ({
  ...item.config,
  chartType: item.chartType,
  chartThemeMode: 'screen-dark',
  ...(item.chartType === 'networkStatusTopology'
    ? { sceneWidgetType: 'networkStatusTopology' as const }
    : {}),
});
