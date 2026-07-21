import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, rm } from 'node:fs/promises';

import fs from 'fs-extra';

import { copyPublicDirectories } from '../src/utils/dynamicsMerged.mjs';

const tmpRoot = await mkdtemp(path.join(os.tmpdir(), 'copy-enterprise-public-'));

try {
  const communityAppRoot = path.join(tmpRoot, 'web', 'src', 'app');
  const enterpriseAppRoot = path.join(tmpRoot, 'enterprise', 'web', 'src', 'app');
  const destinationRoot = path.join(tmpRoot, 'web', 'public', 'app');

  await fs.outputFile(
    path.join(communityAppRoot, 'ops-console', 'public', 'versions', 'ops-console', 'en', 'community.md'),
    'community only'
  );
  await fs.outputFile(
    path.join(communityAppRoot, 'ops-console', 'public', 'versions', 'ops-console', 'en', 'shared.md'),
    'community'
  );
  await fs.outputFile(
    path.join(enterpriseAppRoot, 'ops-console', 'public', 'versions', 'ops-console', 'en', '6.10.md'),
    'enterprise only'
  );
  await fs.outputFile(
    path.join(enterpriseAppRoot, 'ops-console', 'public', 'versions', 'ops-console', 'en', 'shared.md'),
    'enterprise'
  );

  copyPublicDirectories({
    communityAppRoots: [communityAppRoot],
    enterpriseAppRoot,
    enterprisePublicRoot: path.join(tmpRoot, 'enterprise', 'web', 'public'),
    destinationRoot,
  });

  const versionsRoot = path.join(destinationRoot, 'versions', 'ops-console', 'en');
  assert.equal(await fs.readFile(path.join(versionsRoot, 'community.md'), 'utf8'), 'community only');
  assert.equal(await fs.readFile(path.join(versionsRoot, '6.10.md'), 'utf8'), 'enterprise only');
  assert.equal(await fs.readFile(path.join(versionsRoot, 'shared.md'), 'utf8'), 'enterprise');
  assert.equal(await fs.pathExists(path.join(destinationRoot, 'enterprise')), false);

  console.log('enterprise app public directories merged into web public without enterprise sources');
} finally {
  await rm(tmpRoot, { recursive: true, force: true });
}
