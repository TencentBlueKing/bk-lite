import { canShowCrossModulePublicWidget } from '@/context/appCapabilities/crossModuleEmbed';

export function canShowIncidentAssetChangeTab(input: {
  hasOpsAnalysis: boolean;
  declared: boolean;
  instUuids: readonly string[];
}): boolean {
  return (
    input.instUuids.length > 0 &&
    canShowCrossModulePublicWidget({
      hostApp: 'alarm',
      widgetKey: 'cmdb.assetChange',
      hasOpsAnalysis: input.hasOpsAnalysis,
      providerDeclared: input.declared,
    })
  );
}

export function resolveIncidentSelectedAssetUuid(
  instUuids: readonly string[],
  selectedUuid: string,
): string {
  if (instUuids.includes(selectedUuid)) {
    return selectedUuid;
  }
  return instUuids[0] || '';
}
