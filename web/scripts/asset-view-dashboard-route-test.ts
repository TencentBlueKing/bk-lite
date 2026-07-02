import * as assert from 'node:assert/strict';
import { buildAssetViewUrl } from '../src/app/monitor/(pages)/integration/asset/viewRoute';

const k8sClusterUrl = buildAssetViewUrl({
  objectId: 42,
  monitorItem: {
    name: 'Cluster',
    display_name: 'K8s集群',
    icon: 'k8s-icon',
    instance_id_keys: ['instance_id']
  },
  row: {
    instance_id: 'mac',
    instance_name: 'mac',
    instance_id_values: 'mac'
  },
  resolveProfessionalDashboardUrl: (objectName, _objectDisplayName, queryString) =>
    objectName === 'Cluster'
      ? `/monitor/view/dashboard/k8s-cluster?${queryString}`
      : ''
});

assert.ok(
  k8sClusterUrl.startsWith('/monitor/view/dashboard/k8s-cluster?'),
  `expected professional dashboard route, got ${k8sClusterUrl}`
);

const k8sClusterParams = new URLSearchParams(k8sClusterUrl.split('?')[1]);
assert.equal(k8sClusterParams.get('monitorObjId'), '42');
assert.equal(k8sClusterParams.get('name'), 'Cluster');
assert.equal(k8sClusterParams.get('monitorObjDisplayName'), 'K8s集群');
assert.equal(k8sClusterParams.get('instance_id'), 'mac');
assert.equal(k8sClusterParams.get('instance_name'), 'mac');
assert.equal(k8sClusterParams.get('instance_id_values'), 'mac');
assert.equal(k8sClusterParams.get('instance_id_keys'), 'instance_id');

const fallbackUrl = buildAssetViewUrl({
  objectId: 7,
  monitorItem: {
    name: 'UnregisteredObject',
    display_name: '未注册对象'
  },
  row: {
    instance_id: 'unknown-1',
    instance_name: 'unknown-1'
  }
});

assert.ok(
  fallbackUrl.startsWith('/monitor/view/detail?'),
  `expected legacy detail fallback route, got ${fallbackUrl}`
);

const fallbackParams = new URLSearchParams(fallbackUrl.split('?')[1]);
assert.equal(fallbackParams.get('instance_id_keys'), 'instance_id');

console.log('asset view dashboard route tests passed');
