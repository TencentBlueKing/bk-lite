import assert from 'node:assert/strict';

import { buildIntegrationFieldRules } from '../src/app/system-manager/utils/intergrationCenter';

const stringRules = buildIntegrationFieldRules({
  key: 'connection_url',
  label: '服务器 IP',
  field_type: 'string',
  required: true,
  secret: false,
  write_only: false,
  mask_strategy: 'full',
  default: null,
  placeholder: '',
  help_text: '',
  options: [],
  reset_capabilities: [],
});

assert.deepEqual(stringRules, [{ required: true, whitespace: true }]);

const numberRules = buildIntegrationFieldRules({
  key: 'timeout',
  label: '超时时间',
  field_type: 'number',
  required: true,
  secret: false,
  write_only: false,
  mask_strategy: 'full',
  default: 10,
  placeholder: '',
  help_text: '',
  options: [],
  reset_capabilities: [],
});

assert.deepEqual(numberRules, [{ required: true }]);

console.log('integration center field rules tests passed');
