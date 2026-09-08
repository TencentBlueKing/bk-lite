import type { AppCapabilityModule, AppSlotContribution } from './types';

export interface LoadedCapabilitySlots {
  appName: string;
  slots?: AppCapabilityModule['slots'] | null;
}

export function collectSlotContributions(
  modules: Array<LoadedCapabilitySlots | null | undefined>,
  slotId: string
): Array<AppSlotContribution & { appName: string }> {
  const contributions: Array<AppSlotContribution & { appName: string }> = [];
  for (const mod of modules) {
    if (!mod?.appName) continue;
    const slot = mod.slots?.[slotId];
    if (!slot?.key || !slot.component) continue;
    contributions.push({ ...slot, appName: mod.appName });
  }
  return contributions;
}

export function resolveSlot(
  contributions: Array<AppSlotContribution & { appName: string }>,
  slotKey: string
): (AppSlotContribution & { appName: string }) | null {
  return contributions.find((item) => item.key === slotKey) ?? null;
}

export function isHostTab(tab: string, extraTabKeys: Iterable<string>): boolean {
  return !new Set(extraTabKeys).has(tab);
}
