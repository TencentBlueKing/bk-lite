import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderToStaticMarkup } from 'react-dom/server';
import { ThemeBootstrap } from '../src/theme/bootstrap';
import { createThemeCss, legacyVariableMap } from '../src/theme/css-adapter';
import { defaultDarkTokens, defaultLightTokens, defaultTheme } from '../src/theme/defaults';
import { normalizeThemeMode } from '../src/theme/mode-storage';
import { resolveTheme } from '../src/theme/resolve';

const repositoryRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));

const sortedKeys = (value: object) => Object.keys(value).sort();

assert.deepEqual(
  sortedKeys(defaultLightTokens),
  sortedKeys(defaultDarkTokens),
  'Light 与 Dark 必须定义相同的语义 Token'
);
assert.ok(
  Object.values(defaultLightTokens).every(Boolean)
  && Object.values(defaultDarkTokens).every(Boolean),
  '默认主题不能包含空值'
);

const resolved = resolveTheme({
  themeId: 'test',
  themeVersion: '1',
  schemaVersion: 1,
  light: { interactionPrimary: '#123456' },
  dark: { surfacePage: '#010203' },
});
assert.equal(resolved.light.interactionPrimary, '#123456');
assert.equal(resolved.light.chartPrimary, '#123456');
assert.equal(resolved.light.textPrimary, defaultTheme.light.textPrimary);
assert.equal(resolved.dark.surfacePage, '#010203');
assert.equal(resolved.dark.textPrimary, defaultTheme.dark.textPrimary);

const css = createThemeCss(defaultTheme);
assert.match(css, /:root,html\.light\{/);
assert.match(css, /html\.dark\{/);
for (const legacyVariable of Object.keys(legacyVariableMap)) {
  assert.ok(css.includes(`${legacyVariable}:var(`), `缺少兼容变量 ${legacyVariable}`);
}

const bootstrapMarkup = renderToStaticMarkup(<ThemeBootstrap />);
assert.match(bootstrapMarkup, /id="bklite-theme-tokens"/);
assert.match(bootstrapMarkup, /id="bklite-theme-bootstrap"/);
assert.match(bootstrapMarkup, /localStorage\.getItem\('theme'\)/);

assert.equal(normalizeThemeMode('dark'), 'dark');
assert.equal(normalizeThemeMode('light'), 'light');
assert.equal(normalizeThemeMode('system'), 'light');
assert.equal(normalizeThemeMode(undefined), 'light');

const sourceFiles = [
  'src/app',
  'src/components',
  'src/context',
  'src/hooks',
].flatMap((directory) => {
  const output = execFileSync('rg', ['--files', directory, '-g', '*.{ts,tsx}'], {
    cwd: repositoryRoot,
    encoding: 'utf8',
  });
  return output.trim().split('\n').filter(Boolean);
});

const forbiddenPatterns = [
  /localStorage\.(?:getItem|setItem)\(['"]theme['"]/,
  /classList\.(?:contains|add|remove|toggle)\(['"]dark['"]/,
  /@\/context\/theme/,
  /@\/constants\/theme/,
];

for (const relativePath of sourceFiles) {
  const source = readFileSync(resolve(repositoryRoot, relativePath), 'utf8');
  for (const pattern of forbiddenPatterns) {
    assert.doesNotMatch(source, pattern, `${relativePath} 绕过主题模块: ${pattern}`);
  }
}

console.log('theme module contract checks passed');
