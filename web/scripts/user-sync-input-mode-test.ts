import * as assert from 'node:assert/strict';
import {
  getUserSyncBusinessConfigDefaults,
  getRootDepartmentFieldKey,
  getRootDepartmentInputMode,
  isDepartmentSelectMode,
  isManualInputMode,
  mergeUserSyncBusinessConfigWithDefaults,
  shouldFetchDepartmentOptions,
} from '../src/app/system-manager/utils/userSyncUtils';
import type { BusinessTemplate } from '../src/app/system-manager/types/integration-center';

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

const adManualInputTemplate: BusinessTemplate = {
  ...departmentSelectTemplate,
  groups: [
    {
      ...departmentSelectTemplate.groups[0],
      fields: [
        {
          ...departmentSelectTemplate.groups[0].fields[0],
          key: 'root_dn',
          label: '同步起始目录',
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

assert.equal(getRootDepartmentInputMode(null), 'department_select');
assert.equal(getRootDepartmentInputMode(departmentSelectTemplate), 'department_select');
assert.equal(getRootDepartmentInputMode(manualInputTemplate), 'manual_input');
assert.equal(getRootDepartmentFieldKey(departmentSelectTemplate), 'root_department_id');
assert.equal(getRootDepartmentFieldKey(adManualInputTemplate), 'root_dn');
assert.equal(getRootDepartmentInputMode(adManualInputTemplate), 'manual_input');
assert.equal(isDepartmentSelectMode(departmentSelectTemplate), true);
assert.equal(isManualInputMode(manualInputTemplate), true);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: departmentSelectTemplate }), true);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: 1, template: adManualInputTemplate }), false);
assert.equal(shouldFetchDepartmentOptions({ selectedInstanceId: undefined, template: adManualInputTemplate }), false);
assert.deepEqual(
  getUserSyncBusinessConfigDefaults(adManualInputTemplate, { excludeRootScope: true }),
  {
    user_object_class: 'user',
    user_filter: '(&(objectCategory=Person)(sAMAccountName=*))',
  },
);
assert.deepEqual(
  mergeUserSyncBusinessConfigWithDefaults(
    { root_dn: 'OU=Users,DC=example,DC=com', user_filter: '(mail=*)' },
    adManualInputTemplate,
    { excludeRootScope: true },
  ),
  {
    user_object_class: 'user',
    user_filter: '(mail=*)',
    root_dn: 'OU=Users,DC=example,DC=com',
  },
);

console.log('user sync input mode tests passed');
