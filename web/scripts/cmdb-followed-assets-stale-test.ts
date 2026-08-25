import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  normalizeFollowedAssetsConfig,
  resolveVisibleFollowedAssets,
} from '../src/app/cmdb/utils/followedAssets';

const uuid = (n: number) =>
  `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

const followedItems = [
  { model_id: 'host', inst_uuid: uuid(101), followed_at: '2026-07-15T12:00:00Z' },
  { model_id: 'mysql', inst_uuid: uuid(201), followed_at: '2026-07-15T11:00:00Z' },
  ...Array.from({ length: 12 }, (_, index) => ({
    model_id: 'host',
    inst_uuid: uuid(102 + index),
    followed_at: `2026-07-15T${String(10 - index).padStart(2, '0')}:00:00Z`,
  })),
];

const main = async () => {
  const legacyNormalized = normalizeFollowedAssetsConfig({
    items: [
      { model_id: 'host', inst_id: uuid(9), followed_at: '2026-07-15T09:00:00Z' } as any,
    ],
  });
  assert.equal(legacyNormalized.items[0]?.inst_uuid, uuid(9));
  assert.equal(
    Object.prototype.hasOwnProperty.call(legacyNormalized.items[0], 'inst_id'),
    false
  );

  const calls: Array<{ modelId: string; instanceUuids: string[] }> = [];
  const visibleAssets = await resolveVisibleFollowedAssets(
    followedItems,
    async (modelId, instanceUuids) => {
      calls.push({ modelId, instanceUuids });
      if (modelId === 'mysql') {
        return [];
      }
      return instanceUuids
        .filter((instanceUuid) => instanceUuid !== uuid(101))
        .map((instanceUuid) => ({
          inst_uuid: instanceUuid,
          model_id: modelId,
          inst_name: `asset-${instanceUuid}`,
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
    visibleAssets.map(({ item }) => item.inst_uuid),
    Array.from({ length: 12 }, (_, index) => uuid(102 + index)),
    '结果应保持原关注顺序'
  );

  const pageSource = readFileSync(
    resolve(process.cwd(), 'src/app/cmdb/(pages)/assetSearch/page.tsx'),
    'utf8'
  );
  assert.match(pageSource, /resolveVisibleFollowedAssets(?:<[^>]+>)?\(/);
  assert.match(pageSource, /searchInstances\(\{/);
  assert.match(pageSource, /field:\s*'inst_uuid'/);
  assert.doesNotMatch(
    pageSource,
    /getInstanceDetail\(String\(item\.inst_uuid\)\)/,
    '首页不能再对关注资产逐条请求详情，否则已删除实例仍会触发 404'
  );

  console.log('PASS cmdb-followed-assets-stale');
};

void main();
