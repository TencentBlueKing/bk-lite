export { hasAppAccess, listAuthorizedCapabilityApps } from './access';
export { canShowCrossModulePublicWidget } from './crossModuleEmbed';
export { default as AppSlot } from './AppSlot';
export {
  APP_CAPABILITY_LOADERS,
  APP_CAPABILITY_NAMES,
  type AppCapabilityApi,
  type AppCapabilityName,
} from './catalog';
export { loadAuthorizedCapability, resetAppCapabilityCache } from './load';
export { loadAuthorizedCapabilityModules } from './loadAuthorizedModules';
export {
  collectSlotContributions,
  isHostTab,
  resolveSlot,
} from './slots';
export type {
  AppCapabilityModule,
  AppCapabilityState,
  AppCapabilityStatus,
  AppSlotContribution,
} from './types';
export { useAppCapability } from './useAppCapability';
export { useAppWidget, type AppWidgetState } from './useAppWidget';
export { useLazyAppWidget } from './useLazyAppWidget';
export { useAppSlotTabs, type AppSlotTabItem } from './useAppSlotTabs';
export {
  APP_WIDGET_KEYS,
  appNameForWidgetKey,
  resolveWidgetLoader,
  type AppWidgetKey,
  type AppWidgetLoader,
} from './widgets';
