import assert from 'node:assert/strict';
import {
  deriveControllerInstallDisplay,
  deriveControllerInstallPhases,
  getControllerInstallDisplayLabel,
  getControllerInstallPhaseLabel,
  getInstallerFailureGuidance,
  getInstallerSummaryProgressInfo,
  getInstallerSummaryGuidance,
  normalizeInstallerResult
} from '../src/app/node-manager/utils/installerProgress.ts';

const translations: Record<string, string> = {
  'node-manager.cloudregion.node.installerSuggestionObjectMissing': 'localized object-missing guidance',
  'node-manager.cloudregion.node.installerSuggestionFileBusy': 'localized file-busy guidance',
  'node-manager.cloudregion.node.installerSuggestionExtract': 'localized extract fallback',
  'node-manager.cloudregion.node.installerSummaryNoEvents': 'installer details missing',
  'node-manager.cloudregion.node.installerSummaryNoReportConnectivityTimeout': 'installer no report timeout guidance',
  'node-manager.cloudregion.node.installerSummarySuccessWithoutDetail': 'success without detail guidance',
  'node-manager.cloudregion.node.installerSummaryConnectivityPending': 'sidecar pending guidance',
  'node-manager.cloudregion.node.installPhaseCredential': 'Credential validation',
  'node-manager.cloudregion.node.installPhaseCommand': 'Dispatch install command',
  'node-manager.cloudregion.node.installPhaseInstaller': 'Installer execution',
  'node-manager.cloudregion.node.installPhaseConnectivity': 'Wait for node connection',
  'node-manager.cloudregion.node.installStateInstallerNoReport': 'Installer no report',
  'node-manager.cloudregion.node.installStateConnectivityWaiting': 'Waiting for node connection',
  'node-manager.cloudregion.node.installStateSuccessWithoutDetail': 'Success without detail',
  'node-manager.cloudregion.node.failureContextBucket': 'Object Bucket',
  'node-manager.cloudregion.node.failureContextFileKey': 'Object Key',
  'node-manager.cloudregion.node.failureContextArchitecture': 'Target Architecture',
  'node-manager.cloudregion.node.failureContextTargetPath': 'Target Path'
};

const t = (key: string) => translations[key] || key;

const objectMissingResult = normalizeInstallerResult({
  failure: {
    type: 'object_missing',
    summary: 'Required installation package was not found in object storage',
    context: {
      bucket: 'bklite',
      file_key: 'linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz',
      cpu_architecture: 'arm64'
    }
  },
  steps: [
    {
      action: 'download_package',
      status: 'error',
      message: 'Download failed',
      timestamp: '2026-04-28T08:55:32Z',
      details: {
        error: 'Download failed: get object failed: nats: object not found'
      }
    }
  ]
});

const objectMissingGuidance = getInstallerFailureGuidance(t, objectMissingResult);
assert.equal(objectMissingGuidance.reason, 'Required installation package was not found in object storage');
assert.equal(objectMissingGuidance.suggestion, 'localized object-missing guidance');
assert.deepEqual(objectMissingGuidance.context, [
  'Object Bucket: bklite',
  'Object Key: linux/arm64/Controller/3.1.22/fusion-collectors-arm64.tar.gz',
  'Target Architecture: arm64'
]);

const fileBusyResult = normalizeInstallerResult({
  steps: [
    {
      action: 'extract_package',
      status: 'error',
      message: 'Extract failed: open /opt/fusion-collectors/bin/vector: text file busy',
      timestamp: '2026-04-28T08:46:26Z',
      details: {
        error: 'Extract failed: open /opt/fusion-collectors/bin/vector: text file busy',
        failure: {
          type: 'file_busy',
          summary: 'A running process is blocking the target file from being replaced',
          context: {
            target_path: '/opt/fusion-collectors/bin/vector'
          }
        }
      }
    }
  ]
});

const fileBusyGuidance = getInstallerFailureGuidance(t, fileBusyResult);
assert.equal(fileBusyGuidance.reason, 'A running process is blocking the target file from being replaced');
assert.ok(fileBusyGuidance.context?.includes('Target Path: /opt/fusion-collectors/bin/vector'));
assert.equal(fileBusyGuidance.suggestion, 'localized file-busy guidance');

const fallbackResult = normalizeInstallerResult({
  steps: [
    {
      action: 'extract_package',
      status: 'error',
      message: 'Extract failed',
      timestamp: '2026-04-28T08:46:26Z',
      details: {
        error: 'Extract failed'
      }
    }
  ]
});

const fallbackGuidance = getInstallerFailureGuidance(t, fallbackResult);
assert.equal(fallbackGuidance.suggestion, 'localized extract fallback');

const summaryResult = normalizeInstallerResult({
  steps: [],
  installer_summary: {
    state: 'installer_success_connectivity_pending',
    expected_steps: ['fetch_session', 'prepare_dirs', 'download', 'extract', 'write_config', 'install'],
    expected_count: 6,
    observed_count: 12,
    completed_steps: ['fetch_session', 'prepare_dirs', 'download', 'extract', 'write_config', 'install'],
    completed_count: 6,
    missing_steps: [],
    duplicate_count: 6,
    last_step: 'install',
    last_status: 'success',
    anomalies: ['duplicated_events', 'installer_success_connectivity_pending'],
    steps: [
      {
        action: 'install',
        status: 'success',
        message: 'Package installer finished',
        timestamp: '2026-04-28T08:55:32Z',
        details: {
          installer_event: true,
          raw_step: 'run_package_installer'
        }
      }
    ]
  }
});

assert.equal(summaryResult?.installer_summary?.completed_count, 6);
assert.equal(summaryResult?.installer_summary?.steps?.length, 1);
assert.equal(
  getInstallerSummaryGuidance(t, summaryResult?.installer_summary),
  'sidecar pending guidance'
);

assert.deepEqual(
  getInstallerSummaryProgressInfo(summaryResult?.installer_summary),
  {
    stepInfo: '6/6',
    percent: 100
  }
);

const missingSummaryResult = normalizeInstallerResult({
  steps: [],
  installer_summary: {
    state: 'no_installer_events',
    expected_steps: ['fetch_session', 'prepare_dirs', 'download', 'extract', 'write_config', 'install'],
    expected_count: 6,
    observed_count: 0,
    completed_steps: [],
    completed_count: 0,
    missing_steps: [],
    duplicate_count: 0,
    last_step: null,
    last_status: null,
    anomalies: ['no_installer_events'],
    steps: []
  }
});

assert.equal(
  getInstallerSummaryGuidance(t, missingSummaryResult?.installer_summary),
  'installer details missing'
);
assert.equal(
  getInstallerSummaryProgressInfo(missingSummaryResult?.installer_summary),
  null
);

assert.equal(
  getInstallerSummaryGuidance(t, {
    ...missingSummaryResult!.installer_summary!,
    state: 'installer_no_report_connectivity_timeout'
  }),
  'installer no report timeout guidance'
);
assert.equal(
  getInstallerSummaryGuidance(t, {
    ...missingSummaryResult!.installer_summary!,
    state: 'installer_success_without_detail'
  }),
  'success without detail guidance'
);

const noReportDisplay = deriveControllerInstallDisplay({
  steps: [
    { action: 'credential_check', status: 'success', message: 'Validate credentials', timestamp: '' },
    { action: 'run', status: 'success', message: 'Installer bootstrap completed', timestamp: '' },
    { action: 'connectivity_check', status: 'running', message: 'Wait for node connection', timestamp: '' }
  ],
  installer_summary: missingSummaryResult?.installer_summary
});

assert.equal(noReportDisplay.state, 'installer_no_report');
assert.equal(noReportDisplay.phase, 'installer_execution');
assert.equal(noReportDisplay.severity, 'warning');
assert.equal(noReportDisplay.installerStepsReceived, false);

const successWithoutDetailDisplay = deriveControllerInstallDisplay({
  steps: [
    { action: 'credential_check', status: 'success', message: 'Validate credentials', timestamp: '' },
    { action: 'run', status: 'success', message: 'Installer bootstrap completed', timestamp: '' },
    { action: 'connectivity_check', status: 'success', message: 'Sidecar connectivity confirmed', timestamp: '' }
  ],
  installer_summary: {
    ...missingSummaryResult!.installer_summary!,
    state: 'installer_success_without_detail'
  }
});

assert.equal(successWithoutDetailDisplay.state, 'success_without_detail');
assert.equal(successWithoutDetailDisplay.phase, 'node_connectivity');
assert.equal(successWithoutDetailDisplay.severity, 'success');
assert.equal(successWithoutDetailDisplay.installerStepsReceived, false);

const connectivityWaitingDisplay = deriveControllerInstallDisplay(summaryResult);
assert.equal(connectivityWaitingDisplay.state, 'connectivity_waiting');
assert.equal(connectivityWaitingDisplay.phase, 'node_connectivity');
assert.equal(connectivityWaitingDisplay.severity, 'processing');
assert.equal(connectivityWaitingDisplay.installerStepsReceived, true);

const noReportPhases = deriveControllerInstallPhases({
  steps: [
    { action: 'credential_check', status: 'success', message: 'Validate credentials', timestamp: '' },
    { action: 'run', status: 'success', message: 'Installer bootstrap completed', timestamp: '' },
    { action: 'connectivity_check', status: 'running', message: 'Wait for node connection', timestamp: '' }
  ],
  installer_summary: missingSummaryResult?.installer_summary
});

assert.deepEqual(
  noReportPhases.map((phase) => [phase.code, phase.status]),
  [
    ['credential_validation', 'success'],
    ['command_dispatch', 'success'],
    ['installer_execution', 'warning'],
    ['node_connectivity', 'running']
  ]
);
assert.equal(noReportPhases[2].detailState, 'no_report');
assert.equal(noReportPhases[2].showMissingSteps, false);

const partialInstallerPhases = deriveControllerInstallPhases({
  steps: [
    { action: 'credential_check', status: 'success', message: 'Validate credentials', timestamp: '' },
    { action: 'run', status: 'success', message: 'Installer bootstrap completed', timestamp: '' }
  ],
  installer_summary: {
    state: 'incomplete_installer_events',
    expected_count: 6,
    observed_count: 2,
    completed_count: 1,
    missing_steps: ['prepare_dirs', 'extract', 'write_config', 'install'],
    steps: [
      { action: 'fetch_session', status: 'success', message: 'Installer session fetched', timestamp: '' },
      { action: 'download', status: 'error', message: 'Download failed', timestamp: '' }
    ]
  }
});

assert.equal(partialInstallerPhases[2].status, 'error');
assert.equal(partialInstallerPhases[2].detailState, 'partial');
assert.equal(partialInstallerPhases[2].showMissingSteps, true);

assert.equal(
  getControllerInstallPhaseLabel(t, 'installer_execution'),
  'Installer execution'
);
assert.equal(
  getControllerInstallDisplayLabel(t, noReportDisplay),
  'Installer no report'
);
assert.equal(
  getControllerInstallDisplayLabel(t, connectivityWaitingDisplay),
  'Waiting for node connection'
);
assert.equal(
  getControllerInstallDisplayLabel(t, successWithoutDetailDisplay),
  'Success without detail'
);

console.log('installer-progress tests passed');
