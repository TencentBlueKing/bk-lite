import { MODULE_OBJECT_QUERY_PARAM } from '@/app/monitor/utils/monitorObjectQuery';

const ASSET_PATH = '/monitor/integration/asset';

/** 跳到接入资产页，定位对象/插件，并默认打开「可升级」过滤。 */
export const buildCollectNeedUpdateAssetUrl = (options?: {
  monitorObjectId?: number | string | null;
  pluginId?: number | string | null;
  needUpdate?: boolean;
}): string => {
  const params = new URLSearchParams();
  const objectId = options?.monitorObjectId;
  if (objectId != null && String(objectId).trim() !== '') {
    params.set(MODULE_OBJECT_QUERY_PARAM, String(objectId));
  }
  const pluginId = options?.pluginId;
  if (pluginId != null && String(pluginId).trim() !== '') {
    params.set('monitor_plugin_id', String(pluginId));
  }
  if (options?.needUpdate !== false) {
    params.set('need_update', '1');
  }
  const query = params.toString();
  return query ? `${ASSET_PATH}?${query}` : ASSET_PATH;
};

/** 粗粒度版本比较：current < target 为升级；> 为降级；相等或无法解析为对齐。 */
export const comparePackVersions = (
  current?: string | null,
  target?: string | null
): 'upgrade' | 'downgrade' | 'align' => {
  const parse = (value?: string | null): number[] | null => {
    const raw = String(value || '')
      .trim()
      .replace(/^[vV]/, '');
    if (!raw) return null;
    const parts = raw.split('.').slice(0, 3).map((part) => {
      const matched = part.match(/^\d+/);
      return matched ? Number(matched[0]) : NaN;
    });
    if (parts.some((part) => Number.isNaN(part))) return null;
    while (parts.length < 3) parts.push(0);
    return parts;
  };
  const left = parse(current);
  const right = parse(target);
  if (!left || !right) return 'align';
  for (let index = 0; index < 3; index += 1) {
    if (left[index] < right[index]) return 'upgrade';
    if (left[index] > right[index]) return 'downgrade';
  }
  return 'align';
};
