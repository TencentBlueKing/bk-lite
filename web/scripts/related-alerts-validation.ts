import * as assert from 'node:assert/strict';

import {
  getDefaultSelectedRelatedAlertIds,
  getMatchedDimensionsText,
} from '../src/app/alarm/utils/relatedAlerts';

const items = [
  {
    id: 1,
    alert_id: 'ALERT-1',
    title: 'primary',
    content: 'content',
    level: 'warning',
    status: 'unassigned',
    first_event_time: null,
    last_event_time: null,
    incident: null,
    similarity_score: 95,
    match_reason: '关键事件',
    matched_dimensions: { service: 'api', location: 'gz' },
    time_proximity: '3分钟前',
  },
  {
    id: 2,
    alert_id: 'ALERT-2',
    title: 'linked',
    content: 'content',
    level: 'warning',
    status: 'processing',
    first_event_time: null,
    last_event_time: null,
    incident: { id: 11, incident_id: 'INCIDENT-11', title: 'incident' },
    similarity_score: 99,
    match_reason: '关键事件',
    matched_dimensions: { service: 'api' },
    time_proximity: '1分钟前',
  },
  {
    id: 3,
    alert_id: 'ALERT-3',
    title: 'weak',
    content: 'content',
    level: 'warning',
    status: 'unassigned',
    first_event_time: null,
    last_event_time: null,
    incident: null,
    similarity_score: 60,
    match_reason: '相同服务',
    matched_dimensions: { service: 'api' },
    time_proximity: '8分钟前',
  },
];

assert.deepEqual(getDefaultSelectedRelatedAlertIds(items), [1]);
assert.equal(
  getMatchedDimensionsText({ service: 'api', location: 'gz' }),
  'service: api / location: gz'
);
assert.equal(getMatchedDimensionsText({}), '--');

console.log('related-alerts validation passed');
