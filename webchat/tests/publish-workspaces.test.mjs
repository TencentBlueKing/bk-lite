import assert from 'node:assert/strict';
import test from 'node:test';

import { publishWorkspaces } from '../scripts/publish-workspaces.mjs';

function result(status, stdout = '', stderr = '') {
  return { status, stdout, stderr };
}

test('skips versions that are already published and continues to the next workspace', () => {
  const calls = [];
  const runner = (_command, args) => {
    calls.push(args);
    if (args[0] === 'pkg') return result(0, JSON.stringify({ workspace: args[2] === 'name' ? args[4] : '1.0.0' }));
    if (args[0] === 'view') return result(0, '"1.0.0"');
    return result(1, '', 'unexpected publish');
  };
  publishWorkspaces({ runner });
  assert.equal(calls.filter(([command]) => command === 'publish').length, 0);
  assert.equal(calls.filter(([command]) => command === 'view').length, 2);
});

test('publishes a missing version and rechecks after an ambiguous publish failure', () => {
  let viewCount = 0;
  const calls = [];
  const runner = (_command, args) => {
    calls.push(args);
    if (args[0] === 'pkg') return result(0, JSON.stringify({ workspace: args[2] === 'name' ? args[4] : '1.0.0' }));
    if (args[0] === 'view') {
      viewCount += 1;
      return viewCount === 1 ? result(1, '', 'npm error code E404') : result(0, '"1.0.0"');
    }
    if (args[0] === 'publish') return result(1, '', 'connection reset after upload');
    throw new Error(`unexpected call: ${args.join(' ')}`);
  };
  publishWorkspaces({ runner });
  assert.deepEqual(calls.filter(([command]) => command === 'publish').length, 1);
});

test('does not mistake registry or authentication errors for a missing version', () => {
  const runner = (_command, args) => {
    if (args[0] === 'pkg') return result(0, JSON.stringify({ workspace: args[2] === 'name' ? args[4] : '1.0.0' }));
    return result(1, '', 'npm error code E401 authentication required');
  };
  assert.throws(() => publishWorkspaces({ runner }), /E401/);
});
