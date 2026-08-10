#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import nextEnv from '@next/env';

import { resolveBuildSettings } from './mobile-build-config.mjs';

const { loadEnvConfig } = nextEnv;
const args = process.argv.slice(2);

if (args.length === 0) {
  console.error('请指定 Tauri 命令，例如 dev 或 build');
  process.exit(1);
}

loadEnvConfig(process.cwd(), args[0] === 'dev');

let settings;
try {
  settings = resolveBuildSettings({ target: 'tauri', env: process.env });
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

const command = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';
const result = spawnSync(command, ['exec', 'tauri', ...args], {
  stdio: 'inherit',
  env: settings.env,
});

process.exit(result.status ?? 1);
