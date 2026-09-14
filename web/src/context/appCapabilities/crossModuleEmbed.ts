import type { AppCapabilityName } from './catalog';
import { appNameForWidgetKey, type AppWidgetKey } from './widgets';

export function canShowCrossModulePublicWidget(input: {
  hostApp: AppCapabilityName;
  widgetKey: AppWidgetKey;
  hasOpsAnalysis: boolean;
  providerDeclared: boolean;
}): boolean {
  if (!input.providerDeclared) {
    return false;
  }
  const provider = appNameForWidgetKey(input.widgetKey);
  if (provider === input.hostApp) {
    return true;
  }
  return input.hasOpsAnalysis;
}
