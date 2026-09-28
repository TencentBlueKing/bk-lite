import {
  BusinessMetricItem,
  cleanDisplayTags,
  isSelfMetricName
} from './scriptMetricsParser';
import { resolveCatalogUnitId } from './scriptMetricPersist';

const getSessionStorage = (): {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
} | null => {
  try {
    if (typeof sessionStorage === 'undefined') {
      return null;
    }
    return sessionStorage;
  } catch {
    return null;
  }
};

export const SCRIPT_METRIC_DRAFT_QUERY = 'script_metric_draft';
export const SCRIPT_METRIC_CARRY_STORAGE_KEY =
  'bk-lite.monitor.scriptMetricEditCarry';

export interface ScriptMetricEditCarryItem {
  name: string;
  sample: number | string;
  group?: number;
  unit_id?: string;
  description?: string;
  tags: Record<string, string>;
}

export interface ScriptMetricEditCarry {
  metrics: ScriptMetricEditCarryItem[];
}

const carryStorageKey = (
  objectId: string | number,
  pluginId: string | number
): string => `${SCRIPT_METRIC_CARRY_STORAGE_KEY}:${objectId}:${pluginId}`;

export const buildScriptMetricEditCarry = (
  metrics: BusinessMetricItem[]
): ScriptMetricEditCarry => {
  const items: ScriptMetricEditCarryItem[] = [];
  const seen = new Set<string>();
  metrics.forEach((item) => {
    const name = String(item?.name || '').trim();
    if (!name || seen.has(name) || isSelfMetricName(name)) {
      return;
    }
    seen.add(name);
    const tags = cleanDisplayTags(item.tags) || {};
    const unitId = resolveCatalogUnitId(item.unit);
    const group =
      typeof item.metric_group === 'number' && item.metric_group > 0
        ? item.metric_group
        : undefined;
    const description =
      typeof item.description === 'string' ? item.description : '';
    items.push({
      name,
      sample: item.value,
      ...(group ? { group } : {}),
      ...(unitId ? { unit_id: unitId } : {}),
      ...(description ? { description } : {}),
      tags
    });
  });
  return { metrics: items };
};

export const writeScriptMetricEditCarry = (
  objectId: string | number,
  pluginId: string | number,
  payload: ScriptMetricEditCarry
): void => {
  const storage = getSessionStorage();
  if (!storage) {
    return;
  }
  try {
    storage.setItem(carryStorageKey(objectId, pluginId), JSON.stringify(payload));
  } catch {
    // sessionStorage 可能被禁用或超额，忽略即可。
  }
};

export const consumeScriptMetricEditCarry = (
  objectId: string | number,
  pluginId: string | number
): ScriptMetricEditCarry | null => {
  const storage = getSessionStorage();
  if (!storage) {
    return null;
  }
  const key = carryStorageKey(objectId, pluginId);
  try {
    const raw = storage.getItem(key);
    storage.removeItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as ScriptMetricEditCarry;
    if (!parsed || !Array.isArray(parsed.metrics)) {
      return null;
    }
    return {
      metrics: parsed.metrics
        .filter((item) => item?.name && !isSelfMetricName(item.name))
        .map((item) => ({
          name: String(item.name).trim(),
          sample: item.sample,
          ...(typeof item.group === 'number' && item.group > 0
            ? { group: item.group }
            : {}),
          ...(item.unit_id ? { unit_id: String(item.unit_id) } : {}),
          ...(item.description ? { description: String(item.description) } : {}),
          tags: cleanDisplayTags(item.tags) || {}
        }))
    };
  } catch {
    try {
      storage.removeItem(key);
    } catch {
      // ignore
    }
    return null;
  }
};
