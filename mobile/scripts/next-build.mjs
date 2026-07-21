#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import nextEnv from '@next/env';

const { loadEnvConfig } = nextEnv;

export function normalizeBasePath(value) {
  if (!value) return '';
  const normalized = String(value).replace(/^\/|\/$/g, '');
  return normalized ? `/${normalized}` : '';
}

export function resolveBuildSettings({ target = '', env = process.env } = {}) {
  const buildTarget = target || env.BK_MOBILE_TARGET || '';
  const isH5 = buildTarget === 'h5';
  const isTauri = buildTarget === 'tauri';
  const inheritedBasePath = isTauri ? '' : env.NEXT_PUBLIC_BASE_PATH || '';
  const basePath = normalizeBasePath(inheritedBasePath || (isH5 ? '/mobile/h5' : ''));
  const resolvedEnv = { ...env };

  if (buildTarget) {
    resolvedEnv.BK_MOBILE_TARGET = buildTarget;
  } else {
    delete resolvedEnv.BK_MOBILE_TARGET;
  }

  if (basePath) {
    resolvedEnv.NEXT_PUBLIC_BASE_PATH = basePath;
  } else {
    delete resolvedEnv.NEXT_PUBLIC_BASE_PATH;
  }

  if (isH5) {
    resolvedEnv.NEXT_PUBLIC_API_URL = '';
  }

  if (isTauri && !resolvedEnv.NEXT_PUBLIC_API_URL) {
    throw new Error(
      'Tauri 构建需要配置 NEXT_PUBLIC_API_URL 为 Web/Nginx 网关地址，例如 https://bklite.example.com'
    );
  }

  return {
    basePath,
    target: buildTarget,
    env: resolvedEnv,
  };
}

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
