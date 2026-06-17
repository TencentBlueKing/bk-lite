import * as assert from 'node:assert/strict';
import { mergeViewQueryKeyValues } from '../src/app/monitor/utils/common';

assert.equal(
  mergeViewQueryKeyValues([
    {
      keys: ['instance_id'],
      values: ['flow:15:1:10.10.41.149']
    }
  ]),
  'instance_id=~"flow:15:1:10\\\\.10\\\\.41\\\\.149"'
);

assert.equal(
  mergeViewQueryKeyValues([
    {
      keys: ['instance_id'],
      values: ['host-(a)|prod"1']
    }
  ]),
  'instance_id=~"host-\\\\(a\\\\)\\\\|prod\\"1"'
);

console.log('monitor promql label query tests passed');
