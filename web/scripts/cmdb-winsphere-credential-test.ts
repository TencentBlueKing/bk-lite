import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

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

const created = buildWinSphereCredential(
  {
    user: 'api-reader',
    password: 'secret',
    https_port: 8443,
    verify_tls: true,
  },
);
assert.deepEqual(created, {
  user: 'api-reader',
  password: 'secret',
  https_port: 8443,
  verify_tls: true,
});
assert.equal('username' in created, false);
assert.equal('port' in created, false);
assert.equal('ssl' in created, false);

const edited = buildWinSphereCredential(
  {
    user: 'api-reader',
    password: '******',
    https_port: 443,
    verify_tls: false,
  },
);
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
    [{ user: 'api-reader', https_port: 8443, verify_tls: true }],
    true,
  ).password,
  '',
);

assert.equal(
  restoreWinSphereCredential(
    [{ user: 'api-reader', https_port: 8443, verify_tls: true }],
    false,
  ).https_port,
  8443,
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

const editorSource = readFileSync(
  new URL(
    '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.doesNotMatch(editorSource, /credentialSchema\?\.fields\.map/);
assert.match(editorSource, /shape === 'winsphere'/);
assert.match(editorSource, /value=\{item\.https_port\}/);
assert.match(editorSource, /updateItem\(index, \{ https_port:/);

console.log('WinSphere credential contract passed');
