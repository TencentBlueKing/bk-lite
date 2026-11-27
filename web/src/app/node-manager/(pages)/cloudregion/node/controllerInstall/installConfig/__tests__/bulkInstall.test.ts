import { describe, expect, it } from 'vitest';
import {
  BULK_DEFAULT_EXPIRE_COUNT,
  BULK_DEFAULT_EXPIRE_UNIT,
  BULK_DEFAULT_SUCCESS_COUNT,
  BULK_EXPIRE_DAY_MS,
  BULK_INSTALL_METHOD,
  BULK_SUCCESS_COUNT_OPTIONS,
  bulkAttemptDisplay,
  bulkAttemptStatusLabelKey,
  bulkCommandIncludesNodeIp,
  bulkExpireDays,
  bulkExpirePreviewTime,
  clampBulkExpireCount,
  dedupeControllerPackages,
  installWaysForOs
} from '../bulkInstall';

const remote = { label: '远程安装', value: 'remoteInstall' };
const manual = { label: '手动安装', value: 'manualInstall' };
const bulk = { label: '批量命令', value: BULK_INSTALL_METHOD };

describe('installWaysForOs', () => {
  it('adds the bulk command only for Linux', () => {
    expect(installWaysForOs([remote, manual], 'linux', bulk).map((item) => item.value)).toEqual([
      'remoteInstall',
      'manualInstall',
      'bulkInstall'
    ]);
  });

  it('keeps Windows on remote and manual install', () => {
    expect(installWaysForOs([remote, manual, bulk], 'windows', bulk).map((item) => item.value)).toEqual([
      'remoteInstall',
      'manualInstall'
    ]);
  });
});

describe('bulkAttemptStatusLabelKey', () => {
  it('uses different labels for an accepted install and a duplicate', () => {
    const installing = bulkAttemptStatusLabelKey('installing');
    const duplicate = bulkAttemptStatusLabelKey('duplicate');

    expect(installing).not.toBe(duplicate);
    expect(installing).toContain('Installing');
    expect(duplicate).toContain('Duplicate');
  });
});

describe('bulkAttemptDisplay', () => {
  it('shows online in the success color when the node has come online', () => {
    expect(bulkAttemptDisplay({ status: 'installing', online: true })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptOnline',
      color: 'success'
    });
    expect(bulkAttemptDisplay({ status: 'installed', online: true })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptOnline',
      color: 'success'
    });
    expect(bulkAttemptDisplay({ status: 'failed', online: true })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptOnline',
      color: 'success'
    });
  });

  it('shows installed hosts that have not heartbeated as waiting to come online', () => {
    expect(bulkAttemptDisplay({ status: 'installed', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptAwaitingOnline',
      color: 'processing'
    });
    expect(bulkAttemptDisplay({ status: 'installed' })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptAwaitingOnline',
      color: 'processing'
    });
  });

  it('keeps the existing label and color for the other statuses', () => {
    expect(bulkAttemptDisplay({ status: 'installing', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptInstalling',
      color: 'processing'
    });
    expect(bulkAttemptDisplay({ status: 'duplicate', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptDuplicate',
      color: 'warning'
    });
    expect(bulkAttemptDisplay({ status: 'failed', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptFailed',
      color: 'error'
    });
    expect(bulkAttemptDisplay({ status: 'timeout', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptTimeout',
      color: 'default'
    });
    expect(bulkAttemptDisplay({ status: 'other', online: false })).toEqual({
      labelKey: 'node-manager.cloudregion.node.bulkAttemptFailed',
      color: 'default'
    });
  });
});

describe('bulkCommandIncludesNodeIp', () => {
  it('only treats a command as ready to copy when it carries --node_ip', () => {
    expect(
      bulkCommandIncludesNodeIp(
        "curl -fsSLk 'https://node.example/bulk_bootstrap?token=abc' | sudo bash -s -- --node_ip <主机IP>"
      )
    ).toBe(true);
    expect(bulkCommandIncludesNodeIp('curl -fsSLk https://node.example/bootstrap | sudo bash')).toBe(
      false
    );
  });
});

describe('bulk install presets', () => {
  it('keeps the default duration at one day and converts months and years into days', () => {
    expect(BULK_SUCCESS_COUNT_OPTIONS).toContain(BULK_DEFAULT_SUCCESS_COUNT);
    expect(BULK_DEFAULT_EXPIRE_COUNT).toBe(1);
    expect(BULK_DEFAULT_EXPIRE_UNIT).toBe('day');
    expect(bulkExpireDays(1, 'day')).toBe(1);
    expect(bulkExpireDays(6, 'month')).toBe(180);
    expect(bulkExpireDays(12, 'month')).toBe(360);
    expect(bulkExpireDays(1, 'year')).toBe(365);
    expect(bulkExpireDays(3, 'year')).toBe(1095);
    expect(bulkExpireDays(37, 'month')).toBeNull();
    expect(bulkExpireDays(1.5, 'day')).toBeNull();
    expect(bulkExpirePreviewTime(6, 'month', 1_000)).toBe(1_000 + 180 * BULK_EXPIRE_DAY_MS);
  });

  it('reinterprets the typed number when the unit changes and clamps only the overflow', () => {
    expect(clampBulkExpireCount(2, 'day')).toBe(2);
    expect(clampBulkExpireCount(400, 'year')).toBe(3);
    expect(clampBulkExpireCount(0, 'month')).toBe(1);
  });
});

describe('dedupeControllerPackages', () => {
  it('keeps one row per version when the bulk command covers every architecture', () => {
    const packages = dedupeControllerPackages(
      [
        { os: 'linux', cpu_architecture: 'x86_64', version: '1.2.3', id: 1 },
        { os: 'linux', cpu_architecture: 'arm64', version: '1.2.3', id: 2 },
        { os: 'linux', cpu_architecture: 'x86_64', version: '1.2.4', id: 3 }
      ],
      true
    );

    expect(packages.map((item) => item.version)).toEqual(['1.2.3', '1.2.4']);
  });
});
