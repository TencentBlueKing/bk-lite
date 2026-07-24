import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { toMonitorNodeOption } from '../src/app/monitor/hooks/integration/nodeOptions';

const configured = toMonitorNodeOption(
  {
    id: 'node-1',
    name: '生产节点',
    ip: '10.0.0.1',
    deployment_state: 'configured'
  },
  '已接入'
);

assert.deepEqual(configured, {
  id: 'node-1',
  name: '生产节点',
  ip: '10.0.0.1',
  deployment_state: 'configured',
  label: '生产节点 (10.0.0.1)',
  value: 'node-1',
  disabled: true,
  disabledReason: '已接入'
});

const available = toMonitorNodeOption(
  {
    id: 'node-2',
    name: '备用节点',
    ip: '10.0.0.2',
    deployment_state: 'available'
  },
  '已接入'
);

assert.equal(available.disabled, false);
assert.equal(available.disabledReason, undefined);

const rendererSource = readFileSync(
  resolve(process.cwd(), 'src/app/monitor/hooks/integration/useConfigRenderer.tsx'),
  'utf8'
);
assert.match(rendererSource, /disabled=\{option\.disabled\}/);
assert.match(rendererSource, /option\.disabledReason/);
assert.match(rendererSource, /optionFilterProp="label"/);
assert.match(rendererSource, /label=\{option\.label\}/);
assert.match(rendererSource, /className="min-w-0 truncate"/);

for (const localeFile of ['zh.json', 'en.json']) {
  const locale = JSON.parse(
    readFileSync(resolve(process.cwd(), `src/app/monitor/locales/${localeFile}`), 'utf8')
  );
  assert.equal(
    typeof locale.monitor.integrations.hostMonitoringAlreadyConfigured,
    'string'
  );
}

console.log('monitor host deployment option tests passed');
