import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const floatingButtonCss = readFileSync(
  new URL('../packages/webchat-ui/src/styles/floating-button.css', import.meta.url),
  'utf8'
);

test('webchat animations do not override generic application keyframes', () => {
  assert.doesNotMatch(floatingButtonCss, /@keyframes\s+pulse\b/);
  assert.match(
    floatingButtonCss,
    /@keyframes\s+webchat-floating-button-pulse\b/
  );
  assert.match(
    floatingButtonCss,
    /animation:\s*webchat-floating-button-pulse\s+2s\s+infinite/
  );
});
