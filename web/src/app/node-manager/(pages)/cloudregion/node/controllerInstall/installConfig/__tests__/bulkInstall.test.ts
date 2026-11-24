import { describe, expect, it } from 'vitest';
import {
  BULK_DEFAULT_EXPIRE_DAYS,
  BULK_DEFAULT_SUCCESS_COUNT,
  BULK_EXPIRE_DAY_OPTIONS,
  BULK_INSTALL_METHOD,
  BULK_SUCCESS_COUNT_OPTIONS,
  bulkAttemptDisplay,
  bulkAttemptStatusLabelKey,
  bulkCommandIncludesNodeIp,
  bulkExpireHours,
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
  it('offers fixed host counts and day choices, with the defaults included', () => {
    expect(BULK_SUCCESS_COUNT_OPTIONS).toContain(BULK_DEFAULT_SUCCESS_COUNT);
    expect(BULK_EXPIRE_DAY_OPTIONS).toContain(BULK_DEFAULT_EXPIRE_DAYS);
    expect(BULK_EXPIRE_DAY_OPTIONS).toEqual([1, 3, 5, 7]);
    expect(BULK_DEFAULT_EXPIRE_DAYS).toBe(1);
    expect(bulkExpireHours(BULK_DEFAULT_EXPIRE_DAYS)).toBe(24);
    expect(bulkExpireHours(5)).toBe(120);
    expect(bulkExpireHours(7)).toBe(168);
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
