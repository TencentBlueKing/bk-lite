import assert from 'node:assert/strict';
import { getInstallerFailureGuidance, normalizeInstallerResult } from '../src/app/node-manager/utils/installerProgress.ts';

const translations: Record<string, string> = {
  'node-manager.cloudregion.node.installerSuggestionObjectMissing': 'localized object-missing guidance',
  'node-manager.cloudregion.node.installerSuggestionFileBusy': 'localized file-busy guidance',
  'node-manager.cloudregion.node.installerSuggestionExtract': 'localized extract fallback',
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

console.log('installer-progress tests passed');
