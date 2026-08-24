import assert from 'node:assert/strict';

import {
  MODULE_OBJECT_QUERY_PARAM,
  VIEW_OBJECT_QUERY_PARAM,
  buildMonitorObjectUrl,
  isConcreteMonitorObjectId,
  readMonitorObjectQueryId,
  recallMonitorObjectId,
  rememberMonitorObjectId,
  resolveMonitorObjectQueryId,
  resolveMonitorObjectTreeKey,
  shouldSyncMonitorObjectUrl
} from '../src/app/monitor/utils/monitorObjectQuery';

const objects = [
  { id: 25, type: 'os', name: 'Host' },
  { id: 16, type: 'network', name: 'Switch' }
];

assert.equal(isConcreteMonitorObjectId(16), true);
assert.equal(isConcreteMonitorObjectId('25'), true);
assert.equal(isConcreteMonitorObjectId('all'), false);
assert.equal(isConcreteMonitorObjectId('network'), false);

assert.equal(
  readMonitorObjectQueryId(new URLSearchParams('object_id=16')),
  '16'
);
assert.equal(
  readMonitorObjectQueryId(new URLSearchParams('objId=25')),
  '25'
);
assert.equal(
  readMonitorObjectQueryId(new URLSearchParams('object_id=16&objId=25')),
  '25'
);
assert.equal(
  readMonitorObjectQueryId(
    new URLSearchParams('object_id=16&objId=25'),
    VIEW_OBJECT_QUERY_PARAM
  ),
  '16'
);

assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams('object_id=16'),
    objects,
    fallback: 25
  }),
  '16'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams('objId=16'),
    objects,
    fallback: 25
  }),
  '16'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams(),
    objects,
    recalledId: '16',
    fallback: 25
  }),
  '16'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams('objId=99'),
    objects,
    fallback: 25
  }),
  '25'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams(),
    objects,
    allowAll: true
  }),
  'all'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams('objId=network'),
    objects,
    allowAll: true,
    allowTypeKeys: true
  }),
  'network'
);
assert.equal(
  resolveMonitorObjectQueryId({
    searchParams: new URLSearchParams('objId=all'),
    objects,
    allowAll: true
  }),
  'all'
);

assert.equal(resolveMonitorObjectTreeKey(objects, '16'), 16);
assert.equal(resolveMonitorObjectTreeKey(objects, 'all', 'all'), 'all');

assert.equal(
  buildMonitorObjectUrl(
    '/monitor/event/strategy',
    new URLSearchParams('object_id=16&foo=1'),
    25,
    MODULE_OBJECT_QUERY_PARAM
  ),
  '/monitor/event/strategy?foo=1&objId=25'
);
assert.equal(
  buildMonitorObjectUrl(
    '/monitor/view',
    new URLSearchParams('objId=16'),
    16,
    VIEW_OBJECT_QUERY_PARAM
  ),
  '/monitor/view?object_id=16'
);
assert.equal(
  buildMonitorObjectUrl(
    '/monitor/event/alert',
    new URLSearchParams('objId=16'),
    'all',
    MODULE_OBJECT_QUERY_PARAM
  ),
  '/monitor/event/alert?objId=all'
);

assert.equal(
  shouldSyncMonitorObjectUrl(
    new URLSearchParams('objId=16'),
    16,
    MODULE_OBJECT_QUERY_PARAM
  ),
  false
);
assert.equal(
  shouldSyncMonitorObjectUrl(
    new URLSearchParams('object_id=16'),
    16,
    MODULE_OBJECT_QUERY_PARAM
  ),
  true
);

const memory = new Map<string, string>();
const storage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => {
    memory.set(key, value);
  }
};
rememberMonitorObjectId('all', storage);
assert.equal(recallMonitorObjectId(storage), '');
rememberMonitorObjectId(16, storage);
assert.equal(recallMonitorObjectId(storage), '16');

console.log('monitor-object-query-test passed');
