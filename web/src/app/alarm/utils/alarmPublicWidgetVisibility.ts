import { canShowCrossModulePublicWidget } from '@/context/appCapabilities/crossModuleEmbed';

export function resolveAlarmPublicWidgetVisibility(input: {
  hasOpsAnalysis: boolean;
  alertRawLogDeclared: boolean;
  monitorViewDeclared: boolean;
  relatedTopologyDeclared: boolean;
  assetInfoDeclared: boolean;
  assetChangeDeclared: boolean;
  nodeStatusDeclared: boolean;
  serviceOverviewDeclared: boolean;
  callChainDeclared: boolean;
  hasLogAlertId: boolean;
  hasMonitorId: boolean;
  hasInstUuid: boolean;
  hasNodeId: boolean;
  hasServiceId: boolean;
}): {
  alertRawLog: boolean;
  monitorView: boolean;
  relatedTopology: boolean;
  assetInfo: boolean;
  assetChange: boolean;
  nodeStatus: boolean;
  serviceOverview: boolean;
  callChain: boolean;
} {
  const canShow = (
    widgetKey:
      | 'log.alertRawLog'
      | 'monitor.monitorView'
      | 'ops-analysis.relatedTopology'
      | 'cmdb.baseInfo'
      | 'cmdb.assetChange'
      | 'node.nodeStatus'
      | 'apm.serviceOverview'
      | 'apm.callChain',
    declared: boolean,
  ) =>
    canShowCrossModulePublicWidget({
      hostApp: 'alarm',
      widgetKey,
      hasOpsAnalysis: input.hasOpsAnalysis,
      providerDeclared: declared,
    });

  return {
    alertRawLog: canShow('log.alertRawLog', input.alertRawLogDeclared) && input.hasLogAlertId,
    monitorView:
      canShow('monitor.monitorView', input.monitorViewDeclared) && input.hasMonitorId,
    relatedTopology:
      canShow('ops-analysis.relatedTopology', input.relatedTopologyDeclared) &&
      input.hasInstUuid,
    assetInfo: canShow('cmdb.baseInfo', input.assetInfoDeclared) && input.hasInstUuid,
    assetChange: canShow('cmdb.assetChange', input.assetChangeDeclared) && input.hasInstUuid,
    nodeStatus: canShow('node.nodeStatus', input.nodeStatusDeclared) && input.hasNodeId,
    serviceOverview:
      canShow('apm.serviceOverview', input.serviceOverviewDeclared) && input.hasServiceId,
    callChain: canShow('apm.callChain', input.callChainDeclared) && input.hasServiceId,
  };
}
