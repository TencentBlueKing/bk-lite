// 公开入口只看「提供方声明了这个键」+「有约定稳定 ID」。提供方未购 / 无模块级访问时
// 目录探测不到该键，declared 即为 false，所以这里不再额外判断售卖。
export function resolveAlarmPublicWidgetVisibility(input: {
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
  return {
    alertRawLog: input.alertRawLogDeclared && input.hasLogAlertId,
    monitorView: input.monitorViewDeclared && input.hasMonitorId,
    relatedTopology: input.relatedTopologyDeclared && input.hasInstUuid,
    assetInfo: input.assetInfoDeclared && input.hasInstUuid,
    assetChange: input.assetChangeDeclared && input.hasInstUuid,
    nodeStatus: input.nodeStatusDeclared && input.hasNodeId,
    serviceOverview: input.serviceOverviewDeclared && input.hasServiceId,
    callChain: input.callChainDeclared && input.hasServiceId,
  };
}
