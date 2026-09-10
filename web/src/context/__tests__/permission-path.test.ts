import { describe, expect, it } from 'vitest';

import { hasRoutePermission } from '@/context/permission-path';
import cmdbMenu from '@/app/cmdb/constants/menu.json';

const SOID_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/soid';
const PORT_PATH = '/cmdb/assetManage/autoDiscovery/featureLibrary/port';

describe('hasRoutePermission', () => {
  it('does not treat feature-library soid as covering the port tab', () => {
    expect(
      hasRoutePermission({ [SOID_PATH]: ['View'] }, PORT_PATH),
    ).toBe(false);
  });

  it('allows the port tab when it has its own permission key', () => {
    expect(
      hasRoutePermission(
        {
          [SOID_PATH]: ['View', 'Add', 'Delete'],
          [PORT_PATH]: ['View', 'Add', 'Delete'],
        },
        PORT_PATH,
      ),
    ).toBe(true);
  });
});

describe('cmdb feature library menu', () => {
  it.each(['zh', 'en'] as const)(
    'registers the port fingerprint route as a hidden soid_library item (%s)',
    (locale) => {
      const autoDiscovery = cmdbMenu[locale]
        .find((item) => item.url === '/cmdb/assetManage')
        ?.children?.find((item) => item.url === '/cmdb/assetManage/autoDiscovery');
      const portItem = autoDiscovery?.children?.find((item) => item.url === PORT_PATH);

      expect(portItem).toMatchObject({
        url: PORT_PATH,
        name: 'soid_library',
        isNotMenuItem: true,
      });
    },
  );
});
