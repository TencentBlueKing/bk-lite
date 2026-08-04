import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const utils = readFileSync(new URL('../src/app/system-manager/utils/integrationCenter.ts', import.meta.url), 'utf8');
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.match(utils, /wecom:\s*['"]wecom['"]/);
assert.match(utils, /return t\(`system\.integrationCenter\.provider\.\$\{providerKey\}`,\s*providerKey\);/);
assert.equal(zh.system.integrationCenter.provider.wecom, '企业微信');
assert.equal(en.system.integrationCenter.provider.wecom, 'WeCom');

console.log('WeCom integration-center presentation contract passed');