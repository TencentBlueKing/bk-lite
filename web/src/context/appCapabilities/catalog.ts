export const APP_CAPABILITY_LOADERS = {
  alarm: () => import('@/app/alarm/capability'),
} as const;

export type AppCapabilityName = keyof typeof APP_CAPABILITY_LOADERS;

export type AppCapabilityApi<K extends AppCapabilityName> = Awaited<
  ReturnType<(typeof APP_CAPABILITY_LOADERS)[K]>
>;

export const APP_CAPABILITY_NAMES = Object.keys(
  APP_CAPABILITY_LOADERS
) as AppCapabilityName[];
