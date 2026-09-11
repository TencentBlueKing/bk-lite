import assert from 'node:assert/strict';
import {
  encodeInstanceIdValuesParam,
  parseLegacyParamList,
  parsePythonTupleString,
  resolveDashboardInstanceIdentity,
  resolveDashboardInstanceIdValues,
} from '../src/app/monitor/dashboards/shared/utils/instance.ts';

const podMetricsParams = new URLSearchParams(
  `monitorObjId=45&name=Pod&monitorObjDisplayName=Pod&instance_id=${encodeURIComponent("('k8s_prod','nginx_7c9f')")}&instance_id_keys=instance_id%2Cpod&instance_id_values=k8s_prod%2Cnginx_7c9f&instance_name=nginx-pod&view=metrics`
);

const podIdentity = resolveDashboardInstanceIdentity(podMetricsParams);
assert.equal(podIdentity.instanceId, "('k8s_prod','nginx_7c9f')");
assert.deepEqual(podIdentity.idValues, ['k8s_prod', 'nginx_7c9f']);

const tupleParams = new URLSearchParams(
  "instance_id_values=('cluster-a','pod-a')&instance_name=pod-a"
);
const tupleIdentity = resolveDashboardInstanceIdentity(tupleParams);
assert.equal(tupleIdentity.instanceId, "('cluster-a', 'pod-a')");
assert.deepEqual(tupleIdentity.idValues, ['cluster-a', 'pod-a']);

const opaqueValueParams = new URLSearchParams(
  'instance_id_values=ABCDEFGHIJKLMNOP%2Cpod-a&instance_name=pod-a'
);
const opaqueValueIdentity = resolveDashboardInstanceIdentity(opaqueValueParams);
assert.equal(opaqueValueIdentity.instanceId, "('ABCDEFGHIJKLMNOP', 'pod-a')");
assert.deepEqual(opaqueValueIdentity.idValues, ['ABCDEFGHIJKLMNOP', 'pod-a']);

const legacyParams = new URLSearchParams("instance_id=('host_01',)&instance_id_values=");
const legacyIdentity = resolveDashboardInstanceIdentity(legacyParams);
assert.equal(legacyIdentity.instanceId, "('host_01',)");
assert.deepEqual(legacyIdentity.idValues, ['host_01']);

const mysqlStorageKey = "('wwwdb.weops.com:3306',)";
const mysqlParams = new URLSearchParams(`instance_id=${encodeURIComponent(mysqlStorageKey)}`);
const mysqlIdentity = resolveDashboardInstanceIdentity(mysqlParams);
assert.equal(mysqlIdentity.instanceId, mysqlStorageKey);
assert.deepEqual(mysqlIdentity.idValues, ['wwwdb.weops.com:3306']);
assert.equal(
  parseLegacyParamList(mysqlStorageKey)[0],
  'wwwdb.weops.com:3306',
  'legacy comma-split must not be used as query instance_id',
);

const k8sNodeStorageKey = "('prod-cluster','node-1')";
const k8sNodeParams = new URLSearchParams(
  `instance_id=${encodeURIComponent(k8sNodeStorageKey)}&instance_id_keys=instance_id%2Cnode`
);
const k8sNodeIdentity = resolveDashboardInstanceIdentity(k8sNodeParams);
assert.equal(k8sNodeIdentity.instanceId, k8sNodeStorageKey);
assert.deepEqual(k8sNodeIdentity.idValues, ['prod-cluster', 'node-1']);

assert.deepEqual(
  resolveDashboardInstanceIdValues({ instance_id: mysqlStorageKey }),
  ['wwwdb.weops.com:3306'],
);
assert.deepEqual(
  parsePythonTupleString(mysqlStorageKey),
  ['wwwdb.weops.com:3306'],
);

const encodedMysqlValues = encodeInstanceIdValuesParam(['wwwdb.weops.com:3306']);
assert.equal(encodedMysqlValues, '["wwwdb.weops.com:3306"]');
const mysqlSwitchParams = new URLSearchParams();
mysqlSwitchParams.set('instance_id', mysqlStorageKey);
mysqlSwitchParams.set('instance_id_values', encodedMysqlValues);
const mysqlSwitchIdentity = resolveDashboardInstanceIdentity(mysqlSwitchParams);
assert.equal(mysqlSwitchIdentity.instanceId, mysqlStorageKey);
assert.deepEqual(mysqlSwitchIdentity.idValues, ['wwwdb.weops.com:3306']);

const encodedCommaValues = encodeInstanceIdValuesParam(['cluster-a', 'pod,with,comma']);
const commaSwitchParams = new URLSearchParams();
commaSwitchParams.set('instance_id', "('cluster-a','pod,with,comma')");
commaSwitchParams.set('instance_id_values', encodedCommaValues);
const commaSwitchIdentity = resolveDashboardInstanceIdentity(commaSwitchParams);
assert.deepEqual(commaSwitchIdentity.idValues, ['cluster-a', 'pod,with,comma']);
assert.notEqual(
  commaSwitchIdentity.idValues.join('|'),
  parseLegacyParamList('cluster-a,pod,with,comma').join('|'),
  'comma-join must not be used as instance_id_values',
);

console.log('dashboard instance identity tests passed');
