import assert from 'node:assert/strict';

import {
  resolveTableLikeColumns,
  getRecordEntries,
  parseTableLikeData,
} from '../src/app/ops-analysis/(pages)/view/dashBoard/widgets/shared/tableLikeData';
import {
  buildDisplayColumnFieldOptions,
  resolveDatasourceChartTypes,
  shouldShowTableFilterFields,
} from '../src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig/utils/tableSettingsBehavior';

const listData = [
  { id: '1', event: 'created', actor: 'admin' },
  { id: '2', event: 'updated', actor: 'guest' },
];

const pagedData = {
  count: 42,
  items: [
    { id: '3', event: 'deleted', actor: 'admin' },
  ],
};

assert.deepEqual(
  parseTableLikeData(listData, { current: 1, pageSize: 20 }),
  {
    rows: listData,
    pagination: {
      current: 1,
      pageSize: 20,
      total: 2,
    },
    isPaginated: false,
  },
);

assert.deepEqual(
  parseTableLikeData(pagedData, { current: 2, pageSize: 10 }),
  {
    rows: pagedData.items,
    pagination: {
      current: 2,
      pageSize: 10,
      total: 42,
    },
    isPaginated: true,
  },
);

assert.deepEqual(getRecordEntries({ id: 1, name: 'audit', nested: { ok: true } }), [
  { key: 'id', value: '1' },
  { key: 'name', value: 'audit' },
  { key: 'nested', value: '{"ok":true}' },
]);

assert.deepEqual(
  resolveTableLikeColumns({
    configuredColumns: [
      { key: 'event', title: 'Event', visible: true, order: 1 },
      { key: 'actor', title: 'Actor', visible: false, order: 0 },
    ],
    schemaFields: [],
    rows: listData,
  }).map((item) => ({
    key: item.key,
    title: item.title,
    visible: item.visible,
    order: item.order,
  })),
  [
    { key: 'actor', title: 'Actor', visible: false, order: 0 },
    { key: 'event', title: 'Event', visible: true, order: 1 },
  ],
);

assert.deepEqual(
  resolveTableLikeColumns({
    configuredColumns: [],
    schemaFields: [
      { key: 'id', title: 'ID', value_type: 'string' },
      { key: 'event', title: 'Event', value_type: 'string' },
    ],
    rows: listData,
  }).map((item) => item.key),
  ['id', 'event'],
);

assert.equal(shouldShowTableFilterFields('table'), true);
assert.equal(shouldShowTableFilterFields('eventTable'), false);

assert.deepEqual(
  buildDisplayColumnFieldOptions({
    availableFields: [
      { key: 'timestamp', title: 'Timestamp', value_type: 'string' },
      { key: 'message', title: 'Message', value_type: 'string' },
    ],
    displayColumns: [
      {
        id: 'col-message',
        key: 'message',
        title: 'Message',
        visible: true,
        order: 0,
      },
      {
        id: 'col-source-ip',
        key: 'source_ip',
        title: 'Source IP',
        visible: true,
        order: 1,
      },
    ],
  }),
  [
    { label: 'message (Message)', value: 'message' },
    { label: 'source_ip (Source IP)', value: 'source_ip' },
    { label: 'timestamp (Timestamp)', value: 'timestamp' },
  ],
);

assert.deepEqual(
  buildDisplayColumnFieldOptions({
    availableFields: [],
    displayColumns: [],
    detectedColumns: [
      { key: 'raw_message', title: 'Raw Message' },
      { key: 'stream_id', title: 'Stream ID' },
    ],
  }),
  [
    { label: 'raw_message (Raw Message)', value: 'raw_message' },
    { label: 'stream_id (Stream ID)', value: 'stream_id' },
  ],
);

assert.deepEqual(
  resolveDatasourceChartTypes({
    chartTypes: ['message', 'eventTable', 'eventTable', 'table'],
    chartTypeDefinitions: [
      { value: 'eventTable', label: 'Event Table' },
      { value: 'table', label: 'Table' },
    ],
  }).map((item) => item.value),
  ['eventTable', 'table'],
);

console.log('ops-analysis event-table validation passed');