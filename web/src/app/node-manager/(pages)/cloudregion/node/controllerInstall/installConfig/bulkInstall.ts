export const BULK_INSTALL_METHOD = 'bulkInstall';
export const BULK_DEFAULT_EXPIRE_HOURS = 24;
export const BULK_MAX_EXPIRE_HOURS = 168;
export const BULK_MIN_SUCCESS_COUNT = 1;
export const BULK_MAX_SUCCESS_COUNT = 100000;

const ATTEMPT_LABEL_KEYS: Record<string, string> = {
  installing: 'node-manager.cloudregion.node.bulkAttemptInstalling',
  installed: 'node-manager.cloudregion.node.bulkAttemptInstalled',
  duplicate: 'node-manager.cloudregion.node.bulkAttemptDuplicate',
  failed: 'node-manager.cloudregion.node.bulkAttemptFailed',
  timeout: 'node-manager.cloudregion.node.bulkAttemptTimeout'
};

const BATCH_LABEL_KEYS: Record<string, string> = {
  active: 'node-manager.cloudregion.node.bulkStatusActive',
  expired: 'node-manager.cloudregion.node.bulkStatusExpired',
  revoked: 'node-manager.cloudregion.node.bulkStatusRevoked',
  disabled: 'node-manager.cloudregion.node.bulkStatusDisabled'
};

export function bulkCommandIncludesNodeIp(command: string): boolean {
  return command.includes('--node_ip');
}

export function installWaysForOs<T extends { value: string }>(
  ways: T[],
  os: string,
  bulkWay: T
): T[] {
  const base = ways.filter((item) => item.value !== bulkWay.value);
  if (os === 'linux') {
    return [...base, bulkWay];
  }
  return base;
}

export function bulkAttemptStatusLabelKey(status: string): string {
  return ATTEMPT_LABEL_KEYS[status] || ATTEMPT_LABEL_KEYS.failed;
}

export function bulkBatchStatusLabelKey(status: string): string {
  return BATCH_LABEL_KEYS[status] || BATCH_LABEL_KEYS.active;
}

export function dedupeControllerPackages<T>(packages: T[], byVersion: boolean): T[] {
  const deduped = new Map<string, T>();
  packages.forEach((item) => {
    const row = item as {
      version?: string;
      os?: string;
      cpu_architecture?: string;
    };
    const version = String(row.version ?? '');
    const key = byVersion
      ? version
      : `${row.os}-${row.cpu_architecture}-${version}`;
    if (!deduped.has(key)) {
      deduped.set(key, item);
    }
  });
  return Array.from(deduped.values());
}
