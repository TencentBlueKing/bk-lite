import { afterEach, describe, expect, it } from 'vitest';

import { getInstallApps } from '../installApps';

describe('getInstallApps', () => {
  const original = process.env.NEXTAPI_INSTALL_APP;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.NEXTAPI_INSTALL_APP;
    } else {
      process.env.NEXTAPI_INSTALL_APP = original;
    }
  });

  it('keeps glue module-link when NEXTAPI_INSTALL_APP is an explicit sold-app list', async () => {
    process.env.NEXTAPI_INSTALL_APP = 'cmdb,monitor';
    const apps = await getInstallApps(['/unused']);
    expect(apps).toEqual(['cmdb', 'monitor', 'module-link']);
  });

  it('does not duplicate module-link if it is already listed', async () => {
    process.env.NEXTAPI_INSTALL_APP = 'module-link,cmdb';
    const apps = await getInstallApps(['/unused']);
    expect(apps).toEqual(['module-link', 'cmdb']);
  });
});
