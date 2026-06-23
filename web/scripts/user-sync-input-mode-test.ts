import * as assert from 'node:assert/strict';
import {
  getRootDepartmentInputMode,
  isDepartmentSelectMode,
  isManualInputMode,
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

assert.equal(getRootDepartmentInputMode(null), 'department_select');
assert.equal(getRootDepartmentInputMode(departmentSelectTemplate), 'department_select');
assert.equal(getRootDepartmentInputMode(manualInputTemplate), 'manual_input');
assert.equal(isDepartmentSelectMode(departmentSelectTemplate), true);
assert.equal(isManualInputMode(manualInputTemplate), true);

console.log('user sync input mode tests passed');
