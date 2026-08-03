import assert from 'node:assert/strict';

import { DataMapper } from '../src/app/monitor/hooks/integration/useDataMapper';
import { getBaseInstanceColumn } from '../src/app/monitor/utils/common';

const translate = (key: string) => key;
const probeObject = {
  id: 1,
  name: 'Website',
  type: 'Web',
  level: 'base',
  instance_summary_columns: [
    { fact: 'collector.nodes', title: 'monitor.views.probeNodes', order: 10 },
    { fact: 'probe.target', title: 'monitor.views.probeTarget', order: 20 }
  ]
} as any;
const databaseObject = {
  id: 2,
  name: 'Mysql',
  type: 'Database',
  level: 'base',
  instance_summary_columns: [
    { fact: 'asset.ip', title: 'monitor.views.assetIp', order: 10 }
  ]
} as any;

assert.deepEqual(
  getBaseInstanceColumn({ row: probeObject, objects: [probeObject], t: translate }).map(
    (column: any) => column.key
  ),
  ['instance_name', 'summary_fact:collector.nodes', 'summary_fact:probe.target']
);
assert.deepEqual(
  getBaseInstanceColumn({ row: databaseObject, objects: [databaseObject], t: translate }).map(
    (column: any) => column.key
  ),
  ['instance_name', 'summary_fact:asset.ip']
);

const payload = DataMapper.transformAutoRequest(
  {},
  [{
    node_ids: ['node-a', 'node-b'],
    url: 'https://example.com/health',
    instance_name: '北京业务站',
    group_ids: [1]
  }],
  {
    config_type: ['web'],
    collect_type: 'web',
    collector: 'Telegraf',
    instance_type: 'web',
    instance_id: '{{instance_type}}_{{url}}',
    objectId: '1',
    tableColumns: [],
    nodeList: [
      { id: 'node-a', label: '北京节点 (10.0.0.1)' },
      { id: 'node-b', label: '上海节点 (10.0.0.2)' }
    ]
  }
);

assert.equal('probe_nodes' in payload.instances[0], false);
