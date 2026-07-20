import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  applyTreeExpansionPreferenceOperation,
  buildGroupKey,
  createTreeExpansionPreferenceState,
  getAssetModelTreeStorageKey,
  getClassificationIdFromGroupKey,
  getExpandedGroupKeys,
  readCollapsedClassificationIds,
  reconcileTreeExpansionPreference,
  recordTreeExpansionPreferenceWrite,
  transitionTreeExpansionSearch,
  updateCollapsedClassificationIds,
  writeCollapsedClassificationIds,
} from '../src/app/cmdb/(pages)/assetData/treeExpansionPreference';

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

const storage = new MemoryStorage();
const validIds = ['cloud', 'host', 'middleware'];

assert.equal(buildGroupKey('cloud'), 'group:cloud');
assert.equal(getClassificationIdFromGroupKey('group:cloud'), 'cloud');
assert.equal(getClassificationIdFromGroupKey('host'), null);
assert.equal(getAssetModelTreeStorageKey(1), 'bk-lite:cmdb:asset-model-tree:v1:1');
assert.notEqual(getAssetModelTreeStorageKey(1), getAssetModelTreeStorageKey(2));

assert.deepEqual(
  readCollapsedClassificationIds(storage, 1, validIds),
  [],
  '无缓存时应回退为全部展开'
);

storage.setItem(
  getAssetModelTreeStorageKey(1),
  JSON.stringify({ collapsedClassificationIds: ['cloud', 'deleted', 3, 'cloud'] })
);
assert.deepEqual(
  readCollapsedClassificationIds(storage, 1, validIds),
  ['cloud'],
  '应去重并过滤已删除分类和非法值'
);
assert.deepEqual(
  getExpandedGroupKeys([...validIds, 'new-category'], ['cloud']),
  ['group:host', 'group:middleware', 'group:new-category'],
  '后台新增分类应默认展开'
);

assert.deepEqual(
  updateCollapsedClassificationIds(validIds, ['cloud'], 'host', false),
  ['cloud', 'host'],
  '收起单个分类时应加入缓存集合'
);
assert.deepEqual(
  updateCollapsedClassificationIds(validIds, ['cloud', 'host'], 'cloud', true),
  ['host'],
  '展开单个分类时应移出缓存集合'
);
assert.deepEqual(
  updateCollapsedClassificationIds(validIds, ['cloud'], 'deleted', false),
  ['cloud'],
  '未知分类操作应被忽略'
);

storage.setItem(getAssetModelTreeStorageKey(2), '{bad json');
assert.deepEqual(readCollapsedClassificationIds(storage, 2, validIds), []);
storage.setItem(
  getAssetModelTreeStorageKey(2),
  JSON.stringify({ collapsedClassificationIds: 'cloud' })
);
assert.deepEqual(readCollapsedClassificationIds(storage, 2, validIds), []);

assert.equal(
  writeCollapsedClassificationIds(storage, 1, ['host']),
  true,
  '写入成功时应返回 true'
);
assert.deepEqual(JSON.parse(storage.getItem(getAssetModelTreeStorageKey(1)) || '{}'), {
  collapsedClassificationIds: ['host'],
});

const throwingStorage = {
  getItem(): string | null {
    throw new Error('blocked');
  },
  setItem(): void {
    throw new Error('blocked');
  },
};
assert.deepEqual(readCollapsedClassificationIds(throwingStorage, 1, validIds), []);
assert.equal(
  writeCollapsedClassificationIds(throwingStorage, 1, ['cloud']),
  false,
  '写入失败时应返回 false'
);
assert.deepEqual(readCollapsedClassificationIds(null, 1, validIds), []);
assert.equal(writeCollapsedClassificationIds(null, 1, ['cloud']), false);

let preferenceState = createTreeExpansionPreferenceState();
let transition = applyTreeExpansionPreferenceOperation(
  preferenceState,
  null,
  validIds,
  ['cloud']
);
preferenceState = transition.state;
assert.equal(transition.writeRequest, null, '匿名操作不应写入共享缓存');
assert.deepEqual(preferenceState.anonymousCollapsedClassificationIds, ['cloud']);

transition = reconcileTreeExpansionPreference(
  preferenceState,
  'user-a',
  validIds,
  ['host']
);
preferenceState = transition.state;
assert.deepEqual(transition.collapsedClassificationIds, ['cloud']);
assert.deepEqual(transition.writeRequest, {
  userId: 'user-a',
  collapsedClassificationIds: ['cloud'],
});
assert.equal(
  preferenceState.anonymousCollapsedClassificationIds,
  null,
  '首个用户接收匿名偏好后应转入该用户内存'
);

preferenceState = recordTreeExpansionPreferenceWrite(preferenceState, 'user-a', false);
assert.deepEqual(preferenceState.dirtyUserIds, ['user-a']);
transition = reconcileTreeExpansionPreference(preferenceState, null, validIds, []);
preferenceState = transition.state;
assert.equal(preferenceState.loadedUserId, 'user-a', 'userId 短空不得清除已加载用户');
assert.deepEqual(transition.collapsedClassificationIds, ['cloud']);
assert.equal(transition.writeRequest, null);

transition = reconcileTreeExpansionPreference(
  preferenceState,
  'user-a',
  validIds,
  ['middleware']
);
preferenceState = transition.state;
assert.deepEqual(transition.collapsedClassificationIds, ['cloud']);
assert.deepEqual(
  transition.writeRequest,
  { userId: 'user-a', collapsedClassificationIds: ['cloud'] },
  '同一用户恢复时应保留内存 dirty 并重试，而不是被旧缓存覆盖'
);

transition = reconcileTreeExpansionPreference(
  preferenceState,
  'user-b',
  validIds,
  ['host']
);
preferenceState = transition.state;
assert.deepEqual(transition.collapsedClassificationIds, ['host']);
assert.equal(transition.writeRequest, null, '用户 A 的 dirty 绝不能写入用户 B');
assert.deepEqual(preferenceState.dirtyUserIds, ['user-a']);
assert.deepEqual(preferenceState.collapsedClassificationIdsByUser['user-a'], ['cloud']);

transition = reconcileTreeExpansionPreference(
  preferenceState,
  'user-a',
  ['cloud', 'middleware', 'new-category'],
  []
);
preferenceState = transition.state;
assert.deepEqual(transition.collapsedClassificationIds, ['cloud']);
assert.deepEqual(transition.expandedKeys, [
  'group:middleware',
  'group:new-category',
]);
assert.deepEqual(transition.writeRequest, {
  userId: 'user-a',
  collapsedClassificationIds: ['cloud'],
});

transition = applyTreeExpansionPreferenceOperation(
  preferenceState,
  'user-a',
  ['cloud', 'middleware', 'new-category'],
  ['cloud', 'deleted']
);
preferenceState = transition.state;
assert.deepEqual(transition.collapsedClassificationIds, ['cloud']);
assert.deepEqual(transition.writeRequest, {
  userId: 'user-a',
  collapsedClassificationIds: ['cloud'],
});

const searchTransition = transitionTreeExpansionSearch(
  preferenceState,
  'user-a',
  ['cloud', 'middleware', 'new-category'],
  ['group:cloud', 'cloud-model']
);
preferenceState = searchTransition.state;
assert.deepEqual(searchTransition.expandedKeys, ['group:cloud', 'cloud-model']);
assert.equal(searchTransition.writeRequest, null, '搜索自动展开不得写入偏好');
const clearSearchTransition = transitionTreeExpansionSearch(
  preferenceState,
  'user-a',
  ['cloud', 'middleware', 'new-category'],
  null
);
assert.deepEqual(
  clearSearchTransition.expandedKeys,
  ['group:middleware', 'group:new-category'],
  '清空搜索应恢复当前用户内存偏好'
);
assert.equal(clearSearchTransition.state.searchActive, false);

let loadedUserState = createTreeExpansionPreferenceState();
let loadedUserTransition = reconcileTreeExpansionPreference(
  loadedUserState,
  'user-a',
  validIds,
  ['cloud']
);
loadedUserState = loadedUserTransition.state;
loadedUserTransition = applyTreeExpansionPreferenceOperation(
  loadedUserState,
  null,
  validIds,
  ['middleware']
);
loadedUserState = loadedUserTransition.state;
assert.equal(
  loadedUserTransition.writeRequest,
  null,
  'userId 短空期间不得立即写缓存'
);
assert.deepEqual(
  loadedUserState.collapsedClassificationIdsByUser['user-a'],
  ['middleware'],
  'userId 短空期间的操作应归属于已加载用户 A'
);
assert.deepEqual(loadedUserState.dirtyUserIds, ['user-a']);
assert.equal(loadedUserState.anonymousCollapsedClassificationIds, null);

loadedUserTransition = reconcileTreeExpansionPreference(
  loadedUserState,
  'user-b',
  validIds,
  ['host']
);
loadedUserState = loadedUserTransition.state;
assert.deepEqual(
  loadedUserTransition.collapsedClassificationIds,
  ['host'],
  '用户 B 应恢复自己的缓存'
);
assert.equal(
  loadedUserTransition.writeRequest,
  null,
  '用户 B 不应收到用户 A 短空期间操作的写请求'
);
assert.deepEqual(loadedUserState.dirtyUserIds, ['user-a']);

const pageSource = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/page.tsx'),
  'utf8'
);
const styleSource = readFileSync(
  resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/index.module.scss'),
  'utf8'
);

assert.match(pageSource, /onExpand=\{handleTreeExpand\}/);
assert.match(pageSource, /onClick=\{handleExpandAllTreeGroups\}/);
assert.match(pageSource, /onClick=\{handleCollapseAllTreeGroups\}/);
assert.match(pageSource, /PlusSquareOutlined/);
assert.match(pageSource, /MinusSquareOutlined/);
assert.doesNotMatch(pageSource, /ExpandOutlined/);
assert.doesNotMatch(pageSource, /CompressOutlined/);
assert.match(pageSource, /icon=\{<PlusSquareOutlined aria-hidden="true" \/>\}/);
assert.match(pageSource, /icon=\{<MinusSquareOutlined aria-hidden="true" \/>\}/);
assert.match(
  pageSource,
  /<div className=\{assetDataStyle\.treeSearchActions\}>[\s\S]*onClick=\{handleExpandAllTreeGroups\}[\s\S]*onClick=\{handleCollapseAllTreeGroups\}[\s\S]*<\/div>/
);
assert.match(pageSource, /t\('common\.expandAll'\)/);
assert.match(pageSource, /t\('common\.collapseAll'\)/);
assert.match(pageSource, /aria-label=\{t\('common\.expandAll'\)\}/);
assert.match(pageSource, /aria-label=\{t\('common\.collapseAll'\)\}/);
assert.match(pageSource, /readCollapsedClassificationIds\(/);
assert.match(pageSource, /writeCollapsedClassificationIds\(/);
assert.match(pageSource, /preferenceStateRef/);
assert.match(pageSource, /reconcileTreeExpansionPreference\(/);
assert.match(pageSource, /recordTreeExpansionPreferenceWrite\(/);
assert.match(pageSource, /transitionTreeExpansionSearch\(/);
assert.doesNotMatch(pageSource, /isTreeSearchActiveRef/);
assert.match(styleSource, /\.treeSearchInput\s*\{/);
assert.match(
  styleSource,
  /\.groupSelector\s*\{[\s\S]*display:\s*flex;[\s\S]*flex-direction:\s*column;[\s\S]*overflow:\s*hidden;/
);
assert.match(
  styleSource,
  /\.treeSearchWrapper\s*\{[\s\S]*flex:\s*none;[\s\S]*flex-direction:\s*column;/
);
assert.match(
  styleSource,
  /\.treeSearchActions\s*\{[\s\S]*display:\s*flex;[\s\S]*justify-content:\s*flex-end;[\s\S]*gap:\s*4px;[\s\S]*margin-top:\s*4px;/
);
assert.match(
  styleSource,
  /\.treeWrapper\s*\{[\s\S]*flex:\s*1;[\s\S]*min-height:\s*0;[\s\S]*height:\s*auto;[\s\S]*overflow:\s*auto;/
);
assert.doesNotMatch(styleSource, /calc\(100%\s*-\s*44px\)/);

console.log('PASS cmdb-asset-model-tree-expansion');
