import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  buildWinSphereCredential,
  createWinSphereCredential,
  restoreWinSphereCredential,
  validateWinSphereCredential,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/winsphereCredential';

const schema = {
  schema_version: 1,
  allow_multiple: false,
  allow_unknown_fields: false,
  encrypted_fields: ['password'],
  fields: [
    { key: 'user', type: 'string' as const, required: true, label: '账号' },
    { key: 'password', type: 'password' as const, required: true, label: '密码' },
    {
      key: 'https_port',
      type: 'integer' as const,
      required: true,
      default: 443,
      min: 1,
      max: 65535,
      label: '端口',
    },
    {
      key: 'verify_tls',
      type: 'boolean' as const,
      required: true,
      default: false,
      label: 'TLS',
    },
  ],
};

const empty = createWinSphereCredential(schema);
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
  schema,
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
  schema,
);
assert.equal('password' in edited, false);

assert.deepEqual(
  restoreWinSphereCredential(
    { user: 'api-reader', https_port: 8443, verify_tls: true },
    false,
    schema,
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
    schema,
  ).password,
  '',
);
assert.equal(
  restoreWinSphereCredential(
    [{ user: 'api-reader', https_port: 8443, verify_tls: true }],
    false,
    schema,
  ).https_port,
  8443,
);

assert.equal(validateWinSphereCredential(created, schema), null);
assert.equal(
  validateWinSphereCredential({ ...empty, user: '' }, schema),
  'user',
);
assert.equal(
  validateWinSphereCredential(
    { ...empty, user: 'api-reader', password: '' },
    schema,
  ),
  'password',
);
assert.equal(
  validateWinSphereCredential({
    ...empty,
    user: 'api-reader',
    password: 'secret',
    https_port: 0,
  }, schema),
  'https_port',
);

const editorSource = readFileSync(
  new URL(
    '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx',
    import.meta.url,
  ),
  'utf8',
);
assert.match(editorSource, /credentialSchema\?\.fields\.map/);
assert.match(editorSource, /<label className=.*htmlFor=/);
assert.match(editorSource, /id=\{inputId\}/);

console.log('WinSphere credential contract passed');
