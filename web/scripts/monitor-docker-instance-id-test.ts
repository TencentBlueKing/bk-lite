import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { DataMapper } from '../src/app/monitor/hooks/integration/useDataMapper';

const uiPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../server/apps/monitor/support-files/plugins/Telegraf/docker/docker/UI.json'
);
const ui = JSON.parse(fs.readFileSync(uiPath, 'utf8')) as { instance_id: string };
const DEFAULT_ENDPOINT = 'unix:///var/run/docker.sock';
const OLD_TEMPLATE = '{{cloud_region}}_docker_{{endpoint}}';

assert.equal(
  ui.instance_id,
  '{{cloud_region}}_docker_{{ip}}_{{endpoint}}',
  'Docker instance_id must namespace by type and include node IP plus endpoint'
);

const context = {
  config_type: ['docker'],
  collect_type: 'docker',
  collector: 'Telegraf',
  instance_type: 'docker',
  instance_id: ui.instance_id,
  nodeList: [
    {
      id: 'node-a',
      value: 'node-a',
      name: 'host-a',
      ip: '10.20.6.209',
      cloud_region: 1
    },
    {
      id: 'node-b',
      value: 'node-b',
      name: 'host-b',
      ip: '10.20.5.200',
      cloud_region: 1
    }
  ]
};

const build = (rows: Array<Record<string, unknown>>, template = ui.instance_id) =>
  DataMapper.transformAutoRequest({}, rows, { ...context, instance_id: template });

const firstHost = build([
  {
    node_ids: ['node-a'],
    endpoint: DEFAULT_ENDPOINT,
    instance_name: 'docker-10-20-6-209'
  }
]);
const secondHost = build([
  {
    node_ids: ['node-b'],
    endpoint: DEFAULT_ENDPOINT,
    instance_name: 'docker-10.20.5.200'
  }
]);

assert.equal(
  firstHost.instances[0].instance_id,
  DataMapper.hashInstanceId(`1_docker_10.20.6.209_${DEFAULT_ENDPOINT}`)
);
assert.equal(
  secondHost.instances[0].instance_id,
  DataMapper.hashInstanceId(`1_docker_10.20.5.200_${DEFAULT_ENDPOINT}`)
);
assert.notEqual(
  firstHost.instances[0].instance_id,
  secondHost.instances[0].instance_id,
  'same cloud region and default sock must still produce distinct IDs per node IP'
);

const renamed = build([
  {
    node_ids: ['node-a'],
    endpoint: DEFAULT_ENDPOINT,
    instance_name: 'docker-renamed'
  }
]);
assert.equal(
  renamed.instances[0].instance_id,
  firstHost.instances[0].instance_id,
  'display name must not participate in Docker identity'
);

const tcpEndpoint = build([
  {
    node_ids: ['node-a'],
    endpoint: 'tcp://127.0.0.1:2375',
    instance_name: 'docker-tcp'
  }
]);
assert.notEqual(
  tcpEndpoint.instances[0].instance_id,
  firstHost.instances[0].instance_id,
  'different endpoints on the same node remain distinct targets'
);

const oldFirst = build(
  [
    {
      node_ids: ['node-a'],
      endpoint: DEFAULT_ENDPOINT,
      instance_name: 'docker-10-20-6-209'
    }
  ],
  OLD_TEMPLATE
);
const oldSecond = build(
  [
    {
      node_ids: ['node-b'],
      endpoint: DEFAULT_ENDPOINT,
      instance_name: 'docker-10.20.5.200'
    }
  ],
  OLD_TEMPLATE
);
assert.equal(
  oldFirst.instances[0].instance_id,
  oldSecond.instances[0].instance_id,
  'legacy template without IP collides for two hosts on the same sock'
);

console.log('monitor-docker-instance-id test passed');
