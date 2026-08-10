import assert from 'node:assert/strict';
import {
  buildInfluxdbTarget,
  buildInfluxdbCredential,
  createInfluxdbCredential,
  restoreInfluxdbCredential,
  validateInfluxdbCredential,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/influxdbCredential';
import {
  CREDENTIAL_DESCRIPTORS,
  getCredentialDescriptor,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialDescriptors';

assert.deepEqual(createInfluxdbCredential(), {
  scheme: 'http',
  port: 8086,
  verify_tls: true,
  token: '',
});

assert.deepEqual(
  buildInfluxdbCredential({
    scheme: 'https',
    port: 8443,
    verify_tls: false,
    token: 'operator-secret',
  }),
  {
    scheme: 'https',
    port: 8443,
    verify_tls: false,
    token: 'operator-secret',
  },
);

assert.deepEqual(
  buildInfluxdbCredential({
    credential_id: 'cred-1',
    scheme: 'http',
    port: 8086,
    verify_tls: true,
    token: '******',
  }),
  {
    credential_id: 'cred-1',
    scheme: 'http',
    port: 8086,
    verify_tls: true,
  },
);

assert.deepEqual(
  restoreInfluxdbCredential(
    { credential_id: 'cred-1', scheme: 'https', port: 8443, verify_tls: false, token: '******' },
    false,
  ),
  {
    credential_id: 'cred-1',
    scheme: 'https',
    port: 8443,
    verify_tls: false,
    token: '******',
  },
);
assert.equal(
  restoreInfluxdbCredential(
    { scheme: 'https', port: 8443, verify_tls: false, token: '******' },
    true,
  ).token,
  '',
);

assert.equal(validateInfluxdbCredential(createInfluxdbCredential()), null);
assert.equal(
  validateInfluxdbCredential({ ...createInfluxdbCredential(), scheme: 'ftp' }),
  'scheme',
);
assert.equal(
  validateInfluxdbCredential({ ...createInfluxdbCredential(), port: 0 }),
  'port',
);

assert.equal(
  getCredentialDescriptor({ model_id: 'influxdb' })?.formKind,
  'influxdb',
);
assert.equal(
  CREDENTIAL_DESCRIPTORS.models.influxdb.fields
    .find((field) => field.key === 'influxToken')?.defaultValue,
  undefined,
);
assert.deepEqual(
  buildInfluxdbTarget('influx-2', [
    {
      value: 'influx-1',
      origin: { _id: 'influx-1', ip_addr: '10.0.0.1' },
    },
    {
      value: 'influx-2',
      origin: { _id: 'influx-2', ip_addr: '10.0.0.2' },
    },
  ]),
  {
    ip_range: '',
    instances: [{ _id: 'influx-2', ip_addr: '10.0.0.2' }],
  },
);

console.log('CMDB InfluxDB credential contract passed');
