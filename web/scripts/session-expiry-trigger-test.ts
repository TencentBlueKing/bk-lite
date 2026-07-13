import assert from 'node:assert/strict';

import { shouldTriggerSessionExpiry } from '../src/utils/sessionExpiry';

const triggerSessionExpiry = shouldTriggerSessionExpiry as unknown as (
  input: string,
  hasAuthenticatedSession: boolean,
) => boolean;

const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window');
const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'document');
const location = {
  origin: 'https://bk-lite.example.com',
  pathname: '/monitor',
};

Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: { location },
});
Object.defineProperty(globalThis, 'document', {
  configurable: true,
  value: { cookie: '' },
});

try {
  assert.equal(
    triggerSessionExpiry('/api/proxy/monitor/api/metrics/', true),
    true,
    'an authenticated NextAuth session should trigger expiry handling without a readable auth cookie',
  );
  assert.equal(
    triggerSessionExpiry('/api/proxy/monitor/api/metrics/', false),
    false,
    'unauthenticated requests must not trigger the global expiry flow',
  );
  assert.equal(
    triggerSessionExpiry('/api/proxy/core/api/login/', true),
    false,
    'login requests must remain excluded',
  );
  assert.equal(
    triggerSessionExpiry('https://other.example.com/api/metrics/', true),
    false,
    'cross-origin requests must remain excluded',
  );

  location.pathname = '/auth/signin';
  assert.equal(
    triggerSessionExpiry('/api/proxy/monitor/api/metrics/', true),
    false,
    'auth pages must not trigger the expiry flow',
  );
} finally {
  if (windowDescriptor) {
    Object.defineProperty(globalThis, 'window', windowDescriptor);
  } else {
    delete (globalThis as { window?: unknown }).window;
  }
  if (documentDescriptor) {
    Object.defineProperty(globalThis, 'document', documentDescriptor);
  } else {
    delete (globalThis as { document?: unknown }).document;
  }
}

console.log('session expiry trigger tests passed');
