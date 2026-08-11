import assert from 'node:assert/strict';
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
