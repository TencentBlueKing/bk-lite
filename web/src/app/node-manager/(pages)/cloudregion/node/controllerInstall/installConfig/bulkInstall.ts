export const BULK_INSTALL_METHOD = 'bulkInstall';
export const BULK_SUCCESS_COUNT_OPTIONS = [10, 50, 100, 500, 1000] as const;
export const BULK_DEFAULT_SUCCESS_COUNT = 100;
export const BULK_EXPIRE_UNITS = ['day', 'month', 'year'] as const;
export type BulkExpireUnit = (typeof BULK_EXPIRE_UNITS)[number];
export const BULK_DEFAULT_EXPIRE_COUNT = 1;
export const BULK_DEFAULT_EXPIRE_UNIT: BulkExpireUnit = 'day';
export const BULK_EXPIRE_UNIT_DAYS: Record<BulkExpireUnit, number> = {
  day: 1,
  month: 30,
  year: 365
};
export const BULK_EXPIRE_UNIT_MAX: Record<BulkExpireUnit, number> = {
  day: 1095,
  month: 36,
  year: 3
};
export const BULK_EXPIRE_DAY_MS = 24 * 60 * 60 * 1000;

export function clampBulkExpireCount(count: number, unit: BulkExpireUnit): number {
  const max = BULK_EXPIRE_UNIT_MAX[unit];
  if (!Number.isInteger(count) || count < 1) {
    return 1;
  }
  if (count > max) {
    return max;
  }
  return count;
}

export function bulkExpireDays(count: number, unit: BulkExpireUnit): number | null {
  if (!Number.isInteger(count)) {
    return null;
  }
  if (count < 1 || count > BULK_EXPIRE_UNIT_MAX[unit]) {
    return null;
  }
  return count * BULK_EXPIRE_UNIT_DAYS[unit];
}

export function bulkExpirePreviewTime(count: number, unit: BulkExpireUnit, nowMs: number): number | null {
  const days = bulkExpireDays(count, unit);
  if (days == null) {
    return null;
  }
  return nowMs + days * BULK_EXPIRE_DAY_MS;
}

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

const ATTEMPT_STATUS_COLOR: Record<string, string> = {
  installing: 'processing',
  duplicate: 'warning',
  failed: 'error',
  timeout: 'default'
};

export function bulkAttemptDisplay(item: { status: string; online?: boolean }): {
  labelKey: string;
  color: string;
} {
  if (item.online) {
    return {
      labelKey: 'node-manager.cloudregion.node.bulkAttemptOnline',
      color: 'success'
    };
  }
  if (item.status === 'installed') {
    return {
      labelKey: 'node-manager.cloudregion.node.bulkAttemptAwaitingOnline',
      color: 'processing'
    };
  }
  return {
    labelKey: bulkAttemptStatusLabelKey(item.status),
    color: ATTEMPT_STATUS_COLOR[item.status] || 'default'
  };
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
