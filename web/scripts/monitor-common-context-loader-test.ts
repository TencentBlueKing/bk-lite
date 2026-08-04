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

  // 同 key 命中会话缓存,不再打 API
  let secondUsersCalls = 0;
  const cached = await loadMonitorCommonData({
    cacheKey: 'case-users-ok',
    getAllUsers: async () => {
      secondUsersCalls += 1;
      return [];
    },
    getUnitList: async () => [],
  });
  assert.equal(secondUsersCalls, 0);
  assert.deepEqual(cached.users, data.users);

  clearMonitorCommonDataCache();
  const grouped = await loadMonitorCommonData({
    cacheKey: 'case-grouped',
    getAllUsers: async () => [],
    getUnitList: async () => [
      {
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
      },
    ],
  });

  assert.deepEqual(grouped.groupedUnits, [
    {
      label: 'time',
      children: [
        {
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
        },
      ],
    },
  ]);

  console.log('monitor common context loader validation passed');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
