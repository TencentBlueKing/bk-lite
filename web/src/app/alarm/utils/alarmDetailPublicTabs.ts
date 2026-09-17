export interface AlarmDetailTabItem {
  key: string;
  label: string;
}

export function buildAlarmDetailPublicTabs(
  t: (id: string) => string,
  options: {
    includeActionRecords: boolean;
    alertRawLog: boolean;
    monitorView: boolean;
    relatedTopology: boolean;
    assetInfo: boolean;
    assetChange: boolean;
    nodeStatus: boolean;
    serviceOverview: boolean;
    callChain: boolean;
  },
): AlarmDetailTabItem[] {
  const tabs: AlarmDetailTabItem[] = [
    { key: 'baseInfo', label: t('alarms.summary') },
    { key: 'event', label: t('alarms.event') },
  ];
  if (options.alertRawLog) {
    tabs.push({ key: 'alertRawLog', label: t('alarms.alertRawLog') });
  }
  if (options.monitorView) {
    tabs.push({ key: 'monitorView', label: t('alarms.monitorView') });
  }
  if (options.relatedTopology) {
    tabs.push({ key: 'relatedTopology', label: t('alarms.relatedTopology') });
  }
  if (options.assetInfo) {
    tabs.push({ key: 'assetInfo', label: t('alarms.assetInfo') });
  }
  if (options.assetChange) {
    tabs.push({ key: 'assetChange', label: t('alarms.assetChange') });
  }
  if (options.nodeStatus) {
    tabs.push({ key: 'nodeStatus', label: t('alarms.nodeStatus') });
  }
  if (options.serviceOverview) {
    tabs.push({ key: 'serviceOverview', label: t('alarms.serviceOverview') });
  }
  if (options.callChain) {
    tabs.push({ key: 'callChain', label: t('alarms.callChain') });
  }
  tabs.push({ key: 'timeline', label: t('alarms.changes') });
  if (options.includeActionRecords) {
    tabs.push({ key: 'actionRecords', label: t('settings.actionTab') });
  }
  return tabs;
}
