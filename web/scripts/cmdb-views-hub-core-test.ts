import assert from 'node:assert/strict';
import {
  VIEW_TYPES,
  isValidViewType,
} from '../src/app/cmdb/(pages)/views/viewTypes';
import {
  isViewEligible,
  eligibleModelIdsForView,
  resolveRackRoomMode,
  viewAllowsMultiSelect,
} from '../src/app/cmdb/(pages)/views/viewEligibility';
import {
  filterNetworkModelIdsByCatalog,
  networkModelIdsFromInterfaceAssociations,
} from '../src/app/cmdb/(pages)/views/networkModelDiscovery';
import {
  buildViewsPath,
  buildViewsPathPreserving,
  buildBaseInfoPath,
  parseInstUuids,
  parseViewsSearch,
} from '../src/app/cmdb/(pages)/views/viewUrls';
import {
  getViewMemoryStorageKey,
  readViewFocus,
  readViewFocusForMode,
  readViewFocuses,
  readViewFocusesForMode,
  writeViewFocus,
  writeViewFocuses,
  clearViewFocus,
  pushViewRecent,
  readViewRecent,
} from '../src/app/cmdb/(pages)/views/viewMemory';
import {
  mergeRackRoomGroups,
  rackGroupsToSelectOptions,
} from '../src/app/cmdb/(pages)/views/rackPickerGroups';

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) { return this.values.get(key) ?? null; }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

assert.deepEqual([...VIEW_TYPES], ['application', 'k8s', 'network', 'ip', 'rack-room']);
assert.equal(isValidViewType('network'), true);
assert.equal(isValidViewType('nope'), false);

assert.equal(isViewEligible('network', 'router', ['network']), true);
assert.equal(isViewEligible('network', 'host', []), false);
assert.equal(isViewEligible('ip', 'subnet', ['ipam']), true);
assert.equal(isViewEligible('application', 'system', ['app_overview']), true);
assert.equal(isViewEligible('k8s', 'k8s_cluster', []), true);
assert.equal(isViewEligible('k8s', 'host', []), false);
assert.equal(isViewEligible('rack-room', 'server_room', [], 'room'), true);
assert.equal(isViewEligible('rack-room', 'rack', [], 'rack'), true);
assert.equal(isViewEligible('rack-room', 'rack', [], 'room'), false);
assert.deepEqual(eligibleModelIdsForView('k8s'), ['k8s_cluster']);
assert.deepEqual(eligibleModelIdsForView('rack-room', 'room'), ['server_room']);
assert.equal(resolveRackRoomMode('server_room', undefined), 'room');
assert.equal(resolveRackRoomMode('rack', 'room'), 'rack'); // model wins when inconsistent

assert.deepEqual(
  networkModelIdsFromInterfaceAssociations([
    { asst_id: 'belong', src_model_id: 'interface', dst_model_id: 'router' },
    { asst_id: 'belong', src_model_id: 'interface', dst_model_id: 'switch' },
    { asst_id: 'connect', src_model_id: 'interface', dst_model_id: 'host' },
    { asst_id: 'belong', src_model_id: 'host', dst_model_id: 'rack' },
  ]),
  ['router', 'switch']
);
assert.deepEqual(
  filterNetworkModelIdsByCatalog(
    ['host', 'router', 'switch', 'subnet'],
    ['router', 'firewall', 'switch']
  ),
  ['router', 'switch']
);

assert.equal(viewAllowsMultiSelect('rack-room', 'rack'), true);
assert.equal(viewAllowsMultiSelect('rack-room', 'room'), false);
assert.equal(viewAllowsMultiSelect('k8s'), false);

assert.equal(
  buildViewsPath('network', { model_id: 'router', inst_uuid: '1' }),
  '/cmdb/views/network?model_id=router&inst_uuid=1'
);
assert.equal(
  buildViewsPath('rack-room', { model_id: 'rack', inst_uuid: '9', mode: 'rack' }),
  '/cmdb/views/rack-room?model_id=rack&inst_uuid=9&mode=rack'
);
assert.equal(
  buildViewsPath('rack-room', [
    { model_id: 'rack', inst_uuid: 'a', mode: 'rack', inst_name: 'A01' },
    { model_id: 'rack', inst_uuid: 'b', mode: 'rack', inst_name: 'A02' },
  ]),
  '/cmdb/views/rack-room?model_id=rack&inst_uuid=a%2Cb&inst_name=A01&mode=rack'
);
assert.deepEqual(parseInstUuids('a,b,a, c'), ['a', 'b', 'c']);
{
  const withUi = new URLSearchParams(
    'model_id=old&inst_uuid=0&sub=pod&expanded_workloads=w1&unowned_pods=1'
  );
  const preserved = buildViewsPathPreserving(
    'k8s',
    { model_id: 'k8s_cluster', inst_uuid: '42', inst_name: 'prod' },
    withUi
  );
  const preservedParams = new URLSearchParams(preserved.split('?')[1] || '');
  assert.equal(preservedParams.get('model_id'), 'k8s_cluster');
  assert.equal(preservedParams.get('inst_uuid'), '42');
  assert.equal(preservedParams.get('inst_name'), 'prod');
  assert.equal(preservedParams.get('sub'), 'pod');
  assert.equal(preservedParams.get('expanded_workloads'), 'w1');
  assert.equal(preservedParams.get('unowned_pods'), '1');
  assert.equal(preserved.startsWith('/cmdb/views/k8s?'), true);
}
assert.match(
  buildBaseInfoPath({ model_id: 'router', inst_uuid: '1', inst_name: 'r1', model_name: '路由器', icn: 'x' }),
  /^\/cmdb\/assetData\/detail\/baseInfo\?/
);
assert.deepEqual(
  parseViewsSearch(new URLSearchParams('model_id=router&inst_uuid=1')),
  {
    model_id: 'router',
    inst_uuid: '1',
    inst_uuids: ['1'],
    mode: undefined,
    inst_name: undefined,
    model_name: undefined,
    icn: undefined,
  }
);
assert.deepEqual(
  parseViewsSearch(new URLSearchParams('model_id=rack&inst_uuid=a,b&mode=rack')),
  {
    model_id: 'rack',
    inst_uuid: 'a',
    inst_uuids: ['a', 'b'],
    mode: 'rack',
    inst_name: undefined,
    model_name: undefined,
    icn: undefined,
  }
);

const storage = new MemoryStorage();
assert.equal(getViewMemoryStorageKey(7, 'network'), 'bk-lite:cmdb:views:v1:7:network');
assert.equal(readViewFocus(storage, 7, 'network'), null);
writeViewFocus(storage, 7, 'network', { model_id: 'router', inst_uuid: '1', inst_name: 'r1' });
assert.deepEqual(readViewFocus(storage, 7, 'network'), {
  model_id: 'router', inst_uuid: '1', inst_name: 'r1',
});
writeViewFocus(storage, 7, 'application', { model_id: 'system', inst_uuid: '2' });
assert.equal(readViewFocus(storage, 7, 'network')?.inst_uuid, '1'); // isolation
clearViewFocus(storage, 7, 'network');
assert.equal(readViewFocus(storage, 7, 'network'), null);
assert.equal(readViewFocus(storage, 7, 'application')?.inst_uuid, '2');

// rack-room: mode slots are independent; clearing one mode keeps the other.
writeViewFocus(storage, 7, 'rack-room', {
  model_id: 'server_room', inst_uuid: 'room-1', mode: 'room',
});
writeViewFocus(storage, 7, 'rack-room', {
  model_id: 'rack', inst_uuid: 'rack-1', mode: 'rack',
});
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'room')?.inst_uuid, 'room-1');
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'rack')?.inst_uuid, 'rack-1');
assert.equal(readViewFocus(storage, 7, 'rack-room')?.inst_uuid, 'rack-1'); // last write
clearViewFocus(storage, 7, 'rack-room', 'rack');
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'rack'), null);
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'room')?.inst_uuid, 'room-1');

writeViewFocuses(storage, 7, 'rack-room', [
  { model_id: 'rack', inst_uuid: 'rack-a', mode: 'rack', inst_name: 'A01' },
  { model_id: 'rack', inst_uuid: 'rack-b', mode: 'rack', inst_name: 'A02' },
]);
assert.deepEqual(
  readViewFocusesForMode(storage, 7, 'rack-room', 'rack').map((item) => item.inst_uuid),
  ['rack-a', 'rack-b']
);
assert.equal(readViewFocuses(storage, 7, 'rack-room')[1]?.inst_name, 'A02');
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'room')?.inst_uuid, 'room-1');

pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_uuid: '1', inst_name: 'r1' });
pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_uuid: '2', inst_name: 'r2' });
pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_uuid: '1', inst_name: 'r1' }); // move to front
const recent = readViewRecent(storage, 7, 'network');
assert.equal(recent[0].inst_uuid, '1');
assert.equal(recent.length, 2);
for (let i = 0; i < 12; i++) {
  pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_uuid: String(100 + i) });
}
assert.equal(readViewRecent(storage, 7, 'network').length, 10);

const roomA = {
  room_uuid: 'room-a',
  room_name: '北京-1F',
  racks: [
    { inst_uuid: 'r1', inst_name: 'A01' },
    { inst_uuid: 'r2', inst_name: 'A02' },
  ],
};
const roomB = {
  room_uuid: 'room-b',
  room_name: '上海-2F',
  racks: [{ inst_uuid: 'r3', inst_name: 'B01' }],
};

assert.deepEqual(
  mergeRackRoomGroups([], [roomA, roomB], false).map((group) => group.room_name),
  ['北京-1F', '上海-2F']
);
{
  const appended = mergeRackRoomGroups([roomA], [roomB], true);
  assert.deepEqual(appended.map((group) => group.room_name), ['北京-1F', '上海-2F']);
  const mergedSame = mergeRackRoomGroups(
    [roomA],
    [{
      room_uuid: 'room-a',
      room_name: '北京-1F',
      racks: [{ inst_uuid: 'r9', inst_name: 'A09' }],
    }],
    true
  );
  assert.deepEqual(
    mergedSame[0].racks.map((rack) => rack.inst_name),
    ['A01', 'A02', 'A09']
  );
}

{
  const options = rackGroupsToSelectOptions({
    recent: [{ inst_uuid: 'r1', inst_name: 'A01' }],
    groups: [roomA, roomB],
    selected: [],
    keyword: '',
    recentLabel: '最近访问',
    unassociatedLabel: '未关联机房',
    rackWithRoom: '{room} / {rack}',
  });
  assert.equal(options[0].label, '最近访问');
  assert.equal(options[1].label, '北京-1F');
  assert.deepEqual(options[1].options.map((item) => item.label), ['A02']);
  assert.equal(options[1].options[0].selectedLabel, '北京-1F / A02');
  assert.equal(options[2].label, '上海-2F');
}

{
  const searched = rackGroupsToSelectOptions({
    recent: [{ inst_uuid: 'r1', inst_name: 'A01' }],
    groups: [roomA],
    selected: [],
    keyword: '北京',
    recentLabel: '最近访问',
    unassociatedLabel: '未关联机房',
    rackWithRoom: '{room} / {rack}',
  });
  assert.equal(searched[0].label, '北京-1F');
  assert.deepEqual(searched[0].options.map((item) => item.label), ['A01', 'A02']);
}

{
  const unassociated = rackGroupsToSelectOptions({
    recent: [],
    groups: [{ room_uuid: null, room_name: '', racks: [{ inst_uuid: 'z', inst_name: 'Z99' }] }],
    selected: [],
    keyword: 'Z99',
    recentLabel: '最近访问',
    unassociatedLabel: '未关联机房',
    rackWithRoom: '{room} / {rack}',
  });
  assert.equal(unassociated[0].label, '未关联机房');
  assert.equal(unassociated[0].options[0].selectedLabel, '未关联机房 / Z99');
}

console.log('cmdb-views-hub-core-test: PASS');
