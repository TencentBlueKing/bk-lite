import { describe, expect, it } from 'vitest';
import {
  BULK_INSTALL_METHOD,
  bulkAttemptStatusLabelKey,
  bulkCommandIncludesNodeIp,
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
