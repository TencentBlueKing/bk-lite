import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { copyPublicDirectories } from '../src/utils/dynamicsMerged.mjs';

const temporaryRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), 'copy-public-error-')
);
const appRoot = path.join(temporaryRoot, 'apps');
const publicRoot = path.join(appRoot, 'demo', 'public');
const destinationRoot = path.join(temporaryRoot, 'destination');
const originalConsoleError = console.error;
let errorLog = '';

try {
  fs.mkdirSync(publicRoot, { recursive: true });
  fs.symlinkSync(
    path.join(temporaryRoot, 'missing-source'),
    path.join(publicRoot, 'broken-link')
  );

  console.error = (...args) => {
    errorLog += args.map(String).join(' ');
  };
  assert.throws(() => copyPublicDirectories({
    communityAppRoots: [appRoot],
    enterpriseAppRoot: path.join(temporaryRoot, 'missing-enterprise-apps'),
    enterprisePublicRoot: path.join(temporaryRoot, 'missing-enterprise-public'),
    destinationRoot,
  }), /ENOENT|missing-source/);
} finally {
  console.error = originalConsoleError;
  fs.rmSync(temporaryRoot, { recursive: true, force: true });
}

assert.match(errorLog, /Failed to copy contents/);
console.log('public asset copy failures stop the build');
