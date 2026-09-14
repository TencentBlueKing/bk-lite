import { canShowCrossModulePublicWidget } from '@/context/appCapabilities/crossModuleEmbed';

export function resolveAlarmPublicWidgetVisibility(input: {
  hasOpsAnalysis: boolean;
  monitorViewDeclared: boolean;
  relatedTopologyDeclared: boolean;
  assetInfoDeclared: boolean;
  hasMonitorId: boolean;
  hasInstUuid: boolean;
}): {
  monitorView: boolean;
  relatedTopology: boolean;
  assetInfo: boolean;
} {
  return {
    monitorView:
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'monitor.monitorView',
        hasOpsAnalysis: input.hasOpsAnalysis,
        providerDeclared: input.monitorViewDeclared,
      }) && input.hasMonitorId,
    relatedTopology:
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'ops-analysis.relatedTopology',
        hasOpsAnalysis: input.hasOpsAnalysis,
        providerDeclared: input.relatedTopologyDeclared,
      }) && input.hasInstUuid,
    assetInfo:
      canShowCrossModulePublicWidget({
        hostApp: 'alarm',
        widgetKey: 'cmdb.baseInfo',
        hasOpsAnalysis: input.hasOpsAnalysis,
        providerDeclared: input.assetInfoDeclared,
      }) && input.hasInstUuid,
  };
}
