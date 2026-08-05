import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsRoot = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsRoot, '..');
const repositoryRoot = path.resolve(webRoot, '..');
const enterpriseRoot = fs.realpathSync(path.join(webRoot, 'enterprise'));
const config = (await import('../next.config.mjs')).default;

assert.equal(config.outputFileTracingRoot, repositoryRoot);
assert.equal(config.turbopack?.root, repositoryRoot);

const enterpriseRelativePath = path.relative(repositoryRoot, enterpriseRoot);
assert.ok(
  enterpriseRelativePath &&
    !enterpriseRelativePath.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(enterpriseRelativePath),
  `enterprise source must remain inside the build root: ${enterpriseRoot}`
);

console.log('Next build root is limited to the BK-Lite repository');
