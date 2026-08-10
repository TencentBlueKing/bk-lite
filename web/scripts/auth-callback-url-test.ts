import assert from 'node:assert/strict';
import {
  buildLegacyThirdLoginCallbackUrl,
  getLegacyThirdLoginCode,
  toSafeRelativeCallbackUrl,
} from '../src/utils/authRedirect';

function run(name: string, fn: () => void) {
  fn();
  console.log(`  ✓ ${name}`);
}

run('keeps relative callback paths unchanged', () => {
  assert.equal(toSafeRelativeCallbackUrl('/monitor/events?tab=detail'), '/monitor/events?tab=detail');
});

run('converts same-origin absolute callback URL into relative path', () => {
  assert.equal(
    toSafeRelativeCallbackUrl('https://bk-lite.example.com/monitor/events?tab=detail#panel', 'https://bk-lite.example.com'),
    '/monitor/events?tab=detail#panel',
  );
});

run('rejects cross-origin absolute callback URL', () => {
  assert.equal(
    toSafeRelativeCallbackUrl('https://attacker.example.com/steal?token=1', 'https://bk-lite.example.com'),
    '/',
  );
});

run('rejects protocol-relative callback URL', () => {
  assert.equal(toSafeRelativeCallbackUrl('//attacker.example.com/steal'), '/');
});

run('builds a legacy external callback URL when third_login_code is present', () => {
  assert.equal(
    buildLegacyThirdLoginCallbackUrl(
      'https://bklite.ai/playground?third_login_code=old-code&token=old-token#console',
      'new-token',
      'new-code',
    ),
    'https://bklite.ai/playground?third_login_code=new-code&token=new-token#console',
  );
});

run('does not enable a legacy external callback without third_login_code', () => {
  assert.equal(
    buildLegacyThirdLoginCallbackUrl('https://external.example/playground', 'new-token'),
    '/',
  );
});

run('extracts the legacy third login code from an external callback URL', () => {
  assert.equal(
    getLegacyThirdLoginCode('http://localhost:3001/playground?third_login_code=legacy-code'),
    'legacy-code',
  );
});

run('does not extract a legacy third login code from a relative callback URL', () => {
  assert.equal(getLegacyThirdLoginCode('/playground?third_login_code=legacy-code'), undefined);
});

console.log('All auth callback URL tests passed.');
