import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  computeVisibleCapabilityTagCount,
  DEFAULT_INTEGRATION_PROVIDER_ICON,
  resolveIntegrationProviderIcon,
} from '../src/app/system-manager/utils/integrationCenter';

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

assert.equal(resolveIntegrationProviderIcon('wecom'), 'wecom');
assert.equal(resolveIntegrationProviderIcon('acmedemo'), DEFAULT_INTEGRATION_PROVIDER_ICON);
assert.equal(DEFAULT_INTEGRATION_PROVIDER_ICON, 'default-provider');

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

assert.doesNotMatch(page, /provider-packs/);
assert.doesNotMatch(page, /provider_pack/);
assert.doesNotMatch(page, /Provider 包/);

const menu = JSON.parse(readFileSync(new URL('../src/app/system-manager/constants/menu.json', import.meta.url), 'utf8'));
const zhIntegration = menu.zh.find((item) => item.name === 'integration_center');
const enIntegration = menu.en.find((item) => item.name === 'integration_center');
assert.equal(
  zhIntegration.children.every((child) => !child.name || child.name !== 'provider_packs'),
  true,
);
assert.equal(
  enIntegration.children.every((child) => !child.name || child.name !== 'provider_packs'),
  true,
);
const enterpriseMenus = JSON.parse(
  readFileSync(new URL('../../enterprise/web/manifests/menus.json', import.meta.url), 'utf8'),
);
const zhPackPatch = enterpriseMenus.zh_patches.find((patch) => patch.target === 'integration_center');
const enPackPatch = enterpriseMenus.en_patches.find((patch) => patch.target === 'integration_center');
const zhProviderPacks = zhPackPatch.children.find((child) => child.name === 'provider_packs');
const enProviderPacks = enPackPatch.children.find((child) => child.name === 'provider_packs');
const zhInstances = zhPackPatch.children.find((child) => child.name === 'integration_instances');
const enInstances = enPackPatch.children.find((child) => child.name === 'integration_instances');
assert.equal(zhProviderPacks?.title, '集成类型');
assert.equal(enProviderPacks?.title, 'Integration Types');
assert.equal(zh.system.integrationCenter.providerPacks.title, '集成类型');
assert.equal(en.system.integrationCenter.providerPacks.title, 'Integration Types');
assert.equal(zhProviderPacks?.superuserOnly, undefined);
assert.equal(enProviderPacks?.superuserOnly, undefined);
assert.equal(zhProviderPacks?.withParentPermission, true);
assert.equal(enProviderPacks?.withParentPermission, true);
assert.equal(zhInstances?.withParentPermission, true);
assert.equal(enInstances?.withParentPermission, true);
assert.equal(zh.system.integrationCenter.providerPacks.superuserOnly, undefined);
assert.equal(en.system.integrationCenter.providerPacks.superuserOnly, undefined);
assert.ok(zhPackPatch.children.some((child) => child.url === '/system-manager/integration-center'));
assert.doesNotMatch(JSON.stringify(zhPackPatch.children), /replace=true/);
assert.equal(zh.system.integrationCenter.providerPacks.uninstall, '卸载');
assert.equal(en.system.integrationCenter.providerPacks.uninstall, 'Uninstall');
assert.match(zh.system.integrationCenter.providerPacks.uninstallConfirmContent, /下线该类型/);
assert.match(en.system.integrationCenter.providerPacks.uninstallConfirmContent, /offline/);
assert.match(zh.system.integrationCenter.providerPacks.loadFailed, /加载失败/);
assert.match(en.system.integrationCenter.providerPacks.loadFailed, /Load failed/);
assert.equal(zh.system.integrationCenter.providerUnavailable, 'Provider 不可用');
assert.equal(en.system.integrationCenter.providerUnavailable, 'Provider is unavailable');

const packPage = readFileSync(
  new URL('../../enterprise/web/src/app/system-manager/integration-center/provider-packs/page.tsx', import.meta.url),
  'utf8',
);
const packApi = readFileSync(
  new URL('../../enterprise/web/src/app/system-manager/api/provider_pack/index.ts', import.meta.url),
  'utf8',
);
assert.match(packPage, /PermissionWrapper/);
assert.doesNotMatch(packPage, /isSuperUser/);
assert.doesNotMatch(packPage, /superuserOnly/);
assert.match(packPage, /source === 'uploaded'/);
assert.match(packPage, /replaceConfirmContent/);
assert.match(packPage, /uninstall/);
assert.match(packPage, /Upload\.Dragger/);
assert.match(packPage, /uploadModalHint/);
assert.doesNotMatch(packPage, /dataIndex: 'pack_revision'/);
assert.doesNotMatch(packPage, /dataIndex: 'author_version'/);
assert.match(packApi, /formData.append\('replace', 'true'\)/);
assert.match(packApi, /uninstallProviderPack/);
assert.match(packApi, /readProviderPackConflict/);
assert.equal(
  zh.system.integrationCenter.providerPacks.replace,
  '更换',
);
assert.match(
  zh.system.integrationCenter.providerPacks.replaceConfirmContent,
  /覆盖当前已装的该类型/,
);
assert.match(
  zh.system.integrationCenter.providerPacks.replaceConfirmContent,
  /测通前该实例的登录、用户同步和 IM 将不可用/,
);
assert.match(zh.system.integrationCenter.providerPacks.uploadModalHint, /10MB/);
assert.match(
  en.system.integrationCenter.providerPacks.replaceConfirmContent,
  /Login, user sync, and IM/,
);
assert.equal(zh.system.integrationCenter.providerPacks.builtinNoActions, '内置类型不可更换或卸载');
assert.equal(en.system.integrationCenter.providerPacks.builtinNoActions, 'Built-in types cannot be replaced or uninstalled');
assert.match(packPage, /<Tag color="success">\{t\('system\.integrationCenter\.providerPacks\.loadLoaded'\)\}<\/Tag>/);
assert.match(packPage, /<span[\s\S]*?title=\{t\('system\.integrationCenter\.providerPacks\.builtinNoActions'\)\}[\s\S]*?>\s*--\s*<\/span>/);
assert.doesNotMatch(packPage, /record\.source === 'uploaded'[\s\S]*?:\s*null/);

console.log('integration-center create modal presentation contract passed');
