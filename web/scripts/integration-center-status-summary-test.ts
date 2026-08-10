import assert from 'node:assert/strict';

import {
  getAvailableIntegrationTabs,
  getIntegrationBaseCapabilityStatusItems,
  getIntegrationDetailSummaryItems,
  getIntegrationDiagnosticMessage,
} from '../src/app/system-manager/utils/integrationCenter';

const t = (key: string) => key;

const readyInstance = {
  status: 'ready' as const,
  capability_status: { user_sync: 'pending_verification' as const },
  capability_enabled: { user_sync: true },
};

assert.deepEqual(
  getAvailableIntegrationTabs({
    capability_status: {
      user_sync: 'ready',
      im_notification: 'ready',
      im_group: 'pending_verification',
    },
  }),
  ['base', 'user_sync', 'im_notification', 'im_group'],
  'newly introduced IM group capability must be testable from existing integration instances',
);

assert.deepEqual(
  getIntegrationDetailSummaryItems({ activeTab: 'base', instance: readyInstance, t }),
  [{
    label: 'system.integrationCenter.configurationValidation',
    value: 'system.integrationCenter.testStatusHealthy',
    tone: 'success',
  }],
);

assert.deepEqual(
  getIntegrationBaseCapabilityStatusItems({
    instance: {
      status: 'ready',
      capability_status: {
        user_sync: 'pending_verification',
        login_auth: 'ready',
      },
      capability_enabled: {
        user_sync: true,
        login_auth: false,
      },
    },
    t,
  }),
  [
    {
      label: 'system.integrationCenter.capability.userSync',
      value: 'system.integrationCenter.capabilityValidationPending',
      tone: 'neutral',
    },
    {
      label: 'system.integrationCenter.capability.loginAuth',
      value: 'system.integrationCenter.disabled',
      tone: 'neutral',
    },
  ],
);

assert.deepEqual(
  getIntegrationDetailSummaryItems({
    activeTab: 'user_sync',
    instance: { ...readyInstance, status: 'verification_failed' },
    t,
  }),
  [
    {
      label: 'system.integrationCenter.enableStatus',
      value: 'system.integrationCenter.enabled',
      tone: 'success',
    },
    {
      label: 'system.integrationCenter.capabilityConfigurationValidation',
      value: 'system.integrationCenter.baseConnectionAbnormal',
      tone: 'error',
    },
  ],
);

assert.deepEqual(
  getIntegrationDetailSummaryItems({
    activeTab: 'user_sync',
    instance: {
      ...readyInstance,
      capability_enabled: { user_sync: false },
      capability_status: { user_sync: 'verification_failed' },
    },
    t,
  }),
  [
    {
      label: 'system.integrationCenter.enableStatus',
      value: 'system.integrationCenter.disabled',
      tone: 'neutral',
    },
    {
      label: 'system.integrationCenter.capabilityConfigurationValidation',
      value: 'system.integrationCenter.capabilityValidationFailed',
      tone: 'error',
    },
  ],
);

assert.deepEqual(
  getIntegrationDetailSummaryItems({
    activeTab: 'user_sync',
    instance: {
      ...readyInstance,
      capability_status: { user_sync: 'ready' },
    },
    t,
  }),
  [
    {
      label: 'system.integrationCenter.enableStatus',
      value: 'system.integrationCenter.enabled',
      tone: 'success',
    },
    {
      label: 'system.integrationCenter.capabilityConfigurationValidation',
      value: 'system.integrationCenter.capabilityValidationPassed',
      tone: 'success',
    },
  ],
);

assert.equal(
  getIntegrationDiagnosticMessage('provider.auth_failed', t),
  'system.integrationCenter.diagnosticAuthFailed',
);
assert.equal(
  getIntegrationDiagnosticMessage('provider.permission_unverified', t),
  'system.integrationCenter.diagnosticPermissionUnverified',
);
assert.equal(
  getIntegrationDiagnosticMessage('provider.bot_not_enabled', t),
  'system.integrationCenter.diagnosticBotNotEnabled',
);
assert.equal(
  getIntegrationDiagnosticMessage('unknown.code', t), 'system.integrationCenter.diagnosticRequestFailed');

console.log('integration center status summary tests passed');
