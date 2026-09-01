import assert from 'node:assert/strict';

import nextConfig from '../next.config.mjs';

assert.ok(
  nextConfig.allowedDevOrigins?.includes('bklite.weops.com'),
  'Next dev must allow the shared bklite.weops.com development origin'
);
assert.ok(
  nextConfig.allowedDevOrigins?.includes('10.10.40.53'),
  'Next dev must allow the local LAN IP used for on-network access'
);

console.log('next dev origin config ok');
