import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsRoot, '..');
const repositoryRoot = path.resolve(webRoot, '..');
const enterpriseRoot = fs.realpathSync(path.join(webRoot, 'enterprise'));
const config = (await import('../next.config.mjs')).default;

function commonFilesystemRoot(left, right) {
  const leftParts = path.resolve(left).split(path.sep);
  const rightParts = path.resolve(right).split(path.sep);
  const shared = [];
  for (let i = 0; i < Math.min(leftParts.length, rightParts.length); i += 1) {
    if (leftParts[i] !== rightParts[i]) {
      break;
    }
    shared.push(leftParts[i]);
  }
  return shared.length > 1 ? shared.join(path.sep) : path.sep;
}

const expectedRoot = commonFilesystemRoot(repositoryRoot, enterpriseRoot);

assert.equal(config.outputFileTracingRoot, expectedRoot);
assert.equal(config.turbopack?.root, expectedRoot);

const enterpriseRelativePath = path.relative(expectedRoot, enterpriseRoot);
assert.ok(
  enterpriseRelativePath &&
    !enterpriseRelativePath.startsWith(`..${path.sep}`) &&
    enterpriseRelativePath !== '..' &&
    !path.isAbsolute(enterpriseRelativePath),
  `enterprise source must remain inside the build root: ${enterpriseRoot}`
);

const repositoryRelativePath = path.relative(expectedRoot, repositoryRoot);
assert.ok(
  repositoryRelativePath === '' ||
    (!repositoryRelativePath.startsWith(`..${path.sep}`) &&
      repositoryRelativePath !== '..' &&
      !path.isAbsolute(repositoryRelativePath)),
  `BK-Lite repository must remain inside the build root: ${repositoryRoot}`
);

console.log('Next build root covers BK-Lite and enterprise sources');
