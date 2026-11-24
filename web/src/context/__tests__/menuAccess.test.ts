import { describe, expect, it } from 'vitest';

import {
  buildParentPermissionIndex,
  extractPermissions,
  filterMenusByPermission,
} from '@/context/menuAccess';
import { hasRoutePermission } from '@/context/permission-path';
import type { MenuItem } from '@/types/index';

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: item.name,
  icon: '',
  operation: [],
  ...item,
});

describe('hidden menu urls', () => {
  it('keeps the console home when the app has no permission codes', () => {
    const home = [
      menu({ name: 'bot_list', url: '/ops-console/home', isNotMenuItem: true }),
    ];
    const filtered = filterMenusByPermission({}, home, 'ops-console');
    expect(filtered.map((item) => item.url)).toEqual(['/ops-console/home']);
    expect(extractPermissions(filtered)['/ops-console/home']).toContain('View');
  });

  const workflow = [
    menu({ name: 'workflow_home', url: '/workflow/home' }),
    menu({ name: 'workflow_execution', url: '/workflow/executions' }),
    menu({ name: 'workflow_entry', url: '/workflow', isNotMenuItem: true }),
  ];

  it('does not keep a hidden app root when the user has no workflow grant', () => {
    const filtered = filterMenusByPermission({}, workflow, 'workflow');
    expect(filtered.map((item) => item.name)).not.toContain('workflow_entry');
    expect(extractPermissions(filtered)).toEqual({});
  });

  it('grants only the workflow page that was actually assigned', () => {
    const filtered = filterMenusByPermission(
      { workflow_home: ['View'] },
      workflow,
      'workflow',
    );
    const permissions = extractPermissions(filtered);
    expect(permissions['/workflow/home']).toEqual(['View']);
    expect(permissions['/workflow']).toBeUndefined();
    expect(permissions['/workflow/executions']).toBeUndefined();
  });

  it('does not let one integration page open its siblings through a hidden prefix', () => {
    const integration = [
      menu({
        name: 'Integration',
        url: '/apm/integration/applications',
        children: [
          menu({ name: 'applications', url: '/apm/integration/applications' }),
          menu({ name: 'integration_add', url: '/apm/integration/add' }),
          menu({ name: 'integration_instances', url: '/apm/integration/instances' }),
          menu({ name: 'integration_add', url: '/apm/integration', isNotMenuItem: true }),
        ],
      }),
    ];
    const filtered = filterMenusByPermission(
      { integration_instances: ['View'] },
      integration,
      'apm',
    );
    const permissions = extractPermissions(filtered);
    expect(permissions['/apm/integration/instances']).toEqual(['View']);
    expect(permissions['/apm/integration']).toBeUndefined();
    expect(permissions['/apm/integration/add']).toBeUndefined();
  });

  it('still opens a hidden detail page under a granted parent', () => {
    const errors = [
      menu({
        name: 'errors',
        url: '/rum/errors',
        children: [
          menu({ name: 'errors', url: '/rum/errors' }),
          menu({ name: 'error_detail', url: '/rum/errors/detail', isNotMenuItem: true }),
        ],
      }),
    ];
    const filtered = filterMenusByPermission({ errors: ['View'] }, errors, 'rum');
    const permissions = extractPermissions(filtered);
    expect(permissions['/rum/errors/detail']).toContain('View');
  });
});

describe('custom menu pages that follow a parent permission', () => {
  const builtin = [
    menu({
      name: 'asset_info',
      url: '/cmdb/assetOverview',
      children: [
        menu({ name: 'asset_views_overview', url: '/cmdb/assetOverview', withParentPermission: true }),
        menu({ name: 'asset_views_application', url: '/cmdb/views/application', withParentPermission: true }),
        menu({ name: 'asset_views_k8s', url: '/cmdb/views/k8s', withParentPermission: true }),
      ],
    }),
  ];
  const custom = [
    menu({ name: 'asset_views_k8s', url: '/cmdb/views/k8s' }),
    menu({
      name: '新目录',
      url: '',
      children: [
        menu({ name: 'asset_views_application', url: '/cmdb/views/application' }),
        menu({ name: 'asset_views_overview', url: '/cmdb/assetOverview' }),
      ],
    }),
  ];

  it('keeps the saved CMDB views when the user has the parent view permission', () => {
    const filtered = filterMenusByPermission(
      { asset_info: ['View'] },
      custom,
      'cmdb',
      undefined,
      buildParentPermissionIndex(builtin),
    );
    const permissions = extractPermissions(filtered);
    expect(Object.keys(permissions)).toEqual(expect.arrayContaining([
      '/cmdb/views/k8s',
      '/cmdb/views/application',
      '/cmdb/assetOverview',
    ]));
  });

  it('still hides those views when the parent permission is absent', () => {
    const filtered = filterMenusByPermission(
      {},
      custom,
      'cmdb',
      undefined,
      buildParentPermissionIndex(builtin),
    );
    expect(filtered).toEqual([]);
  });
});

describe('directory without its own url', () => {
  const wrapped = [
    menu({
      name: '新目录',
      url: '',
      children: [
        menu({
          name: 'Management',
          url: '/cmdb/assetManage',
          children: [
            menu({
              name: 'model_management',
              url: '/cmdb/assetManage/management',
            }),
            menu({
              name: 'system_settings',
              url: '/cmdb/assetManage/systemSettings',
            }),
          ],
        }),
      ],
    }),
  ];

  it('does not grant the management tree when the user has no permission', () => {
    const filtered = filterMenusByPermission({}, wrapped, 'cmdb');
    const permissions = extractPermissions(filtered);
    expect(permissions['/cmdb/assetManage']).toBeUndefined();
    expect(hasRoutePermission(permissions, '/cmdb/assetManage/management')).toBe(false);
    expect(hasRoutePermission(permissions, '/cmdb/assetManage/systemSettings')).toBe(false);
  });

  it('grants only the assigned page when one child permission is present', () => {
    const filtered = filterMenusByPermission(
      { model_management: ['View'] },
      wrapped,
      'cmdb',
    );
    const permissions = extractPermissions(filtered);
    expect(permissions['/cmdb/assetManage/management']).toEqual(['View']);
    expect(permissions['/cmdb/assetManage']).toBeUndefined();
    expect(hasRoutePermission(permissions, '/cmdb/assetManage/systemSettings')).toBe(false);
  });
});
