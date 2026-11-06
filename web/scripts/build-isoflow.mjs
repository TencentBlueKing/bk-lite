#!/usr/bin/env node
// 在 packages/isoflow 目录执行它自己的 build 脚本。
// 该目录不是 workspace 包，webpack / tsc / tsc-alias 来自 web 根的 devDependencies。

import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isoflowDir = path.join(webRoot, 'packages', 'isoflow');
const { scripts } = require(path.join(isoflowDir, 'package.json'));

if (!scripts?.build) {
  throw new Error('packages/isoflow/package.json 缺少 scripts.build');
}

execSync(scripts.build, {
  cwd: isoflowDir,
  stdio: 'inherit',
  env: {
    ...process.env,
    PATH: `${path.join(webRoot, 'node_modules', '.bin')}${path.delimiter}${process.env.PATH ?? ''}`,
  },
});
