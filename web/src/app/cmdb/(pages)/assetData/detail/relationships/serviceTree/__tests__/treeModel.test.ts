import { describe, expect, it } from 'vitest';

import {
  canAssignHosts,
  canCreateApplication,
  collectTreeKeys,
  createLayerActions,
  flattenApplications,
  hostsForAction,
  mergePageSelection,
  hostCandidateQuery,
  transferAppLabel,
} from '../treeModel';

describe('service tree rules', () => {
  it('only applications can assign hosts', () => {
    expect(canAssignHosts('application')).toBe(true);
    expect(canAssignHosts('system')).toBe(false);
    expect(canAssignHosts('env')).toBe(false);
  });

  it('host actions keep the table selection instead of all hosts', () => {
    const hosts = [
      { inst_uuid: 'h1', inst_name: 'web-1' },
      { inst_uuid: 'h2', inst_name: 'web-2' },
      { inst_uuid: 'h3', inst_name: 'web-3' },
    ];
    expect(hostsForAction(hosts, ['h1', 'h3']).map((item) => item.inst_name)).toEqual(['web-1', 'web-3']);
    expect(hostsForAction(hosts, [])).toEqual([]);
  });

  it('keeps host selection across pages', () => {
    expect(mergePageSelection(['h1', 'h2'], ['h3', 'h4'], ['h4'])).toEqual(['h1', 'h2', 'h4']);
    expect(mergePageSelection(['h1', 'h4'], ['h3', 'h4'], [])).toEqual(['h1']);
    expect(mergePageSelection(['h1'], ['h3', 'h4'], ['h1', 'h4'])).toEqual(['h1', 'h4']);
  });

  it('searches host candidates by name containing the keyword', () => {
    expect(hostCandidateQuery('  ')).toEqual([]);
    expect(hostCandidateQuery('10.0.12')).toEqual([{ field: 'inst_name', type: 'str*', value: '10.0.12' }]);
  });

  it('prefixes transfer targets with the application system', () => {
    expect(transferAppLabel({ inst_name: 'ops-portal', system_name: 'sys-ops' })).toBe('sys-ops / ops-portal');
    expect(transferAppLabel({ inst_name: 'ops-portal' })).toBe('ops-portal');
  });

  it('does not show a grouping button until a custom model sits between system and application', () => {
    expect(createLayerActions({ kind: 'system', create_layers: [] })).toEqual([]);
    expect(
      createLayerActions({
        kind: 'system',
        create_layers: [{ model_id: 'env', model_name: '环境' }],
      }),
    ).toEqual([{ model_id: 'env', model_name: '环境' }]);
    expect(canCreateApplication({ kind: 'system', can_create_application: true })).toBe(true);
    expect(canCreateApplication({ kind: 'application', can_create_application: false })).toBe(false);
    expect(canCreateApplication({ kind: 'env', can_create_application: true })).toBe(true);
  });

  it('collects applications without putting hosts on the tree', () => {
    const apps = flattenApplications({
      inst_uuid: 's1',
      inst_name: '门户',
      kind: 'system',
      depth: 0,
      host_count: 2,
      children: [
        {
          inst_uuid: 'a1',
          inst_name: '前端',
          kind: 'application',
          depth: 1,
          host_count: 1,
        },
      ],
    });
    expect(apps.map((item) => item.inst_uuid)).toEqual(['a1']);
    expect(collectTreeKeys({
      inst_uuid: 's1',
      inst_name: '门户',
      kind: 'system',
      depth: 0,
      host_count: 1,
      children: [{
        inst_uuid: 'a1',
        inst_name: '前端',
        kind: 'application',
        depth: 1,
        host_count: 1,
      }],
    })).toEqual(['s1', 'a1']);
  });
});
