import assert from 'node:assert/strict';

import {
  buildWinSphereCredential,
  createWinSphereCredential,
  restoreWinSphereCredential,
  validateWinSphereCredential,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/winsphereCredential';

const empty = createWinSphereCredential();
assert.deepEqual(empty, {
  user: '',
  password: '',
  https_port: 443,
  verify_tls: false,
});

const created = buildWinSphereCredential({
  user: 'api-reader',
  password: 'secret',
  https_port: 8443,
  verify_tls: true,
});
assert.deepEqual(created, {
  user: 'api-reader',
  password: 'secret',
  https_port: 8443,
  verify_tls: true,
});
assert.equal('username' in created, false);
assert.equal('port' in created, false);
assert.equal('ssl' in created, false);

const edited = buildWinSphereCredential({
  user: 'api-reader',
  password: '******',
  https_port: 443,
  verify_tls: false,
});
assert.equal('password' in edited, false);

assert.deepEqual(
  restoreWinSphereCredential(
    { user: 'api-reader', https_port: 8443, verify_tls: true },
    false,
  ),
  {
    user: 'api-reader',
    password: '******',
    https_port: 8443,
    verify_tls: true,
  },
);
assert.equal(
  restoreWinSphereCredential(
    { user: 'api-reader', https_port: 8443, verify_tls: true },
    true,
  ).password,
  '',
);

assert.equal(validateWinSphereCredential(created), null);
assert.equal(
  validateWinSphereCredential({ ...empty, user: '' }),
  'user',
);
assert.equal(
  validateWinSphereCredential({ ...empty, user: 'api-reader', password: '' }),
  'password',
);
assert.equal(
  validateWinSphereCredential({
    ...empty,
    user: 'api-reader',
    password: 'secret',
    https_port: 0,
  }),
  'https_port',
);

console.log('WinSphere credential contract passed');
