import assert from 'node:assert/strict';
import path from 'node:path';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';

import fs from 'fs-extra';

import * as enterprisePrepare from './prepare-enterprise.mjs';

const tmpRoot = await mkdtemp(path.join(os.tmpdir(), 'prepare-enterprise-assets-'));

try {
  assert.equal(
    typeof enterprisePrepare.prepareEnterprisePublicAssets,
    'function',
    'prepareEnterprisePublicAssets should be exported for isolated assets overlay testing'
  );

  const webRoot = path.join(tmpRoot, 'web');
  const enterpriseWebRoot = path.join(tmpRoot, 'enterprise-web');
  const enterpriseIconsRoot = path.join(enterpriseWebRoot, 'public', 'assets', 'icons');
  const communityIconsRoot = path.join(webRoot, 'public', 'assets', 'icons');

  await fs.ensureDir(enterpriseIconsRoot);
  await fs.ensureDir(communityIconsRoot);
  await writeFile(path.join(communityIconsRoot, 'cc-default_默认.svg'), '<svg>default</svg>');
  await writeFile(path.join(communityIconsRoot, 'cc-existing.svg'), '<svg>community</svg>');
  await writeFile(path.join(enterpriseIconsRoot, 'cc-ibmmq.svg'), '<svg>ibmmq</svg>');
  await writeFile(path.join(enterpriseIconsRoot, 'mm-ibmmq.svg'), '<svg>ibmmq-mm</svg>');
  await writeFile(path.join(enterpriseIconsRoot, 'cc-existing.svg'), '<svg>enterprise</svg>');
  await writeFile(path.join(enterpriseIconsRoot, 'readme.txt'), 'not an icon');

  const copied = await enterprisePrepare.prepareEnterprisePublicAssets({
    webRoot,
    enterpriseWebRoot,
  });

  assert.deepEqual(copied.sort(), ['cc-ibmmq.svg', 'mm-ibmmq.svg']);
  assert.equal(await fs.readFile(path.join(communityIconsRoot, 'cc-ibmmq.svg'), 'utf8'), '<svg>ibmmq</svg>');
  assert.equal(await fs.readFile(path.join(communityIconsRoot, 'mm-ibmmq.svg'), 'utf8'), '<svg>ibmmq-mm</svg>');
  assert.equal(await fs.pathExists(path.join(communityIconsRoot, 'readme.txt')), false);
  assert.equal(await fs.readFile(path.join(communityIconsRoot, 'cc-default_默认.svg'), 'utf8'), '<svg>default</svg>');
  assert.equal(await fs.readFile(path.join(communityIconsRoot, 'cc-existing.svg'), 'utf8'), '<svg>community</svg>');

  console.log('prepare-enterprise public assets overlay ok');
} finally {
  await rm(tmpRoot, { recursive: true, force: true });
}
