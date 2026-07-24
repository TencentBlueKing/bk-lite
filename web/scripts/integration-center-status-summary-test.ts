import assert from 'node:assert/strict';

import {
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
      enableValue: 'system.integrationCenter.enabled',
    },
    {
      label: 'system.integrationCenter.capability.loginAuth',
      value: 'system.integrationCenter.capabilityValidationPassed',
      tone: 'success',
      enableValue: 'system.integrationCenter.disabled',
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

assert.equal(
  getIntegrationDiagnosticMessage('provider.auth_failed', t),
  'system.integrationCenter.diagnosticAuthFailed',
);
assert.equal(
  getIntegrationDiagnosticMessage('unknown.code', t), 'system.integrationCenter.diagnosticRequestFailed');

console.log('integration center status summary tests passed');
