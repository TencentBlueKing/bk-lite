import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { createThemeCss, legacyVariableMap } from '../src/theme/css-adapter';
import { defaultDarkTokens, defaultLightTokens, defaultTheme } from '../src/theme/defaults';

const detailPage = readFileSync(
  new URL('../src/app/system-manager/(pages)/integration-center/detail/page.tsx', import.meta.url),
  'utf8',
);

assert.match(
  detailPage,
  /<section className="grid overflow-hidden rounded-md bg-\[var\(--color-bg\)\] shadow-sm xl:grid-cols-\[minmax\(0,8\.4fr\)_minmax\(200px,1\.6fr\)\]">/,
  'integration detail main pane must use the container surface token so dark theme darkens with chrome',
);
assert.doesNotMatch(
  detailPage,
  /\bbg-white\b/,
  'integration detail must not hardcode a white pane that fights dark-theme labels and inputs',
);
assert.match(
  detailPage,
  /className="mb-4 text-\[16px\] font-semibold text-\[var\(--color-text\)\]"/,
  'section titles must keep semantic text tokens so they remain readable on the themed pane',
);
assert.match(
  detailPage,
  /className="rounded-md border border-\[var\(--color-border\)\] bg-\[var\(--color-bg\)\] px-3 py-2"/,
  'status cards must stay on the same surface token as the pane, distinguished by border',
);
assert.equal(
  legacyVariableMap['--color-bg'],
  'surfaceContainer',
  '--color-bg must remain the main container / card surface token',
);
assert.equal(defaultLightTokens.surfaceContainer, '#FFFFFF');
assert.equal(
  defaultDarkTokens.surfaceContainer,
  '#141414',
  'dark theme container surface must be dark, not white',
);
assert.notEqual(defaultDarkTokens.surfaceContainer, '#FFFFFF');
assert.equal(defaultDarkTokens.textPrimary, 'rgba(255,255,255, 0.9)');

const css = createThemeCss(defaultTheme);
assert.match(css, /html\.dark\{[^}]*--color-bg:var\(--theme-color-surface-container\)/);
assert.match(css, /html\.dark\{[^}]*--theme-color-surface-container:#141414/);

console.log('integration center detail dark theme contract passed');
