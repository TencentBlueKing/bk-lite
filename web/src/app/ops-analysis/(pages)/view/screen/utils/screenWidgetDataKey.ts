import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

/** 大屏数据表单的重开键。样式页改外观或单值样式时，数据表单保持不动。 */
export const screenWidgetDataKey = (item: ScreenWidgetItem) => {
  const { appearance, singleStyle, ...dataConfig } = item.valueConfig ?? {};
  void appearance;
  void singleStyle;
  return JSON.stringify({
    id: item.id,
    title: item.title,
    chartType: item.chartType,
    dataConfig,
  });
};
