import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { computeVisibleCapabilityTagCount } from '../src/app/system-manager/utils/integrationCenter';

const page = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/page.tsx', import.meta.url),
  'utf8',
);
const modal = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/CreateIntegrationInstanceModal.tsx', import.meta.url),
  'utf8',
);
const tags = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/ProviderCapabilityTags.tsx', import.meta.url),
  'utf8',
);
const zh = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'));
const en = JSON.parse(readFileSync(new URL('../src/app/system-manager/locales/en.json', import.meta.url), 'utf8'));

assert.equal(computeVisibleCapabilityTagCount([40, 40, 40], 140, 28), 3);
assert.equal(computeVisibleCapabilityTagCount([54, 54, 54, 54], 208, 28), 3);
assert.equal(computeVisibleCapabilityTagCount([54, 54, 54, 54], 300, 28), 4);
assert.equal(computeVisibleCapabilityTagCount([120, 84, 120, 110], 208, 28), 1);
assert.equal(computeVisibleCapabilityTagCount([40, 40, 40, 40, 40, 40], 208, 28), 4);
assert.equal(computeVisibleCapabilityTagCount([200, 40], 80, 28), 1);
assert.equal(computeVisibleCapabilityTagCount([], 200, 28), 0);
assert.equal(computeVisibleCapabilityTagCount([40], 0, 28), 0);

assert.doesNotMatch(tags, /grid-cols-2/);
assert.match(tags, /ResizeObserver/);
assert.match(tags, /\+\{hiddenCount\}/);
assert.match(tags, /hiddenTags\.map/);
assert.doesNotMatch(tags, /hiddenTags\.map\(\(tag\) => tag\.label\)\.join/);

assert.equal(zh.system.integrationCenter.createInstanceTitle, '添加集成系统');
assert.equal(en.system.integrationCenter.createInstanceTitle, 'Add Integration System');
assert.match(modal, /createInstanceTitle/);
assert.match(modal, /ProviderCapabilityTags/);
assert.match(modal, /tagList:\s*\[\]/);
assert.doesNotMatch(modal, /tagList:\s*provider\.capabilities/);
assert.match(modal, /filterOptions=\{capabilityFilterOptions\}/);
assert.match(modal, /changeFilter=\{\(keys\) => setCapabilityFilters\(keys \|\| \[\]\)\}/);
assert.doesNotMatch(modal, /search=\{false\}/);
assert.doesNotMatch(modal, /Input\.Search/);
assert.doesNotMatch(modal, /showSearch/);
assert.match(modal, /filterIntegrationProvidersByQuery\(cards, '', capabilityFilters, t\)/);
assert.doesNotMatch(modal, /applySearchFilter/);
assert.doesNotMatch(modal, /onSearch=\{setProviderSearch\}/);
assert.match(page, /ProviderCapabilityTags/);
assert.match(page, /align="end"/);
assert.doesNotMatch(page, /flex-wrap justify-end/);

console.log('integration-center create modal presentation contract passed');
