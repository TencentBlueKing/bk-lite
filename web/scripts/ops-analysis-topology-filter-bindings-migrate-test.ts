import assert from 'node:assert/strict';

import type { UnifiedFilterDefinition } from '../src/app/ops-analysis/types/dashBoard';
import {
  processDataSourceParams,
  resolveEffectiveFilterBindings,
} from '../src/app/ops-analysis/utils/widgetDataTransform';

const migratedFilter: UnifiedFilterDefinition = {
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    multiple: true,
    optionsSource: { type: 'static', staticItems: [] },
  },
};

const sourceParams = [
  {
    name: 'instance_ids',
    alias_name: '主机',
    type: 'string' as const,
    filterType: 'filter' as const,
    value: null,
    inputConfig: {
      control: 'select' as const,
      multiple: true,
      optionsSource: { type: 'static' as const, staticItems: [] },
    },
  },
];

{
  const resolved = resolveEffectiveFilterBindings(
    sourceParams,
    [migratedFilter],
    { 'instance_ids__stringList': true },
  );
  assert.deepEqual(resolved, { 'instance_ids__string': true });
  assert.deepEqual(
    processDataSourceParams({
      sourceParams,
      unifiedFilterValues: { [migratedFilter.id]: ['h1', 'h2'] },
      filterBindings: resolved,
      filterDefinitions: [migratedFilter],
    }),
    { instance_ids: ['h1', 'h2'] },
    '旧 __stringList 绑定 remap 后应能取到统一筛选值',
  );
}

{
  const resolved = resolveEffectiveFilterBindings(
    sourceParams,
    [migratedFilter],
    { 'instance_ids__stringList': false },
  );
  assert.deepEqual(resolved, { 'instance_ids__string': false });
  assert.deepEqual(
    processDataSourceParams({
      sourceParams,
      unifiedFilterValues: { [migratedFilter.id]: ['h1'] },
      filterBindings: resolved,
      filterDefinitions: [migratedFilter],
    }),
    {},
    '显式关闭的旧绑定 remap 后不得被默认重新打开',
  );
}

{
  const resolved = resolveEffectiveFilterBindings(
    sourceParams,
    [migratedFilter],
    undefined,
  );
  assert.deepEqual(resolved, { 'instance_ids__string': true });
}

{
  const resolved = resolveEffectiveFilterBindings(
    sourceParams,
    [migratedFilter],
    {},
  );
  // 生产存盘合同：`submitConfig` / layout sync / topology save 均省略空对象；
  // 用户显式关闭绑定保存为 `{ filterId: false }`（见 reportBuilder.test.ts）。
  // 因此 `{}` 只表示未初始化/缺失，应愈合为默认绑定。
  assert.deepEqual(resolved, { 'instance_ids__string': true });
}

console.log('ops analysis topology filter bindings migrate tests passed');
