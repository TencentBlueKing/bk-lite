import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  getEffectiveRootDepartmentFieldKey,
  excludeUserSyncRootScope,
  getUserSyncBusinessConfigDefaults,
  getUserSyncEditFormBusinessConfig,
  getRootDepartmentFieldKey,
  getRootDepartmentInputMode,
  isDepartmentSelectMode,
  isManualInputMode,
  mergeUserSyncBusinessConfigWithDefaults,
  normalizeUserSyncBusinessConfigForSubmit,
  resolveUserSyncTemplate,
  shouldFetchDepartmentOptions,
} from '../src/app/system-manager/utils/userSyncUtils';
import type { BusinessTemplate, ProviderManifest } from '../src/app/system-manager/types/integration-center';

const userSyncTypes = readFileSync(
  new URL('../src/app/system-manager/types/user-sync.ts', import.meta.url),
  'utf8',
);

const departmentSelectTemplate: BusinessTemplate = {
  title: 'User Sync',
  groups: [
    {
      key: 'pull',
      title: '拉取配置',
      description: '',
      fields: [
        {
          key: 'root_department_id',
          label: '根部门 ID',
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
          input_mode: 'department_select',
        },
      ],
    },
  ],
  available_external_fields: [],
  matchable_fields: [],
  receivable_fields: [],
  default_external_match_field: '',
  default_external_receive_field: '',
};

const manualInputTemplate: BusinessTemplate = {
  ...departmentSelectTemplate,
  groups: [
    {
      ...departmentSelectTemplate.groups[0],
      fields: [
        {
          ...departmentSelectTemplate.groups[0].fields[0],
          input_mode: 'manual_input',
        },
      ],
    },
  ],
};

const typedDepartmentSelectTemplate: BusinessTemplate = {
  ...departmentSelectTemplate,
  groups: [
    {
      ...departmentSelectTemplate.groups[0],
      fields: [
        ...departmentSelectTemplate.groups[0].fields,
        {
          key: 'department_id_type',
          label: '部门 ID 类型',
          field_type: 'select',
          required: true,
          secret: false,
          write_only: false,
          mask_strategy: 'full',
          default: 'department_id',
          placeholder: '',
          help_text: '',
          options: [{ value: 'department_id', label: 'department_id' }],
          reset_capabilities: [],
        },
      ],
    },
  ],
};

const adManualInputTemplate: BusinessTemplate = {
  ...departmentSelectTemplate,
  groups: [
    {
      ...departmentSelectTemplate.groups[0],
      fields: [
        {
          ...departmentSelectTemplate.groups[0].fields[0],
          key: 'root_dns',
          label: '同步拉取 DN',
          field_type: 'textarea',
          input_mode: 'manual_input',
        },
        {
          key: 'user_object_class',
          label: '用户对象类',
          field_type: 'string',
          required: true,
          secret: false,
          write_only: false,
          mask_strategy: 'full',
          default: 'user',
          placeholder: 'user',
          help_text: '',
          options: [],
          reset_capabilities: [],
        },
        {
          key: 'user_filter',
          label: '用户对象过滤',
          field_type: 'textarea',
          required: true,
          secret: false,
          write_only: false,
          mask_strategy: 'full',
          default: '(&(objectCategory=Person)(sAMAccountName=*))',
          placeholder: '(&(objectCategory=Person)(sAMAccountName=*))',
          help_text: '',
          options: [],
          reset_capabilities: [],
        },
      ],
    },
  ],
};

const adProvider: ProviderManifest = {
  key: 'ad',
  name: 'Active Directory',
  description: '',
  instance_template: [],
  instance_templates: {},
  business_templates: { user_sync_form: adManualInputTemplate },
  capabilities: [{
    key: 'user_sync',
    name: 'User Sync',
    description: '',
    connection_template: [],
    business_template: 'user_sync_form',
  }],
};

assert.equal(getRootDepartmentInputMode(null), 'department_select');
assert.equal(getRootDepartmentInputMode(departmentSelectTemplate), 'department_select');
assert.equal(getRootDepartmentInputMode(manualInputTemplate), 'manual_input');
assert.equal(getRootDepartmentFieldKey(departmentSelectTemplate), 'root_department_id');
assert.equal(getRootDepartmentFieldKey(adManualInputTemplate), 'root_dns');
assert.equal(
  getEffectiveRootDepartmentFieldKey({ root_scope_field: 'root_dns' }, departmentSelectTemplate),
  'root_dns',
);
assert.equal(
  getEffectiveRootDepartmentFieldKey({ root_scope_field: '' }, adManualInputTemplate),
  'root_dns',
);
assert.equal(getRootDepartmentInputMode(adManualInputTemplate), 'manual_input');
assert.equal(isDepartmentSelectMode(departmentSelectTemplate), true);
assert.equal(isManualInputMode(manualInputTemplate), true);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: departmentSelectTemplate }), true);
assert.equal(
  shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: typedDepartmentSelectTemplate, departmentIdType: '' }),
  false,
  '飞书部门 ID 类型尚未写入表单时不能请求部门选项',
);
assert.equal(
  shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: typedDepartmentSelectTemplate, departmentIdType: 'department_id' }),
  true,
);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: adManualInputTemplate }), false);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: undefined, template: adManualInputTemplate }), false);
assert.equal(
  resolveUserSyncTemplate(1, [], [adProvider], 'ad'),
  adManualInputTemplate,
);
assert.deepEqual(
  getUserSyncBusinessConfigDefaults(adManualInputTemplate, { excludeRootScope: true }),
  {
    user_object_class: 'user',
    user_filter: '(&(objectCategory=Person)(sAMAccountName=*))',
  },
);
assert.deepEqual(
  mergeUserSyncBusinessConfigWithDefaults(
    { root_dns: 'OU=Users,DC=example,DC=com', user_filter: '(mail=*)' },
    adManualInputTemplate,
    { excludeRootScope: true },
  ),
  {
    user_object_class: 'user',
    user_filter: '(mail=*)',
    root_dns: 'OU=Users,DC=example,DC=com',
  },
);
assert.deepEqual(
  excludeUserSyncRootScope(
    { root_department_id: '8eba59d61667gb86', department_id_type: 'department_id', user_id_type: 'user_id' },
    'root_department_id',
  ),
  { department_id_type: 'department_id', user_id_type: 'user_id' },
  '编辑态在部门选项解析前不能将原始根部门 ID 放进 TreeSelect 的表单值',
);
assert.deepEqual(
  getUserSyncEditFormBusinessConfig(
    { root_dns: ['OU=PAAS,DC=corp,DC=example,DC=com'], user_filter: '(mail=*)' },
    adManualInputTemplate,
    'root_dns',
  ),
  {
    user_object_class: 'user',
    user_filter: '(mail=*)',
    root_dns: 'OU=PAAS,DC=corp,DC=example,DC=com',
  },
  'AD 编辑弹窗必须把已保存的 root_dns 列表回显为多行文本',
);
assert.deepEqual(
  getUserSyncEditFormBusinessConfig(
    {
      root_dns: ['OU=BizA,DC=corp,DC=com', 'OU=BizC,DC=corp,DC=com'],
      user_filter: '(mail=*)',
    },
    adManualInputTemplate,
    'root_dns',
  ),
  {
    user_object_class: 'user',
    user_filter: '(mail=*)',
    root_dns: 'OU=BizA,DC=corp,DC=com\nOU=BizC,DC=corp,DC=com',
  },
);
assert.deepEqual(
  getUserSyncEditFormBusinessConfig(
    { root_department_id: '8eba59d61667gb86', department_id_type: 'department_id', user_id_type: 'user_id' },
    departmentSelectTemplate,
    'root_department_id',
  ),
  { department_id_type: 'department_id', user_id_type: 'user_id' },
  '部门树编辑态仍不能把原始根部门 ID 提前写进表单',
);
assert.deepEqual(
  normalizeUserSyncBusinessConfigForSubmit({
    root_dns: 'OU=BizA,DC=corp,DC=com\nOU=BizC,DC=corp,DC=com\n',
    user_filter: '(mail=*)',
  }),
  {
    root_dns: ['OU=BizA,DC=corp,DC=com', 'OU=BizC,DC=corp,DC=com'],
    user_filter: '(mail=*)',
  },
);
assert.deepEqual(
  normalizeUserSyncBusinessConfigForSubmit({
    root_dn: 'OU=PAAS,DC=corp,DC=com',
    user_filter: '(mail=*)',
  }),
  {
    root_dns: ['OU=PAAS,DC=corp,DC=com'],
    user_filter: '(mail=*)',
  },
  '提交时把旧 root_dn 迁成 root_dns 列表',
);

const configModal = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigModal.tsx', import.meta.url),
  'utf8',
);
assert.match(
  configModal,
  /getUserSyncEditFormBusinessConfig\(/,
  '编辑弹窗必须按 input_mode 组装表单初值，不能无条件剥掉根范围',
);
assert.doesNotMatch(
  configModal,
  /excludeUserSyncRootScope\(/,
  '剥根范围只能发生在部门树模式的 helper 内部',
);
assert.doesNotMatch(
  userSyncTypes,
  /\bis_all\b/,
  'department option nodes must only model real Provider departments',
);

const configFields = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx', import.meta.url),
  'utf8',
);
assert.match(
  configFields,
  /isPullDnsListField/,
  'AD 拉取 DN 必须有独立列表字段分支',
);
assert.match(
  configFields,
  /autoSize=\{isPullDnsListField \? \{ minRows: 2, maxRows: 8 \}/,
  '拉取 DN 列表框应变高，避免固定 4 行空洞',
);
assert.match(
  configFields,
  /font-mono text-\[13px\].*whitespace-nowrap|whitespace-nowrap.*font-mono/,
  'DN 列表应使用等宽字体，与过滤表达式文本框区分',
);
assert.match(
  configFields,
  /wrap=\{isPullDnsListField \? 'off'/,
  '长 DN 禁止软换行，避免与「每行一个」语义冲突',
);
assert.match(
  configFields,
  /extra=\{isPullDnsListField && field\.help_text/,
  '每行一个 DN 的说明必须常显，不能只藏在 tooltip',
);

console.log('user sync input mode tests passed');
