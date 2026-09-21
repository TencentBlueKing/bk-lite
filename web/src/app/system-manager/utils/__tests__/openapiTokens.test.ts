import { describe, expect, it } from 'vitest';
import {
  asList,
  canManageByOperations,
  docsToCatalog,
  expiryStatus,
  findMenuOperations,
  formValuesToWritePayload,
  formatScopeLabel,
  isDuplicateTokenNameError,
  isOpenApiTokenScope,
  normalizeClientScope,
  toExpiresAtIso,
  toPersonalRow,
  toSystemRow,
} from '@/app/system-manager/utils/openapiTokens';

describe('asList', () => {
  it('unwraps paginated items and ignores other shapes', () => {
    expect(asList([{ id: 1 }])).toEqual([{ id: 1 }]);
    expect(asList({ items: [{ id: 2 }] })).toEqual([{ id: 2 }]);
    expect(asList(undefined)).toEqual([]);
  });
});

describe('expiryStatus', () => {
  it('treats empty as never and compares against now', () => {
    expect(expiryStatus(null)).toBe('never');
    expect(expiryStatus('1999-01-01T00:00:00Z')).toBe('expired');
    expect(expiryStatus('2999-01-01T00:00:00Z')).toBe('active');
  });
});

describe('scope conversion', () => {
  it('accepts canonical scope and migrates legacy JSON to all', () => {
    expect(isOpenApiTokenScope({ mode: 'all' })).toBe(true);
    expect(isOpenApiTokenScope({
      mode: 'allowlist',
      endpoints: ['GET cmdb/classifications'],
    })).toBe(true);
    expect(isOpenApiTokenScope({ cmdb: ['asset_info-View'] })).toBe(false);
    expect(normalizeClientScope({ cmdb: ['asset_info-View'] })).toEqual({ mode: 'all' });
  });

  it('formats all vs allowlist labels', () => {
    expect(formatScopeLabel({ mode: 'all' }, '全部接口')).toBe('全部接口');
    expect(formatScopeLabel({
      mode: 'allowlist',
      endpoints: ['GET cmdb/classifications', 'EXTERNAL itsm'],
    }, '全部接口')).toBe('GET cmdb/classifications, EXTERNAL itsm');
  });
});

describe('formValuesToWritePayload', () => {
  it('serializes name, expiry and all-mode scope', () => {
    expect(formValuesToWritePayload({
      name: 'CI',
      expiresAt: new Date('2026-12-31T16:00:00.000Z'),
      scopeMode: 'all',
      scopeEndpoints: ['GET cmdb/classifications'],
    })).toEqual({
      name: 'CI',
      expires_at: '2026-12-31T16:00:00.000Z',
      scope: { mode: 'all' },
    });
    expect(toExpiresAtIso(undefined)).toBeNull();
  });

  it('serializes allowlist endpoints', () => {
    expect(formValuesToWritePayload({
      name: 'ITSM',
      scopeMode: 'allowlist',
      scopeEndpoints: ['GET cmdb/classifications', 'GET cmdb/classifications', 'EXTERNAL itsm'],
    })).toEqual({
      name: 'ITSM',
      expires_at: null,
      scope: {
        mode: 'allowlist',
        endpoints: ['GET cmdb/classifications', 'EXTERNAL itsm'],
      },
    });
  });
});

describe('row mapping', () => {
  it('maps personal and system API items for the table', () => {
    expect(toPersonalRow({
      id: 2,
      username: 'alice',
      domain: 'domain.com',
      team: 1,
      team_name: '华南',
      name: 'CI',
      expires_at: '2999-01-01T00:00:00Z',
      scope: { mode: 'all' },
      created_at: '2026-09-10T02:30:00Z',
      updated_at: '2026-09-10T02:30:00Z',
      api_secret_preview: '********',
    })).toEqual({
      id: 2,
      name: 'CI',
      preview: '********',
      teamName: '华南',
      createdAt: '2026-09-10T02:30:00Z',
      expiresAt: '2999-01-01T00:00:00Z',
      status: 'active',
      scope: { mode: 'all' },
    });

    expect(toSystemRow({
      id: 11,
      system_id: 'itsm',
      name: 'ITSM 异步节点',
      expires_at: null,
      scope: { mode: 'allowlist', endpoints: ['EXTERNAL itsm'] },
      enabled: true,
      created_at: '2026-09-12T06:20:00Z',
      updated_at: '2026-09-12T06:20:00Z',
      created_by: 'admin',
      api_secret_preview: 'bksys_********',
    })).toMatchObject({
      id: 11,
      systemId: 'itsm',
      preview: 'bksys_********',
      enabled: true,
      status: 'never',
      scope: { mode: 'allowlist', endpoints: ['EXTERNAL itsm'] },
    });
  });
});

describe('docs catalog', () => {
  it('converts internal endpoints and external prefixes', () => {
    expect(docsToCatalog({
      services: [
        {
          name: 'cmdb',
          kind: 'internal',
          endpoints: [
            {
              path: 'cmdb/classifications',
              method: 'GET',
              summary: '模型分类',
              inject: null,
              permission: '',
              request_schema: {},
            },
          ],
        },
        {
          name: 'itsm',
          kind: 'external',
          doc_url: 'http://itsm/docs',
        },
      ],
    })).toEqual([
      {
        name: 'cmdb',
        kind: 'internal',
        label: 'cmdb',
        endpoints: [{
          key: 'GET cmdb/classifications',
          label: '模型分类',
          method: 'GET',
          path: 'cmdb/classifications',
        }],
      },
      {
        name: 'itsm',
        kind: 'external',
        label: 'itsm',
        endpoints: [{ key: 'EXTERNAL itsm', label: 'itsm' }],
      },
    ]);
  });
});

describe('menu helpers', () => {
  const menus = [
    {
      name: 'Setting',
      children: [
        { name: 'api_secret_key', operation: ['View', 'Add'] },
        { name: 'system_api_secret', display_name: 'System API Secret', operation: ['View', 'Add', 'Edit'] },
      ],
    },
  ];

  it('finds nested menu operations and manage flags', () => {
    expect(findMenuOperations(menus, 'system_api_secret')).toEqual(['View', 'Add', 'Edit']);
    expect(findMenuOperations(menus, 'missing')).toEqual([]);
    expect(canManageByOperations(['View'])).toBe(false);
    expect(canManageByOperations(['Edit'])).toBe(true);
  });
});

describe('isDuplicateTokenNameError', () => {
  it('matches the gateway field-prefixed uniqueness message', () => {
    expect(isDuplicateTokenNameError(new Error('name:name already exists'))).toBe(true);
    expect(isDuplicateTokenNameError(new Error('name already exists'))).toBe(true);
    expect(isDuplicateTokenNameError(new Error('Request failed (400)'))).toBe(false);
  });
});
