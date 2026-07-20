import assert from 'node:assert/strict';
import { toSafeRelativeCallbackUrl } from '../src/utils/authRedirect';

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

console.log('All auth callback URL tests passed.');
