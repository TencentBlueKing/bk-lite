import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { resolveVisibleFollowedAssets } from '../src/app/cmdb/utils/followedAssets';

const followedItems = [
  { model_id: 'host', inst_id: 101, followed_at: '2026-07-15T12:00:00Z' },
  { model_id: 'mysql', inst_id: 201, followed_at: '2026-07-15T11:00:00Z' },
  ...Array.from({ length: 12 }, (_, index) => ({
    model_id: 'host',
    inst_id: 102 + index,
    followed_at: `2026-07-15T${String(10 - index).padStart(2, '0')}:00:00Z`,
  })),
];

const main = async () => {
  const calls: Array<{ modelId: string; instanceIds: Array<string | number> }> = [];
  const visibleAssets = await resolveVisibleFollowedAssets(
    followedItems,
    async (modelId, instanceIds) => {
      calls.push({ modelId, instanceIds });
      if (modelId === 'mysql') {
        return [];
      }
      return instanceIds
        .filter((instanceId) => instanceId !== 101)
        .map((instanceId) => ({
          _id: Number(instanceId),
          model_id: modelId,
          inst_name: `asset-${instanceId}`,
        }));
    },
    12
  );

  assert.equal(calls.length, 2, '关注资产应按模型分组批量查询，不能逐实例请求详情');
  assert.deepEqual(
    calls.map((call) => call.modelId).sort(),
    ['host', 'mysql']
  );
  assert.equal(visibleAssets.length, 12, '已删除关注项应被过滤，后续有效关注项应补位');
  assert.deepEqual(
    visibleAssets.map(({ item }) => item.inst_id),
    Array.from({ length: 12 }, (_, index) => 102 + index),
    '结果应保持原关注顺序'
  );

  const pageSource = readFileSync(
    resolve(process.cwd(), 'src/app/cmdb/(pages)/assetSearch/page.tsx'),
    'utf8'
  );
  assert.match(pageSource, /resolveVisibleFollowedAssets(?:<[^>]+>)?\(/);
  assert.match(pageSource, /searchInstances\(\{/);
  assert.doesNotMatch(
    pageSource,
    /getInstanceDetail\(String\(item\.inst_id\)\)/,
    '首页不能再对关注资产逐条请求详情，否则已删除实例仍会触发 404'
  );

  console.log('PASS cmdb-followed-assets-stale');
};

void main();
