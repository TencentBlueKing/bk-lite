import assert from 'node:assert/strict';

import nextConfig from '../next.config.mjs';

assert.ok(
  nextConfig.allowedDevOrigins?.includes('bklite.weops.com'),
  'Next dev must allow the shared bklite.weops.com development origin'
);

console.log('next dev origin config ok');
