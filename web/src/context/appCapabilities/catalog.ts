export const APP_CAPABILITY_LOADERS = {
  alarm: () => import('@/app/alarm/capability'),
  cmdb: () => import('@/app/cmdb/capability'),
  monitor: () => import('@/app/monitor/capability'),
  'ops-analysis': () => import('@/app/ops-analysis/capability'),
  log: () => import('@/app/log/capability'),
  node: () => import('@/app/node-manager/capability'),
  apm: () => import('@/app/apm/capability'),
} as const;

export type AppCapabilityName = keyof typeof APP_CAPABILITY_LOADERS;

export type AppCapabilityApi<K extends AppCapabilityName> = Awaited<
  ReturnType<(typeof APP_CAPABILITY_LOADERS)[K]>
>;

export const APP_CAPABILITY_NAMES = Object.keys(
  APP_CAPABILITY_LOADERS
) as AppCapabilityName[];
