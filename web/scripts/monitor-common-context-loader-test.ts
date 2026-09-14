import assert from 'node:assert/strict';
import {
  clearMonitorCommonDataCache,
  loadMonitorCommonData,
  shouldLoadMonitorCommonData,
} from '../src/app/monitor/context/commonDataLoader';

assert.equal(
  shouldLoadMonitorCommonData({
    requestLoading: false,
    userInfoLoading: false,
    selectedGroupId: '7',
  }),
  true
);

assert.equal(
  shouldLoadMonitorCommonData({
    requestLoading: false,
    userInfoLoading: true,
    selectedGroupId: '7',
  }),
  false
);

assert.equal(
  shouldLoadMonitorCommonData({
    requestLoading: false,
    userInfoLoading: false,
    selectedGroupId: null,
  }),
  false
);

const sampleUnit = {
  category: 'time',
  unit_id: 'min',
  unit_name: '分钟',
  display_unit: 'min',
  description: '',
  is_standalone: false,
  system: 'time',
  label: '分钟',
  value: 'min',
  unit: 'min',
};

async function main() {
  clearMonitorCommonDataCache();
  const data = await loadMonitorCommonData({
    cacheKey: 'case-users-ok',
    getAllUsers: async () => [{ id: '1', username: 'alice', display_name: 'Alice' }],
    getUnitList: async () => {
      throw new Error('unit api failed');
    },
  });

  assert.deepEqual(data.users, [{ id: '1', username: 'alice', display_name: 'Alice' }]);
  assert.deepEqual(data.units, []);
  assert.deepEqual(data.groupedUnits, []);

  // 单位失败不得当成成功空结果缓存；再次加载必须重试单位，并保留已成功用户
  let secondUsersCalls = 0;
  let secondUnitCalls = 0;
  const retried = await loadMonitorCommonData({
    cacheKey: 'case-users-ok',
    getAllUsers: async () => {
      secondUsersCalls += 1;
      return [];
    },
    getUnitList: async () => {
      secondUnitCalls += 1;
      return [sampleUnit];
    },
  });
  assert.equal(secondUsersCalls, 0, '成功用户不得因单位失败而重拉');
  assert.equal(secondUnitCalls, 1, '单位失败后再次加载必须重试 getUnitList');
  assert.deepEqual(retried.users, data.users);
  assert.deepEqual(retried.units, [sampleUnit]);

  clearMonitorCommonDataCache();
  let emptyUserCalls = 0;
  let emptyUnitCalls = 0;
  const emptyFirst = await loadMonitorCommonData({
    cacheKey: 'case-empty-success',
    getAllUsers: async () => {
      emptyUserCalls += 1;
      return [];
    },
    getUnitList: async () => {
      emptyUnitCalls += 1;
      return [];
    },
  });
  assert.deepEqual(emptyFirst.users, []);
  assert.deepEqual(emptyFirst.units, []);
  assert.equal(emptyUserCalls, 1);
  assert.equal(emptyUnitCalls, 1);

  const emptyCached = await loadMonitorCommonData({
    cacheKey: 'case-empty-success',
    getAllUsers: async () => {
      emptyUserCalls += 1;
      return [{ id: '2', username: 'bob', display_name: 'Bob' }];
    },
    getUnitList: async () => {
      emptyUnitCalls += 1;
      return [sampleUnit];
    },
  });
  assert.equal(emptyUserCalls, 1, '成功空用户列表必须缓存');
  assert.equal(emptyUnitCalls, 1, '成功空单位列表必须缓存，不再请求');
  assert.deepEqual(emptyCached.users, []);
  assert.deepEqual(emptyCached.units, []);

  clearMonitorCommonDataCache();
  let concurrentUserCalls = 0;
  let concurrentUnitCalls = 0;
  const getAllUsers = async () => {
    concurrentUserCalls += 1;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return [{ id: '1', username: 'alice', display_name: 'Alice' }];
  };
  const getUnitList = async () => {
    concurrentUnitCalls += 1;
    await new Promise((resolve) => setTimeout(resolve, 20));
    return [] as typeof sampleUnit[];
  };
  const [firstInflight, secondInflight] = await Promise.all([
    loadMonitorCommonData({
      cacheKey: 'case-inflight',
      getAllUsers,
      getUnitList,
    }),
    loadMonitorCommonData({
      cacheKey: 'case-inflight',
      getAllUsers,
      getUnitList,
    }),
  ]);
  assert.equal(concurrentUserCalls, 1, '同 key 并发必须去重用户请求');
  assert.equal(concurrentUnitCalls, 1, '同 key 并发必须去重单位请求');
  assert.deepEqual(firstInflight.users, secondInflight.users);

  clearMonitorCommonDataCache();
  const grouped = await loadMonitorCommonData({
    cacheKey: 'case-grouped',
    getAllUsers: async () => [],
    getUnitList: async () => [sampleUnit],
  });

  assert.deepEqual(grouped.groupedUnits, [
    {
      label: 'time',
      children: [sampleUnit],
    },
  ]);

  console.log('monitor common context loader validation passed');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
