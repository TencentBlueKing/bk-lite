#!/usr/bin/env node

/* eslint-disable @typescript-eslint/no-require-imports -- package 未启用 ESM，保留原脚本的 CommonJS 入口 */

const fs = require('fs');
const path = require('path');

const WEB_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_PATH = path.join(WEB_ROOT, 'pnpm-workspace.yaml');

function parseActiveApps(value) {
  if (!value?.trim()) {
    return ['*'];
  }

  const apps = value
    .split(',')
    .map(app => app.trim().replace(/[()]/g, ''))
    .filter(Boolean);

  if (apps.includes('*')) {
    return ['*'];
  }

  for (const app of apps) {
    if (!/^[a-z0-9][a-z0-9-]*$/i.test(app)) {
      throw new Error(`无效的应用名称: ${app}`);
    }
  }

  return apps.length > 0 ? [...new Set(apps)] : ['*'];
}

function updateWorkspacePackages(content, activeApps) {
  const newline = content.includes('\r\n') ? '\r\n' : '\n';
  const lines = content.split(/\r?\n/);
  const packagesStart = lines.findIndex(line => line.trim() === 'packages:');

  if (packagesStart === -1) {
    throw new Error('pnpm-workspace.yaml 缺少 packages 配置');
  }

  let packagesEnd = lines.length;
  for (let index = packagesStart + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() && !/^\s/.test(line) && /^[^#][^:]*:/.test(line)) {
      packagesEnd = index;
      break;
    }
  }

  const packageLines = activeApps.map(app =>
    app === '*' ? "  - 'src/app/*'" : `  - 'src/app/${app}'`
  );
  const suffix = lines.slice(packagesEnd);

  while (suffix[0] === '') {
    suffix.shift();
  }

  return [
    ...lines.slice(0, packagesStart),
    'packages:',
    ...packageLines,
    ...(suffix.length > 0 ? ['', ...suffix] : []),
  ].join(newline);
}

function main() {
  require('dotenv').config({ path: path.join(WEB_ROOT, '.env.local'), quiet: true });

  const activeApps = parseActiveApps(process.env.NEXTAPI_INSTALL_APP);
  const currentConfig = fs.readFileSync(WORKSPACE_PATH, 'utf8');
  const nextConfig = updateWorkspacePackages(currentConfig, activeApps);

  fs.writeFileSync(WORKSPACE_PATH, nextConfig);
  console.log(`Workspace 应用: ${activeApps.join(', ')}`);
  console.log(`已更新 ${WORKSPACE_PATH}`);
}

if (require.main === module) {
  main();
}

module.exports = {
  parseActiveApps,
  updateWorkspacePackages,
};
