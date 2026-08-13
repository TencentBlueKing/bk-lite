import assert from 'node:assert/strict';

import { buildCustomReportingCurlPayload } from '../src/app/cmdb/utils/customReportingDocument';

const payload = buildCustomReportingCurlPayload({
  endpoint: '/api/v1/cmdb/api/custom_reporting/ingest/',
  auth_header: { name: 'Authorization', format: 'Bearer <token>' },
  identity_keys: ['inst_name'],
  examples: {
    instances: {
      instances: [
        {
          inst_name: '<inst_name_1>',
          ip_addr: '<ip_addr_1>',
          cloud: '<cloud_1>',
        },
      ],
    },
    with_relations: { instances: [], relations: [] },
  },
});

assert.deepEqual(payload, {
  instances: [
    {
      inst_name: '<inst_name_1>',
      ip_addr: '<ip_addr_1>',
      cloud: '<cloud_1>',
    },
  ],
});

const fallbackPayload = buildCustomReportingCurlPayload({
  endpoint: '/api/v1/cmdb/api/custom_reporting/ingest/',
  auth_header: { name: 'Authorization', format: 'Bearer <token>' },
  identity_keys: ['inst_name', 'organization'],
  examples: {
    instances: { instances: [] },
    with_relations: { instances: [], relations: [] },
  },
});

assert.deepEqual(fallbackPayload, {
  instances: [{ inst_name: '<inst_name>' }],
});

console.log('PASS cmdb-custom-reporting-document');
