import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';

import fs from 'fs-extra';

import { prepareEnterpriseDependencyLink } from './prepare-enterprise.mjs';

const tmpRoot = await mkdtemp(
  path.join(os.tmpdir(), 'prepare-enterprise-dependencies-')
);

try {
  const webRoot = path.join(tmpRoot, 'web');
  const enterpriseWebRoot = path.join(tmpRoot, 'enterprise-web');
  const packageRoot = path.join(
    webRoot,
    'node_modules',
    '@ant-design',
    'icons'
  );
  const enterpriseSource = path.join(
    enterpriseWebRoot,
    'src',
    'app',
    'alarm',
    'incidents'
  );

  await fs.ensureDir(packageRoot);
  await fs.ensureDir(enterpriseSource);
  await writeFile(
    path.join(packageRoot, 'package.json'),
    JSON.stringify({ name: '@ant-design/icons', version: '0.0.0-test' })
  );

  const linked = await prepareEnterpriseDependencyLink({
    webRoot,
    enterpriseWebRoot,
  });

  assert.equal(linked, true);
  assert.equal(
    await fs.realpath(path.join(enterpriseWebRoot, 'node_modules')),
    await fs.realpath(path.join(webRoot, 'node_modules'))
  );

  const requireFromEnterprise = createRequire(
    path.join(enterpriseSource, 'dependency-probe.cjs')
  );
  assert.equal(
    await fs.realpath(
      requireFromEnterprise.resolve('@ant-design/icons/package.json')
    ),
    await fs.realpath(path.join(packageRoot, 'package.json'))
  );

  await fs.remove(path.join(enterpriseWebRoot, 'node_modules'));
  await fs.ensureDir(path.join(enterpriseWebRoot, 'node_modules'));
  await assert.rejects(
    prepareEnterpriseDependencyLink({ webRoot, enterpriseWebRoot }),
    /must be a generated symbolic link/,
  );

  console.log('prepare-enterprise dependency link ok');
} finally {
  await rm(tmpRoot, { recursive: true, force: true });
}
