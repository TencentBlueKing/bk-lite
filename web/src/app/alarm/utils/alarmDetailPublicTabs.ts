export interface AlarmDetailTabItem {
  key: string;
  label: string;
}

export function buildAlarmDetailPublicTabs(
  t: (id: string) => string,
  options: {
    includeActionRecords: boolean;
    monitorView: boolean;
    relatedTopology: boolean;
    assetInfo: boolean;
  },
): AlarmDetailTabItem[] {
  const tabs: AlarmDetailTabItem[] = [
    { key: 'baseInfo', label: t('alarms.summary') },
    { key: 'event', label: t('alarms.event') },
  ];
  if (options.monitorView) {
    tabs.push({ key: 'monitorView', label: t('alarms.monitorView') });
  }
  if (options.relatedTopology) {
    tabs.push({ key: 'relatedTopology', label: t('alarms.relatedTopology') });
  }
  if (options.assetInfo) {
    tabs.push({ key: 'assetInfo', label: t('alarms.assetInfo') });
  }
  tabs.push({ key: 'timeline', label: t('alarms.changes') });
  if (options.includeActionRecords) {
    tabs.push({ key: 'actionRecords', label: t('settings.actionTab') });
  }
  return tabs;
}
