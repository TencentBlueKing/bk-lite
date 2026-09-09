import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface RelationField {
  attr_id: string;
}

type RelationFieldsCache = Record<string, RelationField[]>;

type PruneRelationFieldsCache = (
  prev: RelationFieldsCache,
  selectedModelIds: string[],
) => RelationFieldsCache;

const here = dirname(fileURLToPath(import.meta.url));
const utilPath = resolve(here, '../src/app/cmdb/utils/relationFieldsCache.ts');
const subscriptionFormPath = resolve(
  here,
  '../src/app/cmdb/components/subscription/subscriptionRuleForm.tsx',
);
const drawerFormPath = resolve(
  here,
  '../src/app/cmdb/components/cmdb-subscription-drawer/subscriptionRuleForm.tsx',
);

const REPRO_COPY = {
  menu: ['资产', '基础信息'],
  button: '订阅',
  modal: '新建规则',
  footer: ['保存并启用', '仅保存', '取消'],
  triggerType: '关联变化',
} as const;

async function loadPrune(): Promise<PruneRelationFieldsCache> {
  let loaded: { pruneRelationFieldsCache?: unknown } = {};
  try {
    loaded = await import('../src/app/cmdb/utils/relationFieldsCache.ts');
  } catch {
    // RED：关联字段缓存尚未抽出。
  }

  assert.equal(
    typeof loaded.pruneRelationFieldsCache,
    'function',
    '应抽出 pruneRelationFieldsCache',
  );
  return loaded.pruneRelationFieldsCache as PruneRelationFieldsCache;
}

function assertFormUsesSharedPrune(source: string, label: string) {
  assert.match(
    source,
    /from ['"]@\/app\/cmdb\/utils\/relationFieldsCache['"]/,
    `${label} 必须复用抽出的 relationFieldsCache`,
  );
  assert.match(
    source,
    /pruneRelationFieldsCache\(/,
    `${label} 必须调用 pruneRelationFieldsCache`,
  );
  assert.doesNotMatch(
    source,
    /setRelationFieldsByModel\(\{\}\)/,
    `${label} 空选择不得无条件 setRelationFieldsByModel({})`,
  );
  assert.doesNotMatch(
    source,
    /return next;/,
    `${label} prune 不得无条件 return next`,
  );
}

async function main() {
  assert.deepEqual(REPRO_COPY.menu, ['资产', '基础信息']);
  assert.equal(REPRO_COPY.button, '订阅');
  assert.equal(REPRO_COPY.modal, '新建规则');
  assert.deepEqual(REPRO_COPY.footer, ['保存并启用', '仅保存', '取消']);
  assert.equal(REPRO_COPY.triggerType, '关联变化');

  const pruneRelationFieldsCache = await loadPrune();

  const emptyPrev: RelationFieldsCache = {};
  const emptyFirst = pruneRelationFieldsCache(emptyPrev, []);
  const emptySecond = pruneRelationFieldsCache(emptyFirst, []);
  assert.equal(emptyFirst, emptyPrev, '挂载空配置不得写新对象');
  assert.equal(emptySecond, emptyFirst, '空配置连续 prune 必须返回同一引用');

  const fieldsA: RelationField[] = [{ attr_id: 'name' }];
  const fieldsB: RelationField[] = [{ attr_id: 'status' }];
  const cached: RelationFieldsCache = { modelA: fieldsA, modelB: fieldsB };
  const unchanged = pruneRelationFieldsCache(cached, ['modelA', 'modelB']);
  assert.equal(unchanged, cached, '已缓存配置键未变必须返回 prev');

  const stillCachedWhilePending = pruneRelationFieldsCache(cached, ['modelA', 'modelB', 'modelC']);
  assert.equal(stillCachedWhilePending, cached, '未缓存的新增模型不得在 prune 时换引用');

  const removed = pruneRelationFieldsCache(cached, ['modelA']);
  assert.notEqual(removed, cached, '删除已缓存模型必须写新对象');
  assert.deepEqual(Object.keys(removed), ['modelA']);
  assert.equal(removed.modelA, fieldsA, '保留模型字段引用不得被复制');

  const addedAfterFetch: RelationFieldsCache = { ...cached, modelC: [{ attr_id: 'id' }] };
  const afterAdd = pruneRelationFieldsCache(addedAfterFetch, ['modelA', 'modelB', 'modelC']);
  assert.equal(afterAdd, addedAfterFetch, '增模型后键未变的再次 prune 必须返回 prev');
  assert.notEqual(addedAfterFetch, cached, '增模型写入新对象后不得回写旧缓存');

  const cleared = pruneRelationFieldsCache(cached, []);
  assert.notEqual(cleared, cached, '从已缓存清空必须写新对象');
  assert.deepEqual(cleared, {});
  assert.equal(
    pruneRelationFieldsCache(cleared, []),
    cleared,
    '清空后的空缓存连续调用不得再换引用',
  );

  const subscriptionSource = readFileSync(subscriptionFormPath, 'utf8');
  const drawerSource = readFileSync(drawerFormPath, 'utf8');
  assertFormUsesSharedPrune(subscriptionSource, 'subscription/subscriptionRuleForm');
  assertFormUsesSharedPrune(drawerSource, 'cmdb-subscription-drawer/subscriptionRuleForm');

  const utilSource = readFileSync(utilPath, 'utf8');
  assert.match(utilSource, /export function pruneRelationFieldsCache/, '必须导出 pruneRelationFieldsCache');

  console.log('cmdb-subscribe-relation-fields-loop-test: ok');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
