import assert from 'node:assert/strict';
import { resolveDashboardInstanceIdentity } from '../src/app/monitor/dashboards/shared/utils/instance.ts';

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

console.log('dashboard instance identity tests passed');
