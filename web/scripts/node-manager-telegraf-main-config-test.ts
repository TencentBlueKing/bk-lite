import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  applyConfigFormValues,
  buildConfigModalFormData,
  resolveMainConfig
} from '../src/app/node-manager/utils/collectorConfig.ts';

const telegrafTemplate = `[[inputs.cpu]]
  percpu = true
`;

const configs = [
  {
    key: 'cfg-telegraf',
    id: 'cfg-telegraf',
    collector_id: 'telegraf_linux'
  },
  {
    key: 'cfg-vector',
    id: 'cfg-vector',
    collector_id: 'vector_linux'
  }
];

assert.equal(
  resolveMainConfig(configs, { collector_id: 'telegraf_linux' })?.key,
  'cfg-telegraf',
  'should resolve Telegraf main config by collector_id'
);

assert.equal(
  resolveMainConfig(configs, {
    collector_id: 'telegraf_linux_arm64',
    configuration_id: 'cfg-telegraf'
  })?.key,
  'cfg-telegraf',
  'should prefer configuration_id when sidecar reports an arch-specific Telegraf id'
);

assert.equal(
  resolveMainConfig([], { collector_id: 'telegraf_linux' }),
  null,
  'clicking Telegraf before configs arrive must not invent a main config'
);

assert.equal(
  resolveMainConfig(configs, { collector_id: 'telegraf_linux' })?.key,
  'cfg-telegraf',
  'the same click after configs arrive should show Telegraf main config'
);

const formData = buildConfigModalFormData({
  key: 'cfg-telegraf',
  content: telegrafTemplate
});
assert.equal(formData.configInfo, telegrafTemplate);

assert.equal(
  applyConfigFormValues(null, 'edit', formData),
  false,
  'first Modal open has no form instance; setFieldsValue is a no-op and the editor stays empty'
);

let applied: Record<string, unknown> | null = null;
assert.equal(
  applyConfigFormValues(
    {
      resetFields: () => {
        applied = null;
      },
      setFieldsValue: (values) => {
        applied = values;
      }
    },
    'edit',
    formData
  ),
  true
);
assert.equal(applied?.configInfo, telegrafTemplate);

const configModal = readFileSync(
  resolve(
    import.meta.dirname,
    '../src/app/node-manager/(pages)/cloudregion/node/collectorDetail/configModal.tsx'
  ),
  'utf8'
);
const collectorDetail = readFileSync(
  resolve(
    import.meta.dirname,
    '../src/app/node-manager/(pages)/cloudregion/node/collectorDetail/index.tsx'
  ),
  'utf8'
);

assert.match(
  configModal,
  /initialValues=\{configForm\}/,
  'main config editor must mount with template values on first open'
);
assert.match(
  configModal,
  /destroyOnHidden/,
  'main config modal must remount the form so the first open is not an empty leftover'
);
assert.doesNotMatch(
  configModal,
  /resetFields\(\)/,
  'do not reset the unmounted form on first open'
);
assert.doesNotMatch(
  configModal,
  /value=\{configForm\.configInfo/,
  'editor must take Form.Item value instead of a separately passed snapshot'
);
assert.doesNotMatch(
  configModal,
  /onChange=\{undefined\}/,
  'editor must keep the Form.Item onChange'
);
assert.match(
  collectorDetail,
  /resolveMainConfig/,
  'node detail must resolve the currently selected collector after configs load'
);
assert.match(
  collectorDetail,
  /selectedCollectorRef/,
  'late config responses must follow the collector the user actually opened'
);
assert.match(
  collectorDetail,
  /setAllConfigs\(\[\]\)/,
  'closing the drawer must drop cached configs so the next open refetches cleanly'
);

console.log('node-manager-telegraf-main-config tests passed');
