import assert from 'node:assert/strict';

import { buildLoginAuthCallbackUrl } from '../src/app/system-manager/utils/integrationLoginAuthCallbackUrl';

function run(name: string, fn: () => void) {
  fn();
  console.log(`  ✓ ${name}`);
}

run('prefers the backend-provided login auth callback URL over the current frontend origin', () => {
  assert.equal(
    buildLoginAuthCallbackUrl({
      currentOrigin: 'https://bklite.canway.net',
      backendCallbackUrl: 'https://auth.example.com/api/v1/core/api/login_auth/callback/',
    }),
    'https://auth.example.com/api/v1/core/api/login_auth/callback/',
  );
});

run('builds from the current frontend origin only when the backend callback URL is empty', () => {
  assert.equal(
    buildLoginAuthCallbackUrl({
      currentOrigin: 'https://bklite.canway.net',
      backendCallbackUrl: '',
    }),
    'https://bklite.canway.net/api/v1/core/api/login_auth/callback/',
  );
});

console.log('All login auth callback display URL tests passed.');
