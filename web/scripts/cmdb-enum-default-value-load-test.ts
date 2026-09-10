import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  canSubmitEnumDefaultValue,
  getAttributeEnumOptionIds,
  normalizeDefaultValue,
  resolveEnumDefaultValue,
  sanitizeDefaultValue,
} from '../src/app/cmdb/utils/enumDefaultValue';

const root = process.cwd();
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');

const utilSource = read('src/app/cmdb/utils/enumDefaultValue.ts');
const modalSource = read(
  'src/app/cmdb/(pages)/assetManage/management/detail/attributes/attributesModal.tsx',
);
const attributesPageSource = read(
  'src/app/cmdb/(pages)/assetManage/management/detail/attributes/page.tsx',
);
const zhCmdb = JSON.parse(read('src/app/cmdb/locales/zh.json'));
const zhCommon = JSON.parse(read('src/locales/zh.json'));
const menu = JSON.parse(read('src/app/cmdb/constants/menu.json'));

const managementMenu = (menu.zh as Array<{ title: string; children?: Array<{ title: string; children?: Array<{ title: string }> }> }>).find(
  (item) => item.title === '管理',
);
assert.ok(managementMenu, '菜单应包含「管理」');
const modelMenu = managementMenu?.children?.find((item) => item.title === '模型管理');
assert.ok(modelMenu, '菜单应包含「管理」→「模型管理」');
assert.ok(
  modelMenu?.children?.some((item) => item.title === '属性'),
  '菜单应包含「管理」→「模型管理」→「属性」',
);

assert.equal(zhCmdb.Model.addAttribute, '添加属性');
assert.equal(zhCmdb.Model.editAttribute, '编辑属性');
assert.equal(zhCmdb.Model.defaultValue, '默认值');
assert.equal(zhCmdb.Model.attributes, '属性');
assert.equal(zhCmdb.PublicEnumLibrary.enumRuleType, '选项来源');
assert.equal(zhCmdb.PublicEnumLibrary.enumRuleTypePublicLibrary, '公共选项库');
assert.equal(zhCommon.common.edit, '编辑');
assert.equal(zhCommon.common.confirm, '确认');
assert.equal(zhCommon.common.cancel, '取消');

assert.match(attributesPageSource, /Model\.addAttribute/);
assert.match(attributesPageSource, /Model\.editAttribute/);
assert.match(attributesPageSource, /common\.edit/);
assert.match(modalSource, /Model\.defaultValue/);
assert.match(modalSource, /PublicEnumLibrary\.enumRuleTypePublicLibrary/);
assert.match(modalSource, /common\.confirm/);
assert.match(modalSource, /common\.cancel/);

assert.match(
  utilSource,
  /export type PublicEnumLibraryLoadState = 'unloaded' \| 'ready' \| 'failed'/,
  '源码必须区分公共枚举库未加载 / ready / failed',
);
assert.match(utilSource, /export const resolveEnumDefaultValue/);
assert.match(utilSource, /export const canSubmitEnumDefaultValue/);
assert.match(
  utilSource,
  /publicLibraryLoadState !== 'ready'/,
  '仅 ready 后才对公共库默认值做破坏性过滤',
);

assert.match(modalSource, /publicLibraryLoadState/);
assert.match(modalSource, /setPublicLibraryLoadState\('unloaded'\)/);
assert.match(modalSource, /setPublicLibraryLoadState\('ready'\)/);
assert.match(modalSource, /setPublicLibraryLoadState\('failed'\)/);
assert.match(modalSource, /resolveEnumDefaultValue/);
assert.match(modalSource, /canSubmitEnumDefaultValue/);
assert.doesNotMatch(
  modalSource,
  /\.catch\(\(\) => \{\s*setPublicLibraries\(\[\]\);/s,
  'catch 不得把失败当成已加载空库',
);
assert.match(
  modalSource,
  /getPublicEnumLibraries\(\)/,
  'getPublicEnumLibraries 调用签名不得改变',
);
assert.match(
  modalSource,
  /updateModelAttr\(params\.model_id!, requestParams\)/,
  'updateModelAttr 调用签名不得改变',
);

const library = {
  library_id: 'lib-status',
  name: '状态',
  options: [
    { id: 'online', name: '在线' },
    { id: 'offline', name: '离线' },
  ],
};

const optionIdsOf = (libraries: typeof library[]) =>
  getAttributeEnumOptionIds({
    enumRuleType: 'public_library',
    publicLibraryId: library.library_id,
    publicLibraries: libraries,
    enumList: [],
  });

const syncForm = (
  candidate: unknown,
  libraries: typeof library[],
  loadState: 'unloaded' | 'ready' | 'failed',
) =>
  resolveEnumDefaultValue({
    candidate,
    validOptionIds: optionIdsOf(libraries),
    selectMode: 'single',
    enumRuleType: 'public_library',
    publicLibraryLoadState: loadState,
  });

const submitForm = (
  candidate: unknown,
  libraries: typeof library[],
  loadState: 'unloaded' | 'ready' | 'failed',
) => {
  if (
    !canSubmitEnumDefaultValue({
      enumRuleType: 'public_library',
      publicLibraryLoadState: loadState,
    })
  ) {
    return {
      submitted: false as const,
      defaultValue: normalizeDefaultValue(candidate),
    };
  }
  return {
    submitted: true as const,
    defaultValue: syncForm(candidate, libraries, loadState),
  };
};

assert.deepEqual(
  sanitizeDefaultValue(['online'], optionIdsOf([]), 'single'),
  [],
  '未加载空选项列表会把已存默认值清掉，这是必须避开的破坏性过滤',
);

assert.deepEqual(
  syncForm(['online'], [], 'unloaded'),
  ['online'],
  '公共库未加载时不得清掉已存默认值',
);

const afterDelay = syncForm(syncForm(['online'], [], 'unloaded'), [library], 'ready');
assert.deepEqual(afterDelay, ['online'], '库延迟返回后合法 ID 仍在');

const keptInvalidWhileLoading = syncForm(['deleted-id'], [], 'unloaded');
assert.deepEqual(keptInvalidWhileLoading, ['deleted-id'], '非法 ID 在加载完成前应保留');
assert.deepEqual(
  syncForm(keptInvalidWhileLoading, [library], 'ready'),
  [],
  '非法 ID 在加载完成后才过滤',
);

assert.deepEqual(syncForm([], [], 'unloaded'), [], '用户显式清空后，未加载阶段保持空');
assert.deepEqual(syncForm([], [library], 'ready'), [], '用户显式清空后，加载完成仍保持空');

const failedKeep = syncForm(['online'], [], 'failed');
assert.deepEqual(failedKeep, ['online'], '加载失败必须保留候选默认值');
assert.deepEqual(submitForm(['online'], [], 'failed'), {
  submitted: false,
  defaultValue: ['online'],
});
assert.equal(
  canSubmitEnumDefaultValue({
    enumRuleType: 'public_library',
    publicLibraryLoadState: 'unloaded',
  }),
  false,
);
assert.equal(
  canSubmitEnumDefaultValue({
    enumRuleType: 'public_library',
    publicLibraryLoadState: 'ready',
  }),
  true,
);
assert.equal(
  canSubmitEnumDefaultValue({
    enumRuleType: 'custom',
    publicLibraryLoadState: 'unloaded',
  }),
  true,
);

assert.deepEqual(
  resolveEnumDefaultValue({
    candidate: ['gone', 'keep'],
    validOptionIds: ['keep'],
    selectMode: 'multiple',
    enumRuleType: 'custom',
    publicLibraryLoadState: 'unloaded',
  }),
  ['keep'],
  '自定义枚举仍应立即过滤非法选项',
);

console.log('cmdb-enum-default-value-load-test: ok');
