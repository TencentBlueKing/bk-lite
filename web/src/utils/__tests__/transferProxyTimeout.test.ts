import { expect, it } from 'vitest';
import { getProxyBodyTimeoutMs } from '../proxyTimeout';

it('grants file transfer timeout only to CMDB upload/download POST routes', () => {
  expect(getProxyBodyTimeoutMs('/cmdb/api/transfer_tasks/import/', 'POST')).toBe(300000);
  expect(getProxyBodyTimeoutMs('/cmdb/api/transfer_tasks/123e4567-e89b-42d3-a456-426614174000/download/', 'POST')).toBe(300000);
  expect(getProxyBodyTimeoutMs('/cmdb/api/transfer_tasks/export/', 'POST')).toBe(60000);
  expect(getProxyBodyTimeoutMs('/cmdb/api/transfer_tasks/import/', 'GET')).toBe(60000);
  expect(getProxyBodyTimeoutMs('/other/import/', 'POST')).toBe(60000);
});
