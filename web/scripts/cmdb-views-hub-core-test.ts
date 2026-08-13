import assert from 'node:assert/strict';
import {
  VIEW_TYPES,
  isValidViewType,
} from '../src/app/cmdb/(pages)/views/viewTypes';
import {
  isViewEligible,
  eligibleModelIdsForView,
  resolveRackRoomMode,
} from '../src/app/cmdb/(pages)/views/viewEligibility';
import {
  filterNetworkModelIdsByCatalog,
  networkModelIdsFromInterfaceAssociations,
} from '../src/app/cmdb/(pages)/views/networkModelDiscovery';
import {
  buildViewsPath,
  buildViewsPathPreserving,
  buildBaseInfoPath,
  parseViewsSearch,
} from '../src/app/cmdb/(pages)/views/viewUrls';
import {
  getViewMemoryStorageKey,
  readViewFocus,
  readViewFocusForMode,
  writeViewFocus,
  clearViewFocus,
  pushViewRecent,
  readViewRecent,
} from '../src/app/cmdb/(pages)/views/viewMemory';

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

assert.equal(
  buildViewsPath('network', { model_id: 'router', inst_id: '1' }),
  '/cmdb/views/network?model_id=router&inst_id=1'
);
assert.equal(
  buildViewsPath('rack-room', { model_id: 'rack', inst_id: '9', mode: 'rack' }),
  '/cmdb/views/rack-room?model_id=rack&inst_id=9&mode=rack'
);
{
  const withUi = new URLSearchParams(
    'model_id=old&inst_id=0&sub=pod&expanded_workloads=w1&unowned_pods=1'
  );
  const preserved = buildViewsPathPreserving(
    'k8s',
    { model_id: 'k8s_cluster', inst_id: '42', inst_name: 'prod' },
    withUi
  );
  const preservedParams = new URLSearchParams(preserved.split('?')[1] || '');
  assert.equal(preservedParams.get('model_id'), 'k8s_cluster');
  assert.equal(preservedParams.get('inst_id'), '42');
  assert.equal(preservedParams.get('inst_name'), 'prod');
  assert.equal(preservedParams.get('sub'), 'pod');
  assert.equal(preservedParams.get('expanded_workloads'), 'w1');
  assert.equal(preservedParams.get('unowned_pods'), '1');
  assert.equal(preserved.startsWith('/cmdb/views/k8s?'), true);
}
assert.match(
  buildBaseInfoPath({ model_id: 'router', inst_id: '1', inst_name: 'r1', model_name: '路由器', icn: 'x' }),
  /^\/cmdb\/assetData\/detail\/baseInfo\?/
);
assert.deepEqual(
  parseViewsSearch(new URLSearchParams('model_id=router&inst_id=1')),
  { model_id: 'router', inst_id: '1', mode: undefined, inst_name: undefined, model_name: undefined, icn: undefined }
);

const storage = new MemoryStorage();
assert.equal(getViewMemoryStorageKey(7, 'network'), 'bk-lite:cmdb:views:v1:7:network');
assert.equal(readViewFocus(storage, 7, 'network'), null);
writeViewFocus(storage, 7, 'network', { model_id: 'router', inst_id: '1', inst_name: 'r1' });
assert.deepEqual(readViewFocus(storage, 7, 'network'), {
  model_id: 'router', inst_id: '1', inst_name: 'r1',
});
writeViewFocus(storage, 7, 'application', { model_id: 'system', inst_id: '2' });
assert.equal(readViewFocus(storage, 7, 'network')?.inst_id, '1'); // isolation
clearViewFocus(storage, 7, 'network');
assert.equal(readViewFocus(storage, 7, 'network'), null);
assert.equal(readViewFocus(storage, 7, 'application')?.inst_id, '2');

// rack-room: mode slots are independent; clearing one mode keeps the other.
writeViewFocus(storage, 7, 'rack-room', {
  model_id: 'server_room', inst_id: 'room-1', mode: 'room',
});
writeViewFocus(storage, 7, 'rack-room', {
  model_id: 'rack', inst_id: 'rack-1', mode: 'rack',
});
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'room')?.inst_id, 'room-1');
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'rack')?.inst_id, 'rack-1');
assert.equal(readViewFocus(storage, 7, 'rack-room')?.inst_id, 'rack-1'); // last write
clearViewFocus(storage, 7, 'rack-room', 'rack');
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'rack'), null);
assert.equal(readViewFocusForMode(storage, 7, 'rack-room', 'room')?.inst_id, 'room-1');

pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_id: '1', inst_name: 'r1' });
pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_id: '2', inst_name: 'r2' });
pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_id: '1', inst_name: 'r1' }); // move to front
const recent = readViewRecent(storage, 7, 'network');
assert.equal(recent[0].inst_id, '1');
assert.equal(recent.length, 2);
for (let i = 0; i < 12; i++) {
  pushViewRecent(storage, 7, 'network', { model_id: 'router', inst_id: String(100 + i) });
}
assert.equal(readViewRecent(storage, 7, 'network').length, 10);

console.log('cmdb-views-hub-core-test: PASS');
