import { buildCollectNeedUpdateAssetUrl } from '@/app/monitor/utils/collectNeedUpdate';

/** 超过 1 个待更新对象时不再铺页脚按钮，改为集成列表入口。 */
export const IMPORT_STALE_DIRECT_TARGET_LIMIT = 1;
/** 提示里最多点名 3 个对象，再多只说数量。 */
export const IMPORT_STALE_NAMED_HINT_LIMIT = 3;
export const IMPORT_STALE_LIST_PATH = '/monitor/integration/list';

const PROGRAM_CHANGE_ACTIONS = new Set(['created', 'overwritten']);

export interface ImportStaleApplied {
  ok?: boolean;
  monitor_object_id?: string | number | null;
  plugin_id?: string | number | null;
  stale_instance_count?: number;
  collector?: string;
  version?: string;
  artifacts?: Array<{ os?: string; arch?: string; action?: string }> | null;
}

export interface StaleAssetTarget {
  key: string;
  monitorObjectId: string;
  pluginId?: string | number | null;
  staleCount: number;
  label: string;
}

export const listStaleAssetTargets = (
  items: Array<{ applied?: ImportStaleApplied | null }>
): StaleAssetTarget[] => {
  const seen = new Set<string>();
  const targets: StaleAssetTarget[] = [];
  for (const item of items || []) {
    const applied = item.applied;
    if (!applied?.ok || !(Number(applied.stale_instance_count) > 0)) continue;
    if (applied.monitor_object_id == null || String(applied.monitor_object_id).trim() === '') {
      continue;
    }
    const objectId = String(applied.monitor_object_id);
    const pluginId =
      applied.plugin_id != null && String(applied.plugin_id).trim() !== ''
        ? applied.plugin_id
        : null;
    const key = `${objectId}:${pluginId ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    targets.push({
      key,
      monitorObjectId: objectId,
      pluginId,
      staleCount: Number(applied.stale_instance_count) || 0,
      label: [applied.collector, applied.version].filter(Boolean).join(' ') || objectId
    });
  }
  return targets;
};

export const resolveImportStaleAction = (targets: StaleAssetTarget[]) => {
  const single = targets.length <= IMPORT_STALE_DIRECT_TARGET_LIMIT ? targets[0] : undefined;
  if (single) {
    return {
      href: buildCollectNeedUpdateAssetUrl({
        monitorObjectId: single.monitorObjectId,
        pluginId: single.pluginId,
        needUpdate: true
      }),
      buttonKey: 'goToStaleAssets' as const,
      many: false
    };
  }
  return {
    href: IMPORT_STALE_LIST_PATH,
    buttonKey: 'goToStaleList' as const,
    many: true
  };
};

export const hasCollectorProgramChange = (
  items: Array<{ applied?: ImportStaleApplied | null }>
): boolean =>
  (items || []).some((item) => {
    if (!item.applied?.ok) return false;
    return (item.applied.artifacts || []).some((artifact) =>
      PROGRAM_CHANGE_ACTIONS.has(String(artifact.action || '').toLowerCase())
    );
  });
