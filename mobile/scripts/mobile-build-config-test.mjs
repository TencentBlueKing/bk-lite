import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  H5_BASE_PATH,
  resolveBuildSettings,
} from './mobile-build-config.mjs';

const projectRoot = new URL('../', import.meta.url);

async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}

test('H5 构建使用固定子路径并清空绝对 API 地址', () => {
  const settings = resolveBuildSettings({
    target: 'h5',
    env: {
      NEXT_PUBLIC_API_URL: 'https://stale.example.com',
      NEXT_PUBLIC_BASE_PATH: '/stale-path',
    },
  });

  assert.equal(settings.target, 'h5');
  assert.equal(settings.basePath, H5_BASE_PATH);
  assert.equal(settings.env.BK_MOBILE_BUILD_TARGET, 'h5');
  assert.equal(settings.env.NEXT_PUBLIC_BASE_PATH, H5_BASE_PATH);
  assert.equal(settings.env.NEXT_PUBLIC_API_URL, '');
});

test('构建目标须显式且有效', () => {
  assert.throws(
    () => resolveBuildSettings({ target: '', env: {} }),
    /须指定 Mobile 构建目标/,
  );
  assert.throws(
    () => resolveBuildSettings({ target: 'unknown', env: {} }),
    /不支持的 Mobile 构建目标/,
  );
});

test('Tauri 构建须提供绝对 API 地址', () => {
  assert.throws(
    () => resolveBuildSettings({ target: 'tauri', env: {} }),
    /NEXT_PUBLIC_API_URL/,
  );
  assert.throws(
    () => resolveBuildSettings({
      target: 'tauri',
      env: { NEXT_PUBLIC_API_URL: '/api' },
    }),
    /绝对 HTTP\(S\) 地址/,
  );
});

test('Tauri 构建拒绝外部明文 HTTP API 地址', () => {
  assert.throws(
    () => resolveBuildSettings({
      target: 'tauri',
      env: { NEXT_PUBLIC_API_URL: 'http://api.example.com' },
    }),
    /外部地址必须使用 HTTPS/,
  );

  assert.equal(
    resolveBuildSettings({
      target: 'tauri',
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8011' },
    }).env.NEXT_PUBLIC_API_URL,
    'http://127.0.0.1:8011',
  );
});

test('Tauri 构建从 API 地址派生 Rust 代理白名单', () => {
  const settings = resolveBuildSettings({
    target: 'tauri',
    env: { NEXT_PUBLIC_API_URL: 'https://bklite.example.com:8443/' },
  });

  assert.equal(settings.target, 'tauri');
  assert.equal(settings.basePath, '');
  assert.equal(settings.env.BK_MOBILE_BUILD_TARGET, 'tauri');
  assert.equal(settings.env.NEXT_PUBLIC_BASE_PATH, '');
  assert.equal(settings.env.NEXT_PUBLIC_API_URL, 'https://bklite.example.com:8443');
  assert.equal(settings.env.TAURI_ALLOWED_HOSTS, 'bklite.example.com:8443');
});

test('显式 Tauri 白名单可用于多后端场景', () => {
  const settings = resolveBuildSettings({
    target: 'tauri',
    env: {
      NEXT_PUBLIC_API_URL: 'https://bklite.example.com',
      TAURI_ALLOWED_HOSTS: 'bklite.example.com,files.example.com',
    },
  });

  assert.equal(
    settings.env.TAURI_ALLOWED_HOSTS,
    'bklite.example.com,files.example.com',
  );
});

test('Next 配置只消费构建脚本解析后的环境', async () => {
  const nextConfig = await readProjectFile('next.config.ts');
  const basePathUtility = await readProjectFile('src/utils/basePath.ts');

  assert.match(nextConfig, /BK_MOBILE_BUILD_TARGET/);
  assert.doesNotMatch(nextConfig, /BK_MOBILE_TARGET/);
  assert.doesNotMatch(nextConfig, /TAURI_DEV\b/);
  assert.doesNotMatch(nextConfig, /NEXT_PUBLIC_BASE_PATH\s*\|\|/);
  assert.doesNotMatch(basePathUtility, /NEXT_PUBLIC_BASE_PATH\s*\|\|/);
});

test('所有生产构建命令都显式声明目标', async () => {
  const packageJson = JSON.parse(await readProjectFile('package.json'));
  const tauriConfig = JSON.parse(await readProjectFile('src-tauri/tauri.conf.json'));

  assert.equal(packageJson.scripts.build, 'pnpm build:tauri');
  assert.equal(
    packageJson.scripts['build:tauri'],
    'node scripts/next-build.mjs --target tauri',
  );
  assert.equal(
    packageJson.scripts['build:h5'],
    'node scripts/next-build.mjs --target h5',
  );
  assert.equal(tauriConfig.build.beforeBuildCommand, 'pnpm build:tauri');
});

test('Tauri 启动入口统一加载并校验本地环境', async () => {
  const packageJson = JSON.parse(await readProjectFile('package.json'));
  const tauriCli = await readProjectFile('scripts/tauri-cli.mjs');
  const androidBuild = await readProjectFile('scripts/android-build.mjs');
  const androidBuildShell = await readProjectFile('scripts/android-build.sh');

  assert.equal(packageJson.scripts['dev:tauri'], 'node scripts/tauri-cli.mjs dev');
  assert.equal(packageJson.scripts['package:tauri'], 'node scripts/tauri-cli.mjs build');
  assert.match(tauriCli, /loadEnvConfig/);
  assert.match(tauriCli, /resolveBuildSettings\(\{ target: 'tauri'/);
  assert.match(androidBuild, /loadEnvConfig/);
  assert.match(androidBuild, /resolveBuildSettings\(\{ target: 'tauri'/);
  assert.doesNotMatch(androidBuildShell, /BK_MOBILE_TARGET/);
});

test('Tauri 白名单在打包时固化到 Rust 二进制', async () => {
  const apiProxy = await readProjectFile('src-tauri/src/api_proxy.rs');

  assert.match(apiProxy, /option_env!\("TAURI_ALLOWED_HOSTS"\)/);
});
