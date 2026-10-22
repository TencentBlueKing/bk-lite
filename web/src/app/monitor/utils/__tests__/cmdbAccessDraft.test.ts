import { describe, expect, it } from 'vitest';
import {
  applyCmdbDraftNodeMatch,
  isHostAgentTable,
  mapCmdbAccessDraftRows,
  matchNodeIdByIp,
  projectCmdbDraftRowOntoTable,
} from '../cmdbAccessDraft';

describe('mapCmdbAccessDraftRows', () => {
  it('maps identity fields and keeps cmdb_id', () => {
    const rows = mapCmdbAccessDraftRows(
      [
        {
          inst_uuid: 'ci-1',
          inst_name: 'web-1',
          ip: '10.0.0.1',
          port: 3306,
          organization: [3],
          cloud_region_id: 1,
        },
      ],
      [9],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].instance_name).toBe('web-1');
    expect(rows[0].ip).toBe('10.0.0.1');
    expect(rows[0].port).toBe('3306');
    expect(rows[0].group_ids).toEqual(['3']);
    expect(rows[0].cmdb_id).toBe('ci-1');
    expect(rows[0].cloud_region_id).toBe(1);
    expect(rows[0].key).toBeTruthy();
  });

  it('falls back to current group when draft has no organization', () => {
    const rows = mapCmdbAccessDraftRows([{ instance_name: 'db-1', cmdb_id: 'ci-2' }], [8]);
    expect(rows[0].group_ids).toEqual(['8']);
    expect(rows[0].cmdb_id).toBe('ci-2');
  });

  it('takes the first IP when CMDB stores a list', () => {
    const rows = mapCmdbAccessDraftRows([{ inst_name: 'web-2', ip: ['10.0.0.8', '10.0.0.9'], cmdb_id: 'ci-3' }]);
    expect(rows[0].ip).toBe('10.0.0.8');
  });
});

describe('projectCmdbDraftRowOntoTable', () => {
  it('copies IP and port onto database host/port columns', () => {
    const row = mapCmdbAccessDraftRows([{ inst_name: 'pg-1', ip: '10.1.2.3', port: 5432, cmdb_id: 'ci-pg' }])[0];
    const projected = projectCmdbDraftRowOntoTable(row, {
      node_ids: null,
      host: null,
      port: null,
      instance_name: null,
      group_ids: ['1'],
    });
    expect(projected.host).toBe('10.1.2.3');
    expect(projected.port).toBe('5432');
    expect(projected.instance_name).toBe('pg-1');
  });

  it('seeds HTTP url without inventing a plugin path', () => {
    const row = mapCmdbAccessDraftRows([{ inst_name: 'tomcat-1', ip: '10.1.2.5', port: 8080, cmdb_id: 'ci-tc' }])[0];
    const projected = projectCmdbDraftRowOntoTable(
      row,
      { node_ids: null, url: null, instance_name: null, group_ids: ['1'] },
      [{ name: 'url', widget_props: { placeholder: 'http://example.com:8080/manager/status/all?XML=true' } }],
    );
    expect(projected.url).toBe('http://10.1.2.5:8080');
  });

  it('seeds host:port when the template example has no scheme', () => {
    const row = mapCmdbAccessDraftRows([{ inst_name: 'zk-1', ip: '10.1.2.6', port: 2181, cmdb_id: 'ci-zk' }])[0];
    const projected = projectCmdbDraftRowOntoTable(
      row,
      { node_ids: null, url: null, instance_name: null, group_ids: ['1'] },
      [{ name: 'url', widget_props: { placeholder: '127.0.0.1:2181' } }],
    );
    expect(projected.url).toBe('10.1.2.6:2181');
  });

  it('keeps IP on Host Agent rows even when the table has no IP column', () => {
    const row = mapCmdbAccessDraftRows([{ inst_name: 'os-1', ip: '10.1.2.4', cmdb_id: 'ci-os' }])[0];
    const projected = projectCmdbDraftRowOntoTable(row, {
      node_ids: null,
      instance_name: null,
      group_ids: ['1'],
    });
    expect(projected.ip).toBe('10.1.2.4');
    expect(projected.host).toBeUndefined();
  });
});

describe('isHostAgentTable', () => {
  it('is true only when the node itself is the target', () => {
    expect(isHostAgentTable({ node_ids: null, instance_name: null, group_ids: ['1'] })).toBe(true);
    expect(isHostAgentTable({ node_ids: null, host: null, instance_name: null, group_ids: ['1'] })).toBe(false);
    expect(isHostAgentTable({ node_ids: null, ip: null, instance_name: null, group_ids: ['1'] })).toBe(false);
  });
});

describe('matchNodeIdByIp', () => {
  const nodes = [
    { id: 'n-busy', value: 'n-busy', ip: '10.0.0.1', disabled: true },
    { id: 'n-ok', value: 'n-ok', ip: '10.0.0.2', disabled: false },
  ];

  it('selects the available node with the same IP', () => {
    expect(matchNodeIdByIp('10.0.0.2', nodes)).toBe('n-ok');
  });

  it('falls back to a disabled node when that is the only IP match', () => {
    expect(matchNodeIdByIp('10.0.0.1', nodes)).toBe('n-busy');
  });
});

describe('applyCmdbDraftNodeMatch', () => {
  it('fills empty node_ids for draft rows by IP', () => {
    const rows = [
      { key: '1', cmdb_id: 'ci-1', ip: '10.0.0.2', instance_name: 'os-1' },
      { key: '2', instance_name: 'manual' },
    ];
    const next = applyCmdbDraftNodeMatch(rows, [{ id: 'n-ok', value: 'n-ok', ip: '10.0.0.2' }]);
    expect(next[0].node_ids).toBe('n-ok');
    expect(next[1].node_ids).toBeUndefined();
  });

  it('does not match collector nodes for remote plugins', () => {
    const rows = [{ key: '1', cmdb_id: 'ci-1', ip: '10.0.0.2' }];
    const next = applyCmdbDraftNodeMatch(rows, [{ id: 'n-ok', value: 'n-ok', ip: '10.0.0.2' }], false);
    expect(next).toBe(rows);
  });

  it('does not overwrite a node the operator already chose', () => {
    const rows = [{ key: '1', cmdb_id: 'ci-1', ip: '10.0.0.2', node_ids: 'n-manual' }];
    const next = applyCmdbDraftNodeMatch(rows, [{ id: 'n-ok', value: 'n-ok', ip: '10.0.0.2' }]);
    expect(next).toBe(rows);
    expect(next[0].node_ids).toBe('n-manual');
  });
});
