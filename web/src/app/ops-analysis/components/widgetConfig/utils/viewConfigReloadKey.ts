import type { ViewConfigItem } from '@/app/ops-analysis/types/dashBoard';

/** 数据表单只在数据配置变化时重开。外观和单值样式走各自的即时写入。 */
export const viewConfigReloadKey = (item: ViewConfigItem | null | undefined) => {
  if (!item) return '';
  const id = 'i' in item && item.i ? String(item.i) : 'id' in item && item.id ? String(item.id) : '';
  const name = 'name' in item ? item.name ?? '' : '';
  const valueConfig = item.valueConfig;
  if (!valueConfig) {
    return JSON.stringify({ id, name });
  }
  const { appearance, singleStyle, ...dataConfig } = valueConfig;
  void appearance;
  void singleStyle;
  return JSON.stringify({ id, name, dataConfig });
};
