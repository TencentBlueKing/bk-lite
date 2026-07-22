#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import nextEnv from '@next/env';

import { resolveBuildSettings } from './mobile-build-config.mjs';

const { loadEnvConfig } = nextEnv;

function parseArgs(argv) {
  const args = { target: '' };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--target') {
      args.target = argv[index + 1] || '';
      index += 1;
    } else if (arg.startsWith('--target=')) {
      args.target = arg.slice('--target='.length);
    }
  }
  return args;
}

function main() {
  loadEnvConfig(process.cwd(), false);

  const { target } = parseArgs(process.argv.slice(2));
  let settings;

  try {
    settings = resolveBuildSettings({ target, env: process.env });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }

  const label = settings.target || 'default';
  const basePathLabel = settings.basePath || '(none)';

  console.log(`Building mobile Next target=${label}, basePath=${basePathLabel}`);

  const result = spawnSync('next', ['build', '--turbopack'], {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: settings.env,
  });

  process.exit(result.status ?? 1);
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isCli) {
  main();
}
