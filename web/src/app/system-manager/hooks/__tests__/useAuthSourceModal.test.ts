import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

import type { AuthSource } from '../../types/security';
import { replaceAuthSource } from '../authSourceState.ts';

const originalSource: AuthSource = {
  id: 1,
  name: 'BlueKing',
  source_type: 'bk_login',
  other_config: { app_token: 'plaintext-submitted-by-user' },
  enabled: true,
  is_build_in: false,
};

test('replaceAuthSource keeps the masked server response instead of submitted plaintext', () => {
  const serverResponse: AuthSource = {
    ...originalSource,
    other_config: { app_token: '******' },
  };

  const result = replaceAuthSource([originalSource], serverResponse);

  assert.equal(result[0].other_config.app_token, '******');
});

test('useAuthSourceModal updates state from the server response', async () => {
  const hookSource = await readFile(new URL('../useAuthSourceModal.ts', import.meta.url), 'utf8');

  assert.match(hookSource, /const updatedSource = await updateAuthSource\(editingSource\.id, updateData\)/);
  assert.match(hookSource, /replaceAuthSource\(authSources, enhancedSource\)/);
  assert.doesNotMatch(hookSource, /const updatedSource = \{ \.\.\.editingSource, \.\.\.updateData \}/);
});
