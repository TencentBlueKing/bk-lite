import type { ClientData } from '@/types';

export type ModulePushTarget = 'cmdb' | 'monitor';

export type ModulePushState =
  | 'ok'
  | 'skipped'
  | 'pending'
  | 'conflict'
  | 'failed'
  | string;

export interface ModulePushStatusEntry {
  state?: ModulePushState;
  error?: string | null;
  attempts?: number;
}

export type ModulePushStatusMap = Partial<
  Record<ModulePushTarget, ModulePushStatusEntry>
>;

/**
 * 按已售/已授权应用裁剪推送目标。
 * clientData 为空时无法判断售卖矩阵，默认展示两侧（与规格 DONE_WITH_CONCERNS 一致）。
 */
export const getSoldModulePushTargets = (
  clientData: ClientData[] | undefined | null
): ModulePushTarget[] => {
  if (!clientData?.length) {
    return ['cmdb', 'monitor'];
  }
  const names = new Set(clientData.map((item) => item.name));
  const targets: ModulePushTarget[] = [];
  if (names.has('cmdb')) targets.push('cmdb');
  if (names.has('monitor')) targets.push('monitor');
  return targets;
};

export const getPushStatusState = (
  pushStatus: ModulePushStatusMap | undefined | null,
  target: ModulePushTarget
): ModulePushState | undefined => {
  const entry = pushStatus?.[target];
  return entry?.state;
};

/** 已成功关联或状态为 ok 时展示「重新同步」，否则「推送」 */
export const hasSuccessfulModuleLink = (
  linkedId: string | undefined | null,
  pushStatus: ModulePushStatusMap | undefined | null,
  target: ModulePushTarget
): boolean => {
  if (String(linkedId || '').trim()) return true;
  return getPushStatusState(pushStatus, target) === 'ok';
};
