import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const read = (relativePath: string) =>
  fs.readFileSync(path.join(root, relativePath), 'utf8');

const configurePage = read(
  'src/app/monitor/(pages)/integration/list/detail/configure/page.tsx'
);
const api = read('src/app/monitor/api/integration.ts');
const types = read('src/app/monitor/types/integration.ts');
const k3sDir =
  'src/app/monitor/(pages)/integration/list/detail/configure/k3s';
const k3sSources = [
  'k3sConfiguration.tsx',
  'accessConfig.tsx',
  'collectorInstall.tsx',
  'commonIssuesDrawer.tsx',
]
  .map((file) => read(`${k3sDir}/${file}`))
  .join('\n');

assert.match(configurePage, /collectType === 'k3s'/);
assert.match(configurePage, /<K3sConfiguration/);
assert.match(api, /createK3sInstance/);
assert.match(api, /\/monitor\/api\/k3s_onboarding\/create_instance\//);
assert.match(api, /\/monitor\/api\/k3s_onboarding\/install_command\//);
assert.match(api, /\/monitor\/api\/k3s_onboarding\/verify\//);
assert.match(types, /interface K3sVerificationResult/);
assert.doesNotMatch(k3sSources, /from ['"].*\/k8s\//);
assert.doesNotMatch(
  k3sSources,
  /createK8sInstance|getK8sCommand|checkCollectStatus/
);
assert.doesNotMatch(k3sSources, /name=["']interval["']/);
assert.doesNotMatch(k3sSources, /\bcurl\s+-k\b|--insecure/);
assert.match(k3sSources, /signals\.cluster/);
assert.match(k3sSources, /signals\.container/);
assert.match(k3sSources, /signals\.node/);
assert.match(k3sSources, /monitor\.integrations\.k3s/);

console.log('K3S onboarding contract passed');
