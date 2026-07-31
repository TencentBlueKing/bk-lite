import assert from 'node:assert/strict';

import { hasRoutePermission } from '../src/context/permission-path';

const permissions = {
  '/apm/services': ['View'],
  '/apm/traces': ['View'],
};

assert.equal(hasRoutePermission(permissions, '/apm/services/8ac4f758-1a83-4eb0-986e-47e17d37c721'), true);
assert.equal(hasRoutePermission(permissions, '/apm/traces/0123456789abcdef'), true);
assert.equal(hasRoutePermission(permissions, '/apm'), true);
assert.equal(hasRoutePermission(permissions, '/apm/service-accounts'), false);
assert.equal(hasRoutePermission(permissions, '/monitor/services'), false);

console.log('APM dynamic route permission checks passed');
