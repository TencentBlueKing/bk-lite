import type { IntegrationBatchEditColumnConfig } from '@/app/monitor/components/integration-contract/integration-batch-edit-modal';
import type { IntegrationExcelImportColumnConfig } from '@/app/monitor/components/integration-contract/integration-excel-import-modal';
import {
  createAuthCredentialFieldConfig,
  createAuthTypeFieldConfig,
  createAuthTypeOptions,
} from '@/components/auth-secret-field/field-presets';

export const integrationAuthTypeOptions = createAuthTypeOptions({
  password: 'Password',
  privateKey: 'Private key',
});

export const integrationStoryNodeList = [
  { label: 'node-a (10.0.0.1)', value: 1 },
  { label: 'node-b (10.0.0.2)', value: 2 },
];

export const integrationBatchEditColumns: IntegrationBatchEditColumnConfig[] = [
  createAuthTypeFieldConfig({
    label: 'Auth type',
    optionLabels: {
      password: 'Password',
      privateKey: 'Private key',
    },
  }),
  createAuthCredentialFieldConfig({
    label: 'Credential',
    placeholder: 'Input credential',
  }),
  {
    name: 'node_ids',
    label: 'Node',
    type: 'select',
    required: true,
    options: [],
  },
  {
    name: 'instance_name',
    label: 'Instance name',
    type: 'input',
    widget_props: { placeholder: 'Input instance name' },
  },
  {
    name: 'group_ids',
    label: 'Group',
    type: 'group_select',
    widget_props: { placeholder: 'Select group' },
  },
];

export const integrationBatchEditColumnsWithInterval: IntegrationBatchEditColumnConfig[] = [
  ...integrationBatchEditColumns,
  {
    name: 'interval',
    label: 'Interval',
    type: 'inputNumber',
    widget_props: { min: 1, addonAfter: 's' },
  },
];

export const integrationExcelImportColumns: IntegrationExcelImportColumnConfig[] = [
  createAuthTypeFieldConfig({
    label: 'Auth type',
    optionLabels: {
      password: 'Password',
      privateKey: 'Private key',
    },
    defaultValue: 'password',
    useWidgetProps: true,
  }),
  createAuthCredentialFieldConfig({
    label: 'Credential',
    excelLabel: 'Login password',
  }),
  {
    name: 'node_ids',
    label: 'Node',
    type: 'select',
    required: true,
  },
  {
    name: 'instance_name',
    label: 'Instance name',
    type: 'input',
    required: true,
  },
  {
    name: 'group_ids',
    label: 'Group',
    type: 'group_select',
    required: true,
  },
];

export const integrationExcelImportColumnsWithInterval: IntegrationExcelImportColumnConfig[] = [
  ...integrationExcelImportColumns,
  {
    name: 'interval',
    label: 'Interval',
    type: 'inputNumber',
    widget_props: { min: 1, max: 3600 },
  },
];

export const integrationSingleCredentialColumn = [
  createAuthCredentialFieldConfig({
    label: 'Login credential',
    placeholder: 'Upload a private key or input a password',
  }),
];
