import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { extname } from 'node:path';
import test from 'node:test';

const floatingButtonCss = readFileSync(
  new URL('../packages/webchat-ui/src/styles/floating-button.css', import.meta.url),
  'utf8'
);
const webchatCss = [
  floatingButtonCss,
  readFileSync(new URL('../packages/webchat-ui/src/styles/chat.css', import.meta.url), 'utf8'),
].join('\n');

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
  const keyframeNames = [...webchatCss.matchAll(/@(?:-webkit-)?keyframes\s+([\w-]+)/g)]
    .map((match) => match[1]);
  assert.ok(keyframeNames.length > 0);
  assert.deepEqual(
    keyframeNames.filter((name) => !name.startsWith('webchat-')),
    []
  );
});

const productionSourceRoots = [
  new URL('../../web/src/', import.meta.url),
  new URL('../packages/webchat-ui/src/', import.meta.url),
];

function collectProductionFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === '__tests__' || entry.name === 'node_modules') return [];
    const url = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, directory);
    if (entry.isDirectory()) return collectProductionFiles(url);
    if (/\.(?:test|spec)\.[cm]?[jt]sx?$/.test(entry.name)) return [];
    return ['.css', '.scss', '.sass', '.less', '.js', '.jsx', '.ts', '.tsx'].includes(extname(entry.name))
      ? [url]
      : [];
  });
}

test('application loading animations use the namespaced neutral pulse', () => {
  const offenders = productionSourceRoots.flatMap(collectProductionFiles).flatMap((url) => {
    const source = readFileSync(url, 'utf8');
    const violations = [];
    if (/\banimate-pulse\b/.test(source)) violations.push('animate-pulse');
    if (/@(?:-webkit-)?keyframes\s+pulse\b/.test(source)) violations.push('@keyframes pulse');
    return violations.map((violation) => `${url.pathname}: ${violation}`);
  });

  assert.deepEqual(offenders, []);
});
