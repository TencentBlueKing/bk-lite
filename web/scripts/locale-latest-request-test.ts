import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface LatestRequestGuard {
  begin: () => number;
  commitIfCurrent: (requestId: number, commit: () => void) => boolean;
  invalidate: () => void;
}

type GuardFactory = () => LatestRequestGuard;

let createLatestRequestGuard: GuardFactory | undefined;
try {
  ({ createLatestRequestGuard } = await import('../src/context/latestRequestGuard.ts'));
} catch {
  // RED 阶段模块尚不存在，由下方行为断言给出明确失败。
}

assert.equal(
  typeof createLatestRequestGuard,
  'function',
  '应提供可复用的 latest request guard',
);

const guard = createLatestRequestGuard!();
const commits: string[] = [];
const olderRequest = guard.begin();
const latestRequest = guard.begin();

assert.equal(
  guard.commitIfCurrent(olderRequest, () => commits.push('older')),
  false,
  '旧请求不得提交状态',
);
assert.equal(
  guard.commitIfCurrent(latestRequest, () => commits.push('latest')),
  true,
  '最新请求应提交状态',
);
assert.deepEqual(commits, ['latest']);

guard.invalidate();
assert.equal(
  guard.commitIfCurrent(latestRequest, () => commits.push('after-unmount')),
  false,
  'Provider 卸载后在途请求不得提交状态',
);

const here = dirname(fileURLToPath(import.meta.url));
const localeSource = readFileSync(resolve(here, '../src/context/locale.tsx'), 'utf8');
const menusSource = readFileSync(resolve(here, '../src/context/menus.tsx'), 'utf8');

for (const [name, source, setter] of [
  ['LocaleProvider', localeSource, 'setMessages'],
  ['MenusProvider', menusSource, 'setConfigMenus'],
] as const) {
  assert.match(source, /createLatestRequestGuard/, `${name} 应创建 latest request guard`);
  assert.match(source, /requestGuard\.begin\(\)/, `${name} 应为每次请求生成代次`);
  assert.match(
    source,
    new RegExp(`requestGuard\\.commitIfCurrent\\([\\s\\S]*?${setter}\\(`),
    `${name} 只能让最新请求提交 ${setter}`,
  );
  assert.match(
    source,
    /return\s*\(\)\s*=>\s*requestGuard\.invalidate\(\)/,
    `${name} 卸载时应使在途请求失效`,
  );
}

assert.match(
  menusSource,
  /requestGuard\.commitIfCurrent\([\s\S]*?setLoading\(false\)/,
  'MenusProvider 只能由最新请求结束 loading',
);

console.log('locale latest request test passed');
