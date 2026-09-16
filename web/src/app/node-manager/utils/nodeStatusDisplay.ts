export const COLLECTOR_STATUS_I18N: Record<string, string> = {
  '0': 'node-manager.cloudregion.node.normal',
  '1': 'node-manager.cloudregion.node.unknown',
  '2': 'node-manager.cloudregion.node.error',
  '3': 'node-manager.cloudregion.node.stopped',
  '4': 'node-manager.cloudregion.node.notStarted',
  '10': 'node-manager.cloudregion.node.installing',
  '11': 'node-manager.cloudregion.node.notStarted',
  '12': 'node-manager.cloudregion.node.failInstall',
};

export function nodeOnlineI18nKey(active: boolean | undefined | null): string | null {
  if (typeof active !== 'boolean') return null;
  return active
    ? 'node-manager.cloudregion.node.online'
    : 'node-manager.cloudregion.node.offline';
}

export function collectorStatusI18nKey(status: string | number | undefined | null): string {
  if (status == null || status === '') {
    return 'node-manager.cloudregion.node.unknown';
  }
  return COLLECTOR_STATUS_I18N[String(status)] || 'node-manager.cloudregion.node.unknown';
}
