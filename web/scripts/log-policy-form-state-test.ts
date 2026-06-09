import assert from 'node:assert/strict';
import {
  buildAlertNameVariables,
  buildStrategyPayload,
  getDefaultShowFields,
  getLockedPolicyType,
  insertAlertNameVariable
} from '../src/app/log/(pages)/event/strategy/detail/policyFormUtils';
import {
  buildStrategyDetailUrl,
  getCreatePolicyType
} from '../src/app/log/(pages)/event/strategy/policyRouteUtils';

assert.equal(
  buildStrategyDetailUrl('add', { alertType: 'aggregate' }),
  '/log/event/strategy/detail?type=add&alert_type=aggregate'
);
assert.equal(
  buildStrategyDetailUrl('edit', {
    id: 8,
    name: '已有策略',
    alertType: 'keyword'
  }),
  '/log/event/strategy/detail?type=edit&id=8&name=%E5%B7%B2%E6%9C%89%E7%AD%96%E7%95%A5&alert_type=keyword'
);
assert.equal(getCreatePolicyType('keyword'), 'keyword');
assert.equal(getCreatePolicyType('aggregate'), 'aggregate');
assert.equal(getCreatePolicyType(null), null);
assert.equal(getCreatePolicyType('unknown'), null);

assert.equal(getLockedPolicyType({ urlAlertType: 'keyword' }), 'keyword');
assert.equal(getLockedPolicyType({ detailAlertType: 'aggregate' }), 'aggregate');
assert.equal(getLockedPolicyType({ urlAlertType: 'unknown', detailAlertType: 'keyword' }), 'keyword');
assert.equal(getLockedPolicyType({ urlAlertType: 'keyword', detailAlertType: 'aggregate' }), 'aggregate');

assert.deepEqual(getDefaultShowFields(undefined), ['timestamp', 'message']);
assert.deepEqual(getDefaultShowFields(['message', 'host']), ['timestamp', 'message', 'host']);

assert.deepEqual(buildAlertNameVariables(['log.service.name', 'host']), [
  { value: '${level}', label: '${level}' },
  { value: '${log.service.name}', label: '${log.service.name}' },
  { value: '${host}', label: '${host}' }
]);

assert.equal(insertAlertNameVariable('告警', '${level}', 0, 0), '${level}告警');
assert.equal(insertAlertNameVariable('api告警', '${log.service.name}', 3, 3), 'api${log.service.name}告警');
assert.equal(insertAlertNameVariable('告警', '${level}'), '告警${level}');

const keywordPayload = buildStrategyPayload(
  {
    name: '关键字策略',
    alert_type: 'keyword',
    alert_name: '${level}:${log.service.name}',
    alert_level: 'error',
    log_groups: ['1'],
    organizations: ['10'],
    query: 'error',
    show_fields: ['timestamp', 'message'],
    group_by: ['log.service.name'],
    schedule: 5,
    period: 10,
    notice_type_id: 2
  },
  {
    unit: 'min',
    periodUnit: 'min',
    channelList: [{ id: 2, channel_type: 'email', name: 'Email' }],
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }],
    term: 'and',
    isEdit: false
  }
);

assert.deepEqual(keywordPayload.alert_condition, {
  query: 'error',
  group_by: ['log.service.name']
});
assert.deepEqual(keywordPayload.show_fields, ['timestamp', 'message']);
assert.equal(keywordPayload.notice_type, 'email');
assert.equal(keywordPayload.enable, true);

const aggregatePayload = buildStrategyPayload(
  {
    name: '聚合策略',
    alert_type: 'aggregate',
    alert_name: '${level}:${log.service.name}',
    alert_level: 'warning',
    log_groups: ['1'],
    organizations: ['10'],
    query: 'error',
    show_fields: ['timestamp', 'message'],
    group_by: ['log.service.name'],
    schedule: 5,
    period: 10,
    notice_type_id: 2
  },
  {
    unit: 'min',
    periodUnit: 'min',
    channelList: [{ id: 2, channel_type: 'email', name: 'Email' }],
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }],
    term: 'and',
    isEdit: true,
    formData: { id: 99 }
  }
);

assert.deepEqual(aggregatePayload.alert_condition, {
  query: 'error',
  group_by: ['log.service.name'],
  rule: {
    mode: 'and',
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }]
  }
});
assert.equal(aggregatePayload.id, 99);
assert.equal(Object.prototype.hasOwnProperty.call(aggregatePayload, 'enable'), false);

const existingTimingPayload = buildStrategyPayload(
  {
    name: '已有周期策略',
    alert_type: 'keyword',
    alert_name: 'error',
    alert_level: 'error',
    log_groups: ['1'],
    organizations: ['10'],
    query: 'error',
    show_fields: ['message'],
    schedule: { type: 'hour', value: 2 },
    period: { type: 'min', value: 30 }
  },
  {
    unit: 'min',
    periodUnit: 'min',
    channelList: [],
    conditions: [],
    term: null,
    isEdit: true,
    formData: { id: 100 }
  }
);

assert.deepEqual(existingTimingPayload.schedule, { type: 'hour', value: 2 });
assert.deepEqual(existingTimingPayload.period, { type: 'min', value: 30 });

console.log('log-policy-form-state validation passed');
